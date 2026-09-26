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

        Membership = request.env["slide.channel.partner"].sudo()
        memberships = Membership.search(
            [
                ("partner_id", "=", user.partner_id.id),
                ("member_status", "!=", "invited"),
                ("channel_id.active", "=", True),
                ("channel_id.website_published", "=", True),
                ("channel_id.visibility", "=", "public"),
                "|",
                ("channel_id.website_id", "=", False),
                ("channel_id.website_id", "=", request.website.id),
            ],
            order="write_date desc, id desc",
            limit=6,
        )
        course_rows = []
        for membership in memberships:
            completion = float(membership.completion or 0.0)
            if completion <= 1:
                completion *= 100
            course_rows.append(
                {
                    "course": membership.channel_id,
                    "completion": min(max(completion, 0.0), 100.0),
                    "is_completed": membership.member_status == "completed" or completion >= 100,
                }
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
                "facodi_course_rows": course_rows,
                "facodi_submission_rows": submission_rows,
                "facodi_learning_stats": {
                    "courses": len(course_rows),
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
                    "completed_courses": len(
                        [row for row in course_rows if row["is_completed"]]
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
