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

        enrolled_course_ids = set(enrolled_courses.ids)

        Reference = request.env["facodi.learning.curriculum.reference"].sudo()
        roadmap = Reference.search(
            [
                ("website_published", "=", True),
                ("validated_at", "!=", False),
                ("selection_enabled", "=", True),
            ],
            order="academic_year desc, id",
            limit=1,
        )
        if not roadmap:
            roadmap = Reference.search(
                [
                    ("website_published", "=", True),
                    ("validated_at", "!=", False),
                ],
                order="academic_year desc, id",
                limit=1,
            )

        academic_map = False
        if roadmap:
            matrix = roadmap._facodi_public_unit_matrix(website=request.website)
            counts = {"covered": 0, "partial": 0, "gap": 0}
            preview = []
            for entry in matrix:
                status = entry["coverage_status"]
                counts[status] = counts.get(status, 0) + 1
                on_desk = any(
                    row["channel"].id in enrolled_course_ids
                    for row in entry["coverage_rows"]
                )
                preview.append(
                    {
                        **entry,
                        "on_desk": on_desk,
                    }
                )
            academic_map = {
                "reference": roadmap,
                "url": f"/roadmaps/{roadmap.id}",
                "counts": counts,
                "preview": preview[:8],
                "total": len(matrix),
            }

        forum_posts = []
        if "forum.post" in request.env.registry.models:
            forum_posts = request.env["forum.post"].search(
                [
                    ("parent_id", "=", False),
                    ("active", "=", True),
                    ("state", "=", "active"),
                    ("website_id", "in", [False, request.website.id]),
                ],
                order="last_activity_date desc, id desc",
                limit=4,
            )

        values.update(
            {
                "facodi_enrolled_courses": enrolled_courses,
                "facodi_submission_rows": submission_rows,
                "facodi_academic_map": academic_map,
                "facodi_forum_posts": forum_posts,
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
