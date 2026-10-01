import re
import unicodedata

from odoo.exceptions import AccessError, ValidationError

from .course_profile import COURSE_PROFILE_VERSION
from .course_selection import course_title_similarity


CURRICULUM_COVERAGE_RANKING_VERSION = "curriculum-coverage-ranking-v1"
CURRICULUM_COVERAGE_MIN_CONFIDENCE = 0.35
_CURRICULUM_COVERAGE_LOCK_NAMESPACE = 0x46414343  # FACC


def _tokens(value):
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 3
    }


def _course_search_text(profile):
    channel = profile.get("channel", {})
    values = [
        channel.get("name", ""),
        channel.get("description", ""),
        channel.get("short_description", ""),
        channel.get("detailed_description", ""),
    ]
    values.extend(tag.get("name", "") for tag in profile.get("course_tags", []))
    values.extend(section.get("name", "") for section in profile.get("sections", []))
    values.extend(content.get("name", "") for content in profile.get("contents", []))
    return " ".join(value for value in values if value)


def rank_course_curriculum_unit(channel, curriculum_unit):
    channel.ensure_one()
    curriculum_unit.ensure_one()
    channel.check_access("read")
    curriculum_unit.check_access("read")

    profile = channel._facodi_course_profile()
    title_similarity = course_title_similarity(
        curriculum_unit.name or "",
        profile.get("channel", {}).get("name", ""),
    )
    unit_tokens = _tokens(curriculum_unit.name)
    course_tokens = _tokens(_course_search_text(profile))
    token_recall = (
        len(unit_tokens & course_tokens) / len(unit_tokens)
        if unit_tokens
        else 0.0
    )

    confidence = round(
        0.65 * title_similarity + 0.35 * token_recall,
        4,
    )
    # Deterministic similarity is only proposal evidence. It never establishes
    # full curricular coverage or academic equivalence automatically.
    coverage_type = (
        "partial"
        if confidence >= 0.72 and token_recall >= 0.50
        else "supports"
    )
    signals = {
        "title_similarity": round(title_similarity, 4),
        "unit_token_recall": round(token_recall, 4),
    }
    return {
        "channel_id": channel.id,
        "curriculum_unit_id": curriculum_unit.id,
        "coverage_type": coverage_type,
        "confidence": confidence,
        "evaluation_version": CURRICULUM_COVERAGE_RANKING_VERSION,
        "evidence": {
            "ranking_version": CURRICULUM_COVERAGE_RANKING_VERSION,
            "course_profile_version": COURSE_PROFILE_VERSION,
            "signals": signals,
            "unit": {
                "external_unit_code": curriculum_unit.external_unit_code,
                "name": curriculum_unit.name,
                "reference_external_id": curriculum_unit.reference_id.external_id,
            },
            "course": {
                "channel_id": channel.id,
                "name": channel.name,
            },
            "boundary": (
                "Deterministic similarity is a review proposal only; it does not "
                "establish full curricular coverage, academic equivalence, or ECTS recognition."
            ),
        },
    }


def curriculum_coverage_candidates(curriculum_unit, limit=20):
    curriculum_unit.ensure_one()
    curriculum_unit.check_access("read")
    limit = max(0, int(limit or 0))
    if not limit:
        return []

    Channel = curriculum_unit.env["slide.channel"]
    channels = Channel.search(
        [
            ("active", "=", True),
            ("is_published", "=", True),
        ],
        order="sequence, id",
        limit=limit,
    )
    ranked = [
        rank_course_curriculum_unit(channel, curriculum_unit)
        for channel in channels
    ]
    return sorted(
        ranked,
        key=lambda item: (-item["confidence"], item["channel_id"]),
    )


def _lock_generation(curriculum_unit):
    curriculum_unit.ensure_one()
    curriculum_unit.env.cr.execute(
        "SELECT pg_try_advisory_xact_lock(%s, %s)",
        (_CURRICULUM_COVERAGE_LOCK_NAMESPACE, curriculum_unit.id),
    )
    if not curriculum_unit.env.cr.fetchone()[0]:
        raise ValidationError(
            "Curriculum coverage suggestion generation is already running for this unit. Please retry."
        )


def _check_manager(record):
    if not (
        record.env.is_superuser()
        or record.env.user.has_group("website_slides.group_website_slides_manager")
    ):
        raise AccessError(
            "Only eLearning Managers can generate curriculum coverage suggestions."
        )


def propose_curriculum_coverage(curriculum_unit, limit=20):
    curriculum_unit.ensure_one()
    _check_manager(curriculum_unit)
    curriculum_unit.check_access("read")
    _lock_generation(curriculum_unit)

    Coverage = curriculum_unit.env["facodi.learning.curriculum.coverage"]
    created = Coverage.browse()
    for candidate in curriculum_coverage_candidates(curriculum_unit, limit=limit):
        if candidate["confidence"] < CURRICULUM_COVERAGE_MIN_CONFIDENCE:
            continue

        # Identity for deterministic replay is course + curricular unit, not the
        # guessed coverage type. A prior proposal or terminal editorial decision
        # is authoritative and must never be duplicated/reopened by replay.
        existing = Coverage.search(
            [
                ("channel_id", "=", candidate["channel_id"]),
                ("curriculum_unit_id", "=", curriculum_unit.id),
            ],
            order="id",
            limit=1,
        )
        if existing:
            continue

        created |= Coverage._create_generated(candidate)
    return created


def propose_reference_curriculum_coverage(reference, limit_per_unit=20):
    reference.ensure_one()
    _check_manager(reference)
    proposals = reference.env["facodi.learning.curriculum.coverage"].browse()
    for unit in reference.unit_ids.sorted(key=lambda item: (item.sequence, item.id)):
        proposals |= propose_curriculum_coverage(unit, limit=limit_per_unit)
    return proposals
