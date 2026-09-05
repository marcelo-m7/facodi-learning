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
        "transcript": transcript,
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


def normalize_output(payload, env):
    """Validate the provider boundary before recording any output or proposals."""
    import json

    if not isinstance(payload, dict):
        raise ValueError("Provider output must be an object")
    result = {}
    for key in ("summary", "transcript", "detected_language", "model_name"):
        value = payload.get(key) or False
        if value is not False and not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        result[key] = value
    tags = payload.get("suggested_tag_ids") or []
    if not isinstance(tags, list) or any(type(value) is not int for value in tags):
        raise ValueError("suggested_tag_ids must be integer IDs")
    records = env["slide.tag"].browse(tags).exists()
    records.check_access("read")
    if set(records.ids) != set(tags):
        raise ValueError("Unknown suggested tag")
    result["suggested_tag_ids"] = [(6, 0, records.ids)]
    names = payload.get("suggested_tags") or []
    if not isinstance(names, list) or any(
        not isinstance(name, str) or not name.strip() for name in names
    ):
        raise ValueError("suggested_tags must be nonempty names")
    result["suggested_tags"] = list(dict.fromkeys(name.strip() for name in names))
    proposals = payload.get("proposed_mappings") or []
    if not isinstance(proposals, list):
        raise ValueError("proposed_mappings must be a list")
    result["proposed_mappings"] = []
    for proposal in proposals:
        if (
            not isinstance(proposal, dict)
            or type(proposal.get("target_slide_id")) is not int
        ):
            raise ValueError("Mapping requires a target_slide_id")
        target = env["slide.slide"].browse(proposal["target_slide_id"]).exists()
        if not target:
            raise ValueError("Unknown mapping target")
        target.check_access("read")
        kind = proposal.get("mapping_type", "related")
        confidence = proposal.get("confidence", 0)
        if (
            kind not in ("related", "prerequisite", "recommended", "supports")
            or not isinstance(confidence, (float, int))
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Invalid mapping type or confidence")
        result["proposed_mappings"].append(
            dict(target_slide_id=target.id, mapping_type=kind, confidence=confidence)
        )
    result["raw_payload"] = payload.get("raw_payload") or {}
    json.dumps(result["raw_payload"], allow_nan=False)
    return result
