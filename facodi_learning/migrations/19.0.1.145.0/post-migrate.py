from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    review_table = "facodi_learning_content_review"

    # Preserve the workflow meaning of existing rows introduced before the
    # explicit review_reason field existed. This is metadata migration only;
    # it does not invent provenance or editorial decisions.
    cr.execute(
        f"""
        UPDATE {review_table}
           SET review_reason = CASE origin
               WHEN 'source_ingestion' THEN 'source_ingestion'
               WHEN 'legacy_reconciliation' THEN 'legacy_publication'
               ELSE 'manual'
           END
        """
    )

    root_id = env.ref("base.user_root").id
    admin_id = env.ref("base.user_admin").id
    cr.execute(
        f"""
        UPDATE {review_table} AS review
           SET responsible_id = COALESCE(
               (
                   SELECT users.id
                     FROM slide_slide AS slide
                     JOIN slide_channel AS channel
                       ON channel.id = slide.channel_id
                     JOIN res_users AS users
                       ON users.id = channel.user_id
                    WHERE slide.id = review.slide_id
                      AND users.active IS TRUE
                      AND COALESCE(users.share, FALSE) IS FALSE
                      AND users.id <> %s
                    LIMIT 1
               ),
               %s
           )
         WHERE review.responsible_id IS NULL
            OR review.responsible_id = %s
            OR EXISTS (
                SELECT 1
                  FROM res_users AS users
                 WHERE users.id = review.responsible_id
                   AND (
                       users.active IS NOT TRUE
                       OR COALESCE(users.share, FALSE) IS TRUE
                   )
            )
        """,
        (root_id, admin_id, root_id),
    )

    env["website"].search([]).action_facodi_enable_publication_review()

    # Production's historical eLearning catalogue includes valid site-less
    # slide records (website_id=False). They are intentionally not brought
    # under the runtime publication guard, but the one-time reconciliation
    # still needs accountable pending evidence for every currently public item.
    env["slide.slide"].search(
        [
            "|",
            ("is_published", "=", True),
            ("website_published", "=", True),
        ]
    )._facodi_enqueue_legacy_review_queue()
