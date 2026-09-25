import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from odoo import tools


DEFAULT_FUNCTION = "v3_analyze_learning_resource"
DEFAULT_METADATA_FUNCTION = "v3_discover_resource_metadata"
MAX_ANALYSIS_RESPONSE_BYTES = 512 * 1024
MAX_METADATA_RESPONSE_BYTES = 64 * 1024
_FUNCTION_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _env(name):
    return (os.environ.get(name) or "").strip()


def _function_endpoint(function):
    raw = _env("SUPABASE_URL")
    if not raw:
        raise ValueError("SUPABASE_URL is not configured.")

    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("SUPABASE_URL is invalid.") from exc

    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or (port not in (None, 443))
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("SUPABASE_URL must be a credential-free HTTPS origin.")

    if not _FUNCTION_RE.fullmatch(function):
        raise ValueError("FACODI Supabase function name is invalid.")

    origin = urlunsplit(("https", parsed.netloc, "", "", "")).rstrip("/")
    return f"{origin}/functions/v1/{function}"


def _analysis_endpoint():
    function = _env("FACODI_SUPABASE_ANALYSIS_FUNCTION") or DEFAULT_FUNCTION
    return _function_endpoint(function)


def _metadata_endpoint():
    function = _env("FACODI_SUPABASE_METADATA_FUNCTION") or DEFAULT_METADATA_FUNCTION
    return _function_endpoint(function)


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "Supabase analysis redirects are not allowed.",
            headers,
            fp,
        )


def _open_endpoint(request, timeout=60):
    opener = urllib.request.build_opener(_RejectRedirects())
    return opener.open(request, timeout=timeout)


def _read_bounded_response(response, max_bytes):
    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("Supabase response exceeded the configured size limit.")
    return payload.decode("utf-8", "replace")


def _source_url_for_slide(slide):
    source_url = (slide.url or "").strip()
    if source_url:
        return source_url

    source = (
        slide.env["facodi.learning.source"]
        .search(
            [
                ("slide_id", "=", slide.id),
                ("state", "=", "imported"),
                ("url", "!=", False),
            ],
            order="id desc",
            limit=1,
        )
    )
    return (source.url or "").strip() if source else ""


