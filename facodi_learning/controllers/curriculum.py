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
        website = request.website
        return request.render(
            "facodi_learning.curriculum_public_detail",
            {
                "reference": reference,
                "unit_groups": reference._facodi_public_units_grouped(),
                "unit_matrix_groups": reference._facodi_public_unit_matrix_grouped(
                    website=website
                ),
                "coverage_links": reference._facodi_public_coverage_links(
                    website=website
                ),
            },
        )

    @http.route(
        "/curriculos/<int:reference_id>/unidades/<path:unit_code>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def curriculum_unit_detail(self, reference_id, unit_code, **kwargs):
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

        unit = (
            request.env["facodi.learning.curriculum.unit"]
            .sudo()
            .search(
                [
                    ("reference_id", "=", reference.id),
                    ("external_unit_code", "=", unit_code),
                ],
                limit=1,
            )
        )
        if not unit:
            return request.not_found()

        coverage_rows = unit._facodi_public_coverage_rows(website=request.website)
        return request.render(
            "facodi_learning.curriculum_public_unit",
            {
                "reference": reference,
                "unit": unit,
                "coverage_rows": coverage_rows,
                "coverage_status": unit._facodi_public_coverage_status(
                    website=request.website
                ),
            },
        )
