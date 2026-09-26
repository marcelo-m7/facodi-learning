from odoo import http
from odoo.http import request


class FacodiCurriculumController(http.Controller):
    @staticmethod
    def _public_references():
        return (
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

    @staticmethod
    def _positive_integer(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False
        return value if value > 0 else False

    @staticmethod
    def _nonnegative_float(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        return value if value >= 0 else False

    @http.route("/roadmaps", type="http", auth="public", website=True, sitemap=True)
    def roadmap_index(self, **kwargs):
        references = self._public_references()
        return request.render(
            "facodi_learning.curriculum_public_index",
            {"references": references},
        )

    @http.route(
        "/curriculos", type="http", auth="public", website=True, sitemap=False
    )
    def legacy_curriculum_index(self, **kwargs):
        return request.redirect("/roadmaps", code=301)

    @http.route(
        "/mapa-curricular", type="http", auth="public", website=True, sitemap=False
    )
    def legacy_curriculum_map(self, **kwargs):
        return request.redirect("/roadmaps", code=301)

    @http.route(
        "/unidades-curriculares", type="http", auth="public", website=True, sitemap=True
    )
    def curriculum_unit_index(self, **kwargs):
        references = self._public_references()
        reference_id = self._positive_integer(kwargs.get("reference_id"))
        if reference_id not in references.ids:
            reference_id = False

        curricular_year = self._positive_integer(kwargs.get("year"))
        period = kwargs.get("period")
        if period not in {"semester_1", "semester_2", "annual", "other"}:
            period = False
        credits = None
        if kwargs.get("credits"):
            credits = self._nonnegative_float(kwargs["credits"])

        Unit = request.env["facodi.learning.curriculum.unit"]
        available_entries = Unit._facodi_public_catalog_entries(website=request.website)
        entries = Unit._facodi_public_catalog_entries(
            reference_id=reference_id,
            curricular_year=curricular_year,
            period=period,
            credits=credits,
            website=request.website,
        )
        years = sorted({entry["unit"].curricular_year for entry in available_entries})
        credits_options = sorted({entry["unit"].credits for entry in available_entries})
        return request.render(
            "facodi_learning.curriculum_public_unit_index",
            {
                "references": references,
                "entries": entries,
                "years": years,
                "credits_options": credits_options,
                "selected_reference_id": reference_id,
                "selected_year": curricular_year,
                "selected_period": period,
                "selected_credits": credits,
                "has_available_units": bool(available_entries),
                "has_active_filters": bool(reference_id or curricular_year or period or credits is not None),
            },
        )

    @http.route(
        "/roadmaps/<int:reference_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def roadmap_detail(self, reference_id, **kwargs):
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
        show_learning_progress = not request.env.user._is_public()
        partner = request.env.user.partner_id if show_learning_progress else None
        unit_matrix_groups = reference._facodi_public_unit_matrix_by_period(
            website=website
        )
        for _year, period_groups in unit_matrix_groups:
            for _period, entries in period_groups:
                for entry in entries:
                    entry["learning"] = entry[
                        "unit"
                    ]._facodi_public_learning_projection(
                        website=website,
                        partner=partner,
                        viewer_env=request.env,
                    )
        flat_entries = [
            entry
            for _year, period_groups in unit_matrix_groups
            for _period, entries in period_groups
            for entry in entries
        ]
        roadmap_stats = {
            "units": len(flat_entries),
            "covered": len([entry for entry in flat_entries if entry["coverage_status"] == "covered"]),
            "partial": len([entry for entry in flat_entries if entry["coverage_status"] == "partial"]),
            "gaps": len([entry for entry in flat_entries if entry["coverage_status"] == "gap"]),
        }

        return request.render(
            "facodi_learning.curriculum_public_detail",
            {
                "reference": reference,
                "unit_groups": reference._facodi_public_units_grouped(),
                "unit_matrix_groups": unit_matrix_groups,
                "coverage_links": reference._facodi_public_coverage_links(
                    website=website
                ),
                "roadmap_stats": roadmap_stats,
            },
        )

    @http.route(
        "/curriculos/<int:reference_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def legacy_curriculum_detail(self, reference_id, **kwargs):
        return request.redirect("/roadmaps/%s" % reference_id, code=301)

    @http.route(
        "/roadmaps/<int:reference_id>/units/<path:unit_code>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def roadmap_unit_detail(self, reference_id, unit_code, **kwargs):
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

        return self._render_unit(reference, unit)

    @http.route(
        "/curriculos/<int:reference_id>/unidades/<path:unit_code>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def legacy_curriculum_unit_detail(self, reference_id, unit_code, **kwargs):
        return request.redirect(
            "/roadmaps/%s/units/%s" % (reference_id, unit_code), code=301
        )

    @http.route(
        "/unidades-curriculares/<int:reference_id>/<path:unit_slug>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def curriculum_unit_catalog_detail(self, reference_id, unit_slug, **kwargs):
        reference = self._public_references().filtered(lambda item: item.id == reference_id)
        if not reference:
            return request.not_found()
        unit = next(
            (
                candidate
                for candidate in request.env["facodi.learning.curriculum.unit"]
                .sudo()
                .search([("reference_id", "=", reference.id)])
                if candidate._facodi_public_catalog_path().rsplit("/", 1)[-1]
                == unit_slug
            ),
            False,
        )
        if not unit:
            return request.not_found()

        return self._render_unit(reference, unit)

    @http.route(
        "/modulos/<int:module_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def curriculum_module_detail(self, module_id, **kwargs):
        module = (
            request.env["facodi.learning.curriculum.module"]
            .sudo()
            .search([( "id", "=", module_id), ("website_published", "=", True)], limit=1)
        )
        if not module:
            return request.not_found()
        show_learning_progress = not request.env.user._is_public()
        return request.render(
            "facodi_learning.curriculum_public_module",
            {
                "module_row": module._facodi_public_projection(
                    website=request.website,
                    partner=request.env.user.partner_id if show_learning_progress else None,
                    viewer_env=request.env,
                ),
                "show_learning_progress": show_learning_progress,
            },
        )

    @staticmethod
    def _render_unit(reference, unit):
        coverage_rows = unit._facodi_public_coverage_rows(website=request.website)
        show_learning_progress = not request.env.user._is_public()
        learning = unit._facodi_public_learning_projection(
            website=request.website,
            partner=request.env.user.partner_id if show_learning_progress else None,
            viewer_env=request.env,
        )
        if any(row["coverage_status"] == "covered" for row in coverage_rows):
            coverage_status = "covered"
        elif coverage_rows:
            coverage_status = "partial"
        else:
            coverage_status = "gap"
        forum = False
        forum_url = "/forum"
        if "forum.forum" in request.env:
            forum = (
                request.env["forum.forum"]
                .sudo()
                .search([("website_id", "in", [False, request.website.id])], order="id", limit=1)
            )
            if forum:
                # Odoo 19 forum.forum does not expose website_url. Build the
                # canonical native Website Forum route with the same slug helper
                # used by forum.post.
                forum_url = "/forum/%s" % request.env["ir.http"]._slug(forum)

        return request.render(
            "facodi_learning.curriculum_public_unit",
            {
                "reference": reference,
                "unit": unit,
                "coverage_rows": coverage_rows,
                "coverage_status": coverage_status,
                "learning": learning,
                "show_learning_progress": show_learning_progress,
                "community_forum": forum,
                "community_forum_url": forum_url,
            },
        )
