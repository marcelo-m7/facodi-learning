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
_FUNCTION_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _env(name):
    return (os.environ.get(name) or "").strip()


def _function_endpoint(function_env, default_function):
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

    function = _env(function_env) or default_function
    if not _FUNCTION_RE.fullmatch(function):
        raise ValueError("FACODI Supabase function name is invalid.")

    origin = urlunsplit(("https", parsed.netloc, "", "", "")).rstrip("/")
    return f"{origin}/functions/v1/{function}"


def _analysis_endpoint():
    return _function_endpoint(
        "FACODI_SUPABASE_ANALYSIS_FUNCTION",
        DEFAULT_FUNCTION,
    )


def _metadata_endpoint():
    return _function_endpoint(
        "FACODI_SUPABASE_METADATA_FUNCTION",
        DEFAULT_METADATA_FUNCTION,
    )


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "Supabase processing redirects are not allowed.",
            headers,
            fp,
        )


def _open_endpoint(request, timeout=60):
    opener = urllib.request.build_opener(_RejectRedirects())
    return opener.open(request, timeout=timeout)


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


def _read_json_response(request, *, timeout, operation):
    try:
        with _open_endpoint(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"{operation} returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"{operation} endpoint is unavailable.") from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{operation} returned invalid JSON.") from exc
    if not isinstance(result, dict) or result.get("success") is not True:
        raise ValueError(f"{operation} did not complete successfully.")
    return result


def _clean_metadata_text(value, limit):
    if not isinstance(value, str):
        return False
    value = value.strip()
    return value[:limit] if value else False


def discover_resource_metadata(source_url):
    """Return bounded public metadata for a submitted learning-resource URL.

    Odoo only proxies the request and validates the response contract. Provider-
    specific network discovery remains in the Supabase processing plane.
    """

    secret = _env("SUPABASE_SECRET_KEY")
    if not secret:
        raise ValueError("SUPABASE_SECRET_KEY is not configured.")

    source_url = (source_url or "").strip()
    if not source_url:
        raise ValueError("Resource metadata discovery requires a source URL.")

    request = urllib.request.Request(
        _metadata_endpoint(),
        data=json.dumps(
            {"source_url": source_url},
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "apikey": secret,
            "content-type": "application/json",
            "user-agent": "FACODI-Odoo/19 MetadataDiscovery",
        },
        method="POST",
    )
    result = _read_json_response(
        request,
        timeout=15,
        operation="Supabase metadata discovery",
    )
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Supabase metadata response is missing metadata.")

    duration = metadata.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        duration = False
    elif duration < 0 or duration > 604800:
        duration = False
    else:
        duration = int(duration)

    return {
        "provider": _clean_metadata_text(metadata.get("provider"), 32) or "generic",
        "external_id": _clean_metadata_text(metadata.get("external_id"), 128),
        "canonical_url": _clean_metadata_text(metadata.get("canonical_url"), 4096),
        "title": _clean_metadata_text(metadata.get("title"), 500),
        "author_name": _clean_metadata_text(metadata.get("author_name"), 300),
        "author_url": _clean_metadata_text(metadata.get("author_url"), 4096),
        "thumbnail_url": _clean_metadata_text(metadata.get("thumbnail_url"), 4096),
        "duration_seconds": duration,
        "published_at": _clean_metadata_text(metadata.get("published_at"), 64),
        "language": _clean_metadata_text(metadata.get("language"), 32),
        "metadata_source": _clean_metadata_text(
            metadata.get("metadata_source"),
            64,
        ),
    }


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

    result = _read_json_response(
        request,
        timeout=60,
        operation="Supabase analysis",
    )
    return _validate_response_correlation(result, idempotency_key)
