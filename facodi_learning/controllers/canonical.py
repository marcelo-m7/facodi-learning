from odoo import http
from odoo.http import request
from odoo.addons.website.controllers.main import Website


class FacodiCanonicalRoutes(http.Controller):
    """Stable English entrypoints while preserving Odoo-native feature owners."""

    @http.route(
        "/courses",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def courses(self, **kwargs):
        # website_slides remains authoritative for search, enrolment and progress.
        query = request.httprequest.query_string.decode()
        target = "/slides"
        if query:
            target = f"{target}?{query}"
        return request.redirect(target, code=302)

    @http.route(
        "/unidades-curriculares",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def legacy_curricular_units(self, **kwargs):
        query = request.httprequest.query_string.decode()
        target = "/curricular-units"
        if query:
            target = f"{target}?{query}"
        return request.redirect(target, code=301)

    @http.route(
        "/unidades-curriculares/<int:reference_id>/<path:unit_slug>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def legacy_curricular_unit_detail(self, reference_id, unit_slug, **kwargs):
        return request.redirect(
            f"/curricular-units/{reference_id}/{unit_slug}",
            code=301,
        )


class FacodiWebsiteLogin(Website):
    """Keep native Odoo authentication and land portal users on My FACODI."""

    def _login_redirect(self, uid, redirect=None):
        if not redirect and request.params.get("login_success"):
            user = request.env["res.users"].browse(uid)
            if not user._is_internal():
                redirect = "/my/home"
        return super()._login_redirect(uid, redirect=redirect)
