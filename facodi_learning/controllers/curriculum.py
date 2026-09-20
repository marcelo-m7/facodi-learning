from odoo import http
from odoo.http import request


class FacodiCurriculumController(http.Controller):
    @http.route("/curriculos", type="http", auth="public", website=True, sitemap=True)
    def curriculum_index(self, **kwargs):
        references = (
            request.env["facodi.learning.curriculum.reference"]
            .sudo()
            .search(
                [
                    ("website_published", "=", True),
                    ("validated_at", "!=", False),
                ],
                order="institution, programme_name, academic_year desc, id",
            )
        )
        return request.render(
            "facodi_learning.curriculum_public_index",
            {"references": references},
        )

    @http.route(
        "/curriculos/<int:reference_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def curriculum_detail(self, reference_id, **kwargs):
        reference = (
            request.env["facodi.learning.curriculum.reference"]
            .sudo()
            .search(
                [
                    ("id", "=", reference_id),
                    ("website_published", "=", True),
                    ("validated_at", "!=", False),
                ],
                limit=1,
            )
        )
        if not reference:
            return request.not_found()
        return request.render(
            "facodi_learning.curriculum_public_detail",
            {
                "reference": reference,
                "unit_groups": reference._facodi_public_units_grouped(),
                "coverage_links": reference._facodi_public_coverage_links(),
            },
        )