def _validate_response_correlation(result, idempotency_key):
    job_id = result.get("job_id")
    status = result.get("status")
    if not isinstance(job_id, str):
        raise ValueError("Supabase analysis response is missing its job identifier.")
    try:
        UUID(job_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Supabase analysis returned an invalid job identifier.") from exc
    if status not in {"completed", "needs_review"}:
        raise ValueError("Supabase analysis returned an invalid terminal status.")

    normalized = result.get("odoo_payload")
    if not isinstance(normalized, dict):
        raise ValueError("Supabase analysis response is missing the Odoo payload.")

    raw_payload = normalized.get("raw_payload")
    if not isinstance(raw_payload, dict):
        raise ValueError("Supabase analysis response is missing correlation evidence.")
    if raw_payload.get("processing_job_id") != job_id:
        raise ValueError("Supabase analysis job correlation does not match.")
    if raw_payload.get("idempotency_key") != idempotency_key:
        raise ValueError("Supabase analysis idempotency correlation does not match.")
    if raw_payload.get("source") != "supabase_edge":
        raise ValueError("Supabase analysis source correlation does not match.")

    return normalized


def analyze_supabase_edge(slide):
    """Delegate learning-resource enrichment and analysis to Supabase Edge Functions.

    The Odoo provider performs transport and contract validation only. It does not
    run provider-specific enrichment, classification, or AI inference.
    """

    slide.ensure_one()
    secret = _env("SUPABASE_SECRET_KEY")
    if not secret:
        raise ValueError("SUPABASE_SECRET_KEY is not configured.")

    source_url = _source_url_for_slide(slide)
    if not source_url:
        raise ValueError("Supabase analysis requires a public source URL.")

    job_id = slide.env.context.get("facodi_analysis_job_id")
    if not job_id:
        raise ValueError("Supabase analysis requires an Odoo analysis job context.")

    description = tools.html2plaintext(slide.description or "").strip()
    transcript = (slide.facodi_transcript or "").strip()
    provider_hint = "youtube" if slide.slide_type == "youtube_video" else "generic"
    idempotency_key = f"odoo-analysis-job-{job_id}"

    payload = {
        "idempotency_key": idempotency_key,
        "source_url": source_url,
        "provider_hint": provider_hint,
        "odoo": {
            "model": "slide.slide",
            "res_id": slide.id,
            "analysis_job_id": job_id,
            "slide_id": slide.id,
            "channel_id": slide.channel_id.id,
            "title": slide.name or "",
            "description": description,
            "transcript": transcript,
        },
    }

    headers = {
        "apikey": secret,
        "content-type": "application/json",
        "user-agent": "FACODI-Odoo/19 SupabaseAnalysis",
    }
    gemini_key = _env("GEMINI_API_KEY")
    if gemini_key:
        headers["x-facodi-gemini-key"] = gemini_key

    request = urllib.request.Request(
        _analysis_endpoint(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with _open_endpoint(request, timeout=60) as response:
            raw = _read_bounded_response(response, MAX_ANALYSIS_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        # Do not propagate response bodies: provider responses can contain
        # operational details that should stay out of Odoo user-facing errors.
        raise ValueError(f"Supabase analysis returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ValueError("Supabase analysis endpoint is unavailable.") from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Supabase analysis returned invalid JSON.") from exc

    if not isinstance(result, dict) or result.get("success") is not True:
        raise ValueError("Supabase analysis did not complete successfully.")

    return _validate_response_correlation(result, idempotency_key)


def discover_supabase_resource_metadata(source_url):
    """Return public-safe metadata discovered by the Supabase processing plane."""

    secret = _env("SUPABASE_SECRET_KEY")
    if not secret:
        raise ValueError("SUPABASE_SECRET_KEY is not configured.")

    value = (source_url or "").strip()
    if not value:
        raise ValueError("Metadata discovery requires a public source URL.")

    request = urllib.request.Request(
        _metadata_endpoint(),
        data=json.dumps({"source_url": value}, ensure_ascii=False).encode("utf-8"),
        headers={
            "apikey": secret,
            "content-type": "application/json",
            "user-agent": "FACODI-Odoo/19 MetadataDiscovery",
        },
        method="POST",
    )

    try:
        with _open_endpoint(request, timeout=15) as response:
            raw = _read_bounded_response(response, MAX_METADATA_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Supabase metadata discovery returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ValueError("Supabase metadata discovery endpoint is unavailable.") from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Supabase metadata discovery returned invalid JSON.") from exc

    if not isinstance(result, dict) or result.get("success") is not True:
        raise ValueError("Supabase metadata discovery did not complete successfully.")

    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Supabase metadata discovery response is missing metadata.")

    provider = metadata.get("provider")
    if provider != "youtube":
        return {
            "supported": False,
            "provider": provider or "generic",
        }

    canonical_url = metadata.get("canonical_url")
    title = metadata.get("title")
    language = metadata.get("language")
    author_name = metadata.get("author_name")
    thumbnail_url = metadata.get("thumbnail_url")
    duration_seconds = metadata.get("duration_seconds")

    if not isinstance(canonical_url, str) or not canonical_url.startswith(
        "https://www.youtube.com/watch?v="
    ):
        raise ValueError("Supabase metadata discovery returned an invalid YouTube URL.")

    return {
        "supported": True,
        "provider": "youtube",
        "external_id": metadata.get("external_id"),
        "canonical_url": canonical_url[:2048],
        "title": title[:200] if isinstance(title, str) else False,
        "language": language[:16] if isinstance(language, str) else False,
        "author_name": author_name[:300] if isinstance(author_name, str) else False,
        "thumbnail_url": thumbnail_url[:2048]
        if isinstance(thumbnail_url, str) and thumbnail_url.startswith("https://")
        else False,
        "duration_seconds": duration_seconds
        if isinstance(duration_seconds, int) and duration_seconds >= 0
        else False,
        "published_at": metadata.get("published_at")
        if isinstance(metadata.get("published_at"), str)
        else False,
    }
