import logging

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from ..services.supabase_edge import discover_supabase_resource_metadata
from ..services.youtube import youtube_video_identity


_logger = logging.getLogger(__name__)


class FacodiSubmissionController(http.Controller):
    @staticmethod
    def _public_curriculum_unit(raw_id):
        try:
            unit_id = int(raw_id or 0)
        except (TypeError, ValueError):
            return request.env["facodi.learning.curriculum.unit"].browse()
        if unit_id <= 0:
            return request.env["facodi.learning.curriculum.unit"].browse()

        unit = (
            request.env["facodi.learning.curriculum.unit"]
            .sudo()
            .browse(unit_id)
            .exists()
        )
        if not unit or not unit._facodi_public_path():
            return request.env["facodi.learning.curriculum.unit"].browse()
        return unit

    @staticmethod
    def _form_values(
        values=None,
        errors=None,
        curriculum_unit=None,
        duplicate=False,
    ):
        return {
            "form_values": values or {},
            "errors": errors or [],
            "curriculum_unit": curriculum_unit,
            "duplicate": duplicate,
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
        curriculum_unit = self._public_curriculum_unit(
            kwargs.get("curriculum_unit_id")
        )
        values = {}
        if curriculum_unit:
            values["curriculum_unit_id"] = curriculum_unit.id
        return request.render(
            "facodi_learning.resource_submission_form",
            self._form_values(
                values=values,
                curriculum_unit=curriculum_unit,
            ),
        )

    @http.route(
        "/contribuir/recurso/metadata",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        sitemap=False,
        csrf=True,
    )
    def resource_submission_metadata(self, **post):
        source_url = (post.get("source_url") or "").strip()[:2048]
        Submission = request.env["facodi.learning.submission"]

        if not Submission._is_valid_source_url(source_url):
            return request.make_json_response(
                {
                    "success": False,
                    "supported": False,
                    "error": "invalid_source_url",
                },
                status=400,
            )

        # Keep the public discovery surface intentionally narrow. Generic URLs
        # remain valid submissions, but only recognized YouTube videos trigger
        # server-side network enrichment.
        identity = youtube_video_identity(source_url)
        if not identity:
            return request.make_json_response(
                {
                    "success": True,
                    "supported": False,
                    "provider": "generic",
                }
            )

        try:
            metadata = discover_supabase_resource_metadata(source_url)
        except Exception as exc:
            _logger.warning(
                "FACODI public metadata discovery failed (%s)",
                type(exc).__name__,
            )
            return request.make_json_response(
                {
                    "success": False,
                    "supported": True,
                    "provider": "youtube",
                    "error": "metadata_unavailable",
                },
                status=502,
            )

        response = request.make_json_response(
            {
                "success": True,
                **metadata,
            }
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

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
        raw_curriculum_unit_id = post.get("curriculum_unit_id")
        curriculum_unit = self._public_curriculum_unit(raw_curriculum_unit_id)

        youtube_identity = youtube_video_identity(source_url)
        if youtube_identity and (
            not name
            or not language
            or source_url != youtube_identity["source_url"]
        ):
            try:
                discovered = discover_supabase_resource_metadata(source_url)
            except Exception as exc:
                _logger.info(
                    "FACODI submission enrichment unavailable (%s)",
                    type(exc).__name__,
                )
            else:
                if discovered.get("supported"):
                    source_url = discovered.get("canonical_url") or source_url
                    name = name or (discovered.get("title") or "")
                    language = language or (discovered.get("language") or "")

        values = {
            "name": name,
            "source_url": source_url,
            "context": context,
            "language": language,
        }
        if curriculum_unit:
            values["curriculum_unit_id"] = curriculum_unit.id

        errors = []
        if not name:
            errors.append(request.env._("Enter a short title for the resource."))

        Submission = request.env["facodi.learning.submission"]
        if not Submission._is_valid_source_url(source_url):
            errors.append(request.env._("Enter a valid public HTTP or HTTPS URL."))

        if raw_curriculum_unit_id and not curriculum_unit:
            errors.append(
                request.env._(
                    "The curricular unit context is no longer publicly available."
                )
            )

        if errors:
            return request.render(
                "facodi_learning.resource_submission_form",
                self._form_values(
                    values=values,
                    errors=errors,
                    curriculum_unit=curriculum_unit,
                ),
            )

        normalized_source_url = Submission._normalize_source_url(source_url)
        duplicate_domain = [
            ("normalized_source_url", "=", normalized_source_url),
            ("state", "in", ("submitted", "reviewing", "accepted")),
        ]
        if curriculum_unit:
            duplicate_domain.append(
                ("curriculum_unit_id", "=", curriculum_unit.id)
            )
        else:
            duplicate_domain.append(("curriculum_unit_id", "=", False))

        duplicate = Submission.sudo().search(duplicate_domain, limit=1)
        if duplicate:
            return request.render(
                "facodi_learning.resource_submission_form",
                self._form_values(
                    values=values,
                    curriculum_unit=curriculum_unit,
                    duplicate=True,
                ),
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
                    curriculum_unit=curriculum_unit,
                    errors=[
                        request.env._(
                            "The resource could not be submitted. Check the URL and try again."
                        )
                    ],
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

        state_label = dict(
            submission._fields["state"]._description_selection(request.env)
        ).get(submission.state, submission.state)

        curriculum_unit = submission.curriculum_unit_id
        curriculum_unit_url = (
            curriculum_unit._facodi_public_path() if curriculum_unit else False
        )
        if not curriculum_unit_url:
            curriculum_unit = False

        response = request.render(
            "facodi_learning.resource_submission_status",
            {
                "submission": submission,
                "state_label": state_label,
                "curriculum_unit": curriculum_unit,
                "curriculum_unit_url": curriculum_unit_url,
            },
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
