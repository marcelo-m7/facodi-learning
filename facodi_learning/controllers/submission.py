import logging
import threading
import time
from collections import OrderedDict

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from ..services.supabase_edge import discover_supabase_resource_metadata
from ..services.youtube import youtube_video_identity


_logger = logging.getLogger(__name__)

_METADATA_CACHE_MAX = 256
_METADATA_CACHE_TTL = 900
_METADATA_RATE_WINDOW = 60
_METADATA_RATE_PER_CLIENT = 12
_METADATA_RATE_GLOBAL = 60
_METADATA_RATE_CLIENTS_MAX = 2048
_metadata_lock = threading.Lock()
_metadata_cache = OrderedDict()
_metadata_rate = OrderedDict()


class MetadataDiscoveryRateLimited(Exception):
    pass


def _metadata_cache_get(key, now=None):
    now = time.monotonic() if now is None else now
    with _metadata_lock:
        entry = _metadata_cache.get(key)
        if not entry:
            return False
        expires_at, payload = entry
        if expires_at <= now:
            _metadata_cache.pop(key, None)
            return False
        _metadata_cache.move_to_end(key)
        return dict(payload)


def _metadata_cache_set(key, payload, now=None):
    now = time.monotonic() if now is None else now
    with _metadata_lock:
        _metadata_cache[key] = (now + _METADATA_CACHE_TTL, dict(payload))
        _metadata_cache.move_to_end(key)
        while len(_metadata_cache) > _METADATA_CACHE_MAX:
            _metadata_cache.popitem(last=False)


def _consume_metadata_budget(client_key, now=None):
    now = time.monotonic() if now is None else now
    client_key = client_key or "unknown"

    def consume(key, limit):
        timestamps = _metadata_rate.get(key, [])
        cutoff = now - _METADATA_RATE_WINDOW
        timestamps = [stamp for stamp in timestamps if stamp > cutoff]
        if len(timestamps) >= limit:
            _metadata_rate[key] = timestamps
            _metadata_rate.move_to_end(key)
            return False
        timestamps.append(now)
        _metadata_rate[key] = timestamps
        _metadata_rate.move_to_end(key)
        return True

    with _metadata_lock:
        if not consume("__global__", _METADATA_RATE_GLOBAL):
            return False
        if not consume(f"client:{client_key}", _METADATA_RATE_PER_CLIENT):
            # Roll back the global token consumed above.
            global_stamps = _metadata_rate.get("__global__", [])
            if global_stamps and global_stamps[-1] == now:
                global_stamps.pop()
            return False
        while len(_metadata_rate) > _METADATA_RATE_CLIENTS_MAX + 1:
            first_key = next(iter(_metadata_rate))
            if first_key == "__global__":
                _metadata_rate.move_to_end(first_key)
                continue
            _metadata_rate.popitem(last=False)
        return True


def _discover_public_youtube_metadata(source_url):
    identity = youtube_video_identity(source_url)
    if not identity:
        return False

    cache_key = identity["source_url"]
    cached = _metadata_cache_get(cache_key)
    if cached:
        return cached

    client_key = request.httprequest.remote_addr or "unknown"
    if not _consume_metadata_budget(client_key):
        raise MetadataDiscoveryRateLimited()

    metadata = discover_supabase_resource_metadata(cache_key)
    if metadata.get("supported"):
        _metadata_cache_set(cache_key, metadata)
    return metadata


