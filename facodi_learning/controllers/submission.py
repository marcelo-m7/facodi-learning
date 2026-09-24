from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request


class FacodiSubmissionController(http.Controller):
    @staticmethod
    def _form_values(values=None, errors=None):
        return {
            "form_values": values or {},
            "errors": errors or [],
        }

    @http.route(
        "/contribuir/recurso",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=True,
    )
    def resource_submission_form(self, **kwargs):
        return request.render(
            "facodi_learning.resource_submission_form",
            self._form_values(),
        )

    @http.route(
        "/contribuir/recurso",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        sitemap=False,
        csrf=True,
    )
    def resource_submission_create(self, **post):
        name = (post.get("name") or "").strip()[:200]
        source_url = (post.get("source_url") or "").strip()[:2048]
        context = (post.get("context") or "").strip()[:4000]
        language = (post.get("language") or "").strip().lower()[:16]

        values = {
            "name": name,
            "source_url": source_url,
            "context": context,
            "language": language,
        }
        errors = []
        if not name:
            errors.append("Enter a short title for the resource.")
        Submission = request.env["facodi.learning.submission"]
        if not Submission._is_valid_source_url(source_url):
            errors.append("Enter a valid public HTTP or HTTPS URL.")

        if errors:
            return request.render(
                "facodi_learning.resource_submission_form",
                self._form_values(values=values, errors=errors),
            )

        if not request.env.user._is_public():
            values["submitted_by_id"] = request.env.user.id

        try:
            submission = Submission.sudo().create(values)
        except ValidationError:
            return request.render(
                "facodi_learning.resource_submission_form",
                self._form_values(
                    values=values,
                    errors=["The resource could not be submitted. Check the URL and try again."],
                ),
            )

        return request.redirect(
            "/contribuir/recurso/status/%s" % submission.access_token,
            code=303,
        )

    @http.route(
        "/contribuir/recurso/status/<string:access_token>",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def resource_submission_status(self, access_token, **kwargs):
        submission = (
            request.env["facodi.learning.submission"]
            .sudo()
            .search([("access_token", "=", access_token)], limit=1)
        )
        if not submission:
            return request.not_found()

        response = request.render(
            "facodi_learning.resource_submission_status",
            {"submission": submission},
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
