from collections import OrderedDict
import threading
import time

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from ..services import discover_resource_metadata


_METADATA_CACHE_TTL_SECONDS = 15 * 60
_METADATA_CACHE_MAX_ITEMS = 256
_METADATA_MIN_INTERVAL_SECONDS = 1.5
_METADATA_CACHE = OrderedDict()
_METADATA_CACHE_LOCK = threading.Lock()
_METADATA_LOOKUP_SLOTS = threading.BoundedSemaphore(4)


def _metadata_cache_get(key):
    now = time.time()
    with _METADATA_CACHE_LOCK:
        cached = _METADATA_CACHE.get(key)
        if not cached:
            return False
        expires_at, metadata = cached
        if expires_at <= now:
            _METADATA_CACHE.pop(key, None)
            return False
        _METADATA_CACHE.move_to_end(key)
        return dict(metadata)


def _metadata_cache_put(keys, metadata):
    expires_at = time.time() + _METADATA_CACHE_TTL_SECONDS
    with _METADATA_CACHE_LOCK:
        for key in keys:
            if not key:
                continue
            _METADATA_CACHE[key] = (expires_at, dict(metadata))
            _METADATA_CACHE.move_to_end(key)
        while len(_METADATA_CACHE) > _METADATA_CACHE_MAX_ITEMS:
            _METADATA_CACHE.popitem(last=False)


class FacodiSubmissionController(http.Controller):
    _SUPPORTED_FORM_LANGUAGES = {"pt", "en", "es", "fr"}

    @classmethod
    def _supported_form_language(cls, value):
        normalized = (value or "").strip().lower().replace("_", "-")
        base = normalized.split("-", 1)[0]
        return base if base in cls._SUPPORTED_FORM_LANGUAGES else False

    @staticmethod
    def _metadata_rate_limited():
        now = time.time()
        try:
            last_request = float(
                request.session.get("facodi_resource_metadata_last_request", 0)
            )
        except (TypeError, ValueError):
            last_request = 0
        if last_request and now - last_request < _METADATA_MIN_INTERVAL_SECONDS:
            return True
        request.session["facodi_resource_metadata_last_request"] = now
        return False

    def _resource_metadata_response(self, Submission, metadata):
        canonical_url = metadata.get("canonical_url")
        if canonical_url and not Submission._is_valid_source_url(canonical_url):
            canonical_url = False

        language = self._supported_form_language(metadata.get("language"))
        available = bool(
            canonical_url
            or metadata.get("title")
            or metadata.get("author_name")
            or metadata.get("thumbnail_url")
            or language
        )
        return request.make_json_response(
            {
                "success": True,
                "available": available,
                "metadata": {
                    "provider": metadata.get("provider") or "generic",
                    "canonical_url": canonical_url,
                    "title": metadata.get("title") or False,
                    "author_name": metadata.get("author_name") or False,
                    "thumbnail_url": metadata.get("thumbnail_url") or False,
                    "duration_seconds": metadata.get("duration_seconds") or False,
                    "published_at": metadata.get("published_at") or False,
                    "language": language,
                },
                "message": (
                    request.env._("Resource details found.")
                    if available
                    else request.env._(
                        "No automatic details were found. Complete the fields manually."
                    )
                ),
            }
        )

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
        source_url = (post.get("source_url") or "").strip()
        Submission = request.env["facodi.learning.submission"]
        if len(source_url) > 2048 or not Submission._is_valid_source_url(source_url):
            return request.make_json_response(
                {
                    "success": False,
                    "message": request.env._(
                        "Enter a valid public HTTP or HTTPS URL."
                    ),
                },
                status=400,
            )

        cache_key = Submission._normalize_source_url(source_url)
        cached = _metadata_cache_get(cache_key)
        if cached:
            return self._resource_metadata_response(Submission, cached)

        if self._metadata_rate_limited():
            return request.make_json_response(
                {
                    "success": False,
                    "message": request.env._(
                        "Automatic details are temporarily unavailable. You can continue manually."
                    ),
                },
                headers=[("Retry-After", "2")],
                status=429,
            )

        if not _METADATA_LOOKUP_SLOTS.acquire(blocking=False):
            return request.make_json_response(
                {
                    "success": False,
                    "message": request.env._(
                        "Automatic details are temporarily unavailable. You can continue manually."
                    ),
                },
                headers=[("Retry-After", "2")],
                status=429,
            )

        try:
            metadata = discover_resource_metadata(source_url)
        except ValueError:
            return request.make_json_response(
                {
                    "success": False,
                    "message": request.env._(
                        "Automatic details are temporarily unavailable. You can continue manually."
                    ),
                },
                status=503,
            )
        finally:
            _METADATA_LOOKUP_SLOTS.release()

        canonical_url = metadata.get("canonical_url")
        canonical_key = (
            Submission._normalize_source_url(canonical_url)
            if canonical_url
            else False
        )
        _metadata_cache_put(
            {cache_key, canonical_key},
            metadata,
        )
        return self._resource_metadata_response(Submission, metadata)

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