class FacodiSubmissionController(http.Controller):
    @staticmethod
    def _owned_submission(raw_id):
        try:
            submission_id = int(raw_id or 0)
        except (TypeError, ValueError):
            return request.env["facodi.learning.submission"].browse()
        if submission_id <= 0 or request.env.user._is_public():
            return request.env["facodi.learning.submission"].browse()
        return (
            request.env["facodi.learning.submission"]
            .sudo()
            .search(
                [
                    ("id", "=", submission_id),
                    ("submitted_by_id", "=", request.env.user.id),
                ],
                limit=1,
            )
        )

    @staticmethod
    def _submission_state_label(submission):
        return dict(
            submission._fields["state"]._description_selection(request.env)
        ).get(submission.state, submission.state)

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
        if not youtube_video_identity(source_url):
            return request.make_json_response(
                {
                    "success": True,
                    "supported": False,
                    "provider": "generic",
                }
            )

        try:
            metadata = _discover_public_youtube_metadata(source_url)
        except MetadataDiscoveryRateLimited:
            response = request.make_json_response(
                {
                    "success": False,
                    "supported": True,
                    "provider": "youtube",
                    "error": "rate_limited",
                },
                status=429,
            )
            response.headers["Retry-After"] = str(_METADATA_RATE_WINDOW)
            response.headers["Cache-Control"] = "no-store"
            return response
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
        Submission = request.env["facodi.learning.submission"]

        youtube_identity = (
            youtube_video_identity(source_url)
            if Submission._is_valid_source_url(source_url)
            else False
        )
        if youtube_identity and (
            not name
            or not language
            or source_url != youtube_identity["source_url"]
        ):
            try:
                discovered = _discover_public_youtube_metadata(source_url)
            except MetadataDiscoveryRateLimited:
                discovered = False
            except Exception as exc:
                _logger.info(
                    "FACODI submission enrichment unavailable (%s)",
                    type(exc).__name__,
                )
                discovered = False

            if discovered and discovered.get("supported"):
                source_url = discovered.get("canonical_url") or source_url
                name = name or (discovered.get("title") or "")
                detected_language = (discovered.get("language") or "").lower()
                detected_language = detected_language.replace("_", "-").split("-", 1)[0]
                language = language or detected_language[:16]

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

    @http.route(
        "/minhas-contribuicoes",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def my_submissions(self, **kwargs):
        submissions = (
            request.env["facodi.learning.submission"]
            .sudo()
            .search(
                [("submitted_by_id", "=", request.env.user.id)],
                order="create_date desc, id desc",
            )
        )
        rows = [
            {
                "submission": submission,
                "state_label": self._submission_state_label(submission),
                "can_edit": submission.state == "submitted",
                "can_withdraw": submission.state in {"submitted", "reviewing"},
            }
            for submission in submissions
        ]
        response = request.render(
            "facodi_learning.resource_submission_my_list",
            {"rows": rows},
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @http.route(
        "/minhas-contribuicoes/<int:submission_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def my_submission_detail(self, submission_id, **kwargs):
        submission = self._owned_submission(submission_id)
        if not submission:
            return request.not_found()
        response = request.render(
            "facodi_learning.resource_submission_manage",
            {
                "submission": submission,
                "state_label": self._submission_state_label(submission),
                "can_edit": submission.state == "submitted",
                "can_withdraw": submission.state in {"submitted", "reviewing"},
                "errors": [],
                "form_values": {},
            },
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @http.route(
        "/minhas-contribuicoes/<int:submission_id>/editar",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        sitemap=False,
        csrf=True,
    )
    def my_submission_edit(self, submission_id, **post):
        submission = self._owned_submission(submission_id)
        if not submission:
            return request.not_found()

        values = {
            "name": (post.get("name") or "").strip()[:200],
            "source_url": (post.get("source_url") or "").strip()[:2048],
            "context": (post.get("context") or "").strip()[:4000],
            "language": (post.get("language") or "").strip().lower()[:16],
        }
        errors = []
        if not values["name"]:
            errors.append(request.env._("Enter a short title for the resource."))
        if not request.env["facodi.learning.submission"]._is_valid_source_url(
            values["source_url"]
        ):
            errors.append(request.env._("Enter a valid public HTTP or HTTPS URL."))

        normalized_source_url = (
            request.env["facodi.learning.submission"]._normalize_source_url(
                values["source_url"]
            )
        )
        if not errors:
            duplicate = (
                request.env["facodi.learning.submission"]
                .sudo()
                .search(
                    [
                        ("id", "!=", submission.id),
                        ("normalized_source_url", "=", normalized_source_url),
                        ("state", "in", ("submitted", "reviewing", "accepted")),
                        ("curriculum_unit_id", "=", submission.curriculum_unit_id.id or False),
                    ],
                    limit=1,
                )
            )
            if duplicate:
                errors.append(
                    request.env._(
                        "This resource is already under editorial review for this context."
                    )
                )

        if not errors:
            try:
                submission.action_update_by_contributor(request.env.user, values)
            except ValidationError as exc:
                errors.append(str(exc))

        if errors:
            response = request.render(
                "facodi_learning.resource_submission_manage",
                {
                    "submission": submission,
                    "state_label": self._submission_state_label(submission),
                    "can_edit": submission.state == "submitted",
                    "can_withdraw": submission.state in {"submitted", "reviewing"},
                    "errors": errors,
                    "form_values": values,
                },
            )
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            return response

        return request.redirect(
            f"/minhas-contribuicoes/{submission.id}?updated=1",
            code=303,
        )

    @http.route(
        "/minhas-contribuicoes/<int:submission_id>/retirar",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        sitemap=False,
        csrf=True,
    )
    def my_submission_withdraw(self, submission_id, **post):
        submission = self._owned_submission(submission_id)
        if not submission:
            return request.not_found()
        try:
            submission.action_withdraw_by_contributor(request.env.user)
        except ValidationError:
            return request.redirect(
                f"/minhas-contribuicoes/{submission.id}?withdraw_error=1",
                code=303,
            )
        return request.redirect("/minhas-contribuicoes?withdrawn=1", code=303)
