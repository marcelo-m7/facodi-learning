from odoo import SUPERUSER_ID


COURSE_MAPPING_POLICY_VERSION = "course-mapping-policy-v1"
DEFAULT_MIN_CONFIDENCE = 0.85
SAFE_AUTO_TYPES = {"related", "complements"}
VALID_MODES = {"manual", "assisted", "auto"}


def _bounded_float(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(value, 1.0))


def get_course_mapping_policy(env):
    params = env["ir.config_parameter"].sudo()

    mode = (
        params.get_param("facodi_learning.course_mapping_mode", "manual")
        or "manual"
    ).strip()
    if mode not in VALID_MODES:
        mode = "manual"

    raw_types = params.get_param(
        "facodi_learning.course_mapping_auto_types", "related"
    )
    requested_types = {
        item.strip()
        for item in (raw_types or "").split(",")
        if item.strip()
    }
    auto_types = requested_types & SAFE_AUTO_TYPES

    min_confidence = _bounded_float(
        params.get_param(
            "facodi_learning.course_mapping_min_confidence",
            str(DEFAULT_MIN_CONFIDENCE),
        ),
        DEFAULT_MIN_CONFIDENCE,
    )

    return {
        "policy_version": COURSE_MAPPING_POLICY_VERSION,
        "mode": mode,
        "auto_types": auto_types,
        "min_confidence": min_confidence,
    }


def is_course_mapping_auto_eligible(mapping, policy):
    mapping.ensure_one()
    is_manager = mapping.env.uid == SUPERUSER_ID or mapping.env.user.has_group(
        "website_slides.group_website_slides_manager"
    )
    return bool(
        is_manager
        and policy.get("mode") == "auto"
        and mapping.state == "proposed"
        and mapping.mapping_type != "prerequisite"
        and mapping.mapping_type in policy.get("auto_types", set())
        and mapping.confidence >= policy.get("min_confidence", 1.0)
    )
