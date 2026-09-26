from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class FacodiCustomerPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        user = request.env.user

        Submission = request.env["facodi.learning.submission"].sudo()
        submissions = Submission.search(
            [("submitted_by_id", "=", user.id)],
            order="create_date desc, id desc",
        )
        recent_submissions = submissions[:5]

        enrolled_courses = request.env["slide.channel"].search(
            [
                ("active", "=", True),
                ("is_published", "=", True),
                ("is_visible", "=", True),
                ("partner_ids", "in", [user.partner_id.id]),
            ],
            order="write_date desc, id desc",
            limit=6,
        )

        state_labels = dict(
            Submission._fields["state"]._description_selection(request.env)
        )
        submission_rows = [
            {
                "submission": submission,
                "state_label": state_labels.get(
                    submission.state,
                    submission.state,
                ),
            }
            for submission in recent_submissions
        ]

        values.update(
            {
                "facodi_enrolled_courses": enrolled_courses,
                "facodi_submission_rows": submission_rows,
                "facodi_learning_stats": {
                    "courses": len(enrolled_courses),
                    "contributions": len(submissions),
                    "in_review": len(
                        submissions.filtered(
                            lambda item: item.state in {"submitted", "reviewing"}
                        )
                    ),
                    "accepted": len(
                        submissions.filtered(
                            lambda item: item.state in {"accepted", "resolved"}
                        )
                    ),
                },
            }
        )
        return values


class FacodiPortalAliases(http.Controller):
    @http.route(
        "/minha-facodi",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def minha_facodi(self, **kwargs):
        return request.redirect("/my/home", code=302)
