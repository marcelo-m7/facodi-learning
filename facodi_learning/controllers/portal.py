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

        SlidePartner = request.env["slide.slide.partner"].sudo()
        completion_rows = SlidePartner.search(
            [
                ("partner_id", "=", user.partner_id.id),
                ("completed", "=", True),
            ],
            order="write_date desc, id desc",
            limit=12,
        )
        completion_by_slide = {
            row.slide_id.id: row
            for row in completion_rows
            if row.slide_id
        }
        visible_slides = request.env["slide.slide"].search(
            [
                ("id", "in", list(completion_by_slide)),
                ("active", "=", True),
                ("website_published", "=", True),
                ("channel_id.active", "=", True),
                ("channel_id.website_published", "=", True),
                ("channel_id.visibility", "=", "public"),
                "|",
                ("channel_id.website_id", "=", False),
                ("channel_id.website_id", "=", request.website.id),
            ]
        )
        visible_by_id = {slide.id: slide for slide in visible_slides}
        recent_learning_rows = []
        for completion in completion_rows:
            slide = visible_by_id.get(completion.slide_id.id)
            if not slide:
                continue
            recent_learning_rows.append(
                {
                    "slide": slide,
                    "course": slide.channel_id,
                    "completed_at": completion.write_date,
                }
            )
            if len(recent_learning_rows) >= 5:
                break

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

        enrolled_course_ids = set(memberships.mapped("channel_id").ids)

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
                "facodi_course_rows": course_rows,
                "facodi_submission_rows": submission_rows,
                "facodi_recent_learning_rows": recent_learning_rows,
                "facodi_academic_map": academic_map,
                "facodi_forum_posts": forum_posts,
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
        return request.redirect("/my/home", code=301)
