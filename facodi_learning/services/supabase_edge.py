import json
import os
import urllib.error
import urllib.request

from odoo import tools


DEFAULT_FUNCTION = "v3_analyze_learning_resource"


def _env(name):
    return (os.environ.get(name) or "").strip()


def _analysis_endpoint():
    base = _env("SUPABASE_URL").rstrip("/")
    if not base:
        raise ValueError("SUPABASE_URL is not configured.")
    function = _env("FACODI_SUPABASE_ANALYSIS_FUNCTION") or DEFAULT_FUNCTION
    return f"{base}/functions/v1/{function}"


def analyze_supabase_edge(slide):
    """Delegate learning-resource enrichment and analysis to Supabase Edge Functions.

    The Odoo provider performs transport and contract validation only. It does not
    run provider-specific enrichment, classification, or AI inference.
    """

    slide.ensure_one()
    secret = _env("SUPABASE_SECRET_KEY")
    if not secret:
        raise ValueError("SUPABASE_SECRET_KEY is not configured.")

    source_url = (slide.url or "").strip()
    if not source_url:
        raise ValueError("Supabase analysis requires a public source URL.")

    job_id = slide.env.context.get("facodi_analysis_job_id")
    if not job_id:
        raise ValueError("Supabase analysis requires an Odoo analysis job context.")

    description = tools.html2plaintext(slide.description or "").strip()
    transcript = (slide.facodi_transcript or "").strip()
    provider_hint = "youtube" if slide.slide_type == "youtube_video" else "generic"

    payload = {
        "idempotency_key": f"odoo-analysis-job-{job_id}",
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
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", "replace")
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

    normalized = result.get("odoo_payload")
    if not isinstance(normalized, dict):
        raise ValueError("Supabase analysis response is missing the Odoo payload.")

    return normalized
