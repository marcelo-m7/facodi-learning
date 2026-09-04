from odoo import tools


def analyze_local_metadata(slide):
    """Return a deterministic normalized analysis using Odoo-owned metadata only.

    This provider intentionally performs no network access.  It is useful as the
    safe default, for tests, and as the normalized contract that future provider
    adapters must return.
    """
    slide.ensure_one()
    description = tools.html2plaintext(slide.description or "").strip()
    transcript = (slide.facodi_transcript or "").strip()
    text_parts = [part for part in (slide.name or "", description, transcript) if part]
    normalized_text = "\n\n".join(text_parts).strip()

    if normalized_text:
        summary = normalized_text[:1000]
    else:
        summary = slide.name or ""

    return {
        "summary": summary,
        "detected_language": False,
        "suggested_tag_ids": slide.tag_ids.ids,
        "model_name": "odoo_metadata",
        "raw_payload": {
            "source": "odoo",
            "slide_id": slide.id,
            "has_description": bool(description),
            "has_transcript": bool(transcript),
        },
    }
