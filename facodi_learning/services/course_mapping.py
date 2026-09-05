from ..services.course_profile import COURSE_PROFILE_VERSION
from ..services.course_selection import course_title_similarity


COURSE_MAPPING_RANKING_VERSION = "course-mapping-v1"
PROPOSAL_MIN_CONFIDENCE = 0.50


def _jaccard(left, right):
    left = set(left or [])
    right = set(right or [])
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)


def _language_compatibility(source_profile, target_profile):
    source_languages = set(
        source_profile.get("analysis", {}).get("detected_languages", []) or []
    )
    target_languages = set(
        target_profile.get("analysis", {}).get("detected_languages", []) or []
    )
    if not source_languages or not target_languages:
        return 1.0
    return 1.0 if source_languages & target_languages else 0.0


def _duration_similarity(source_profile, target_profile):
    source_duration = float(
        source_profile.get("structure", {}).get("total_duration", 0.0) or 0.0
    )
    target_duration = float(
        target_profile.get("structure", {}).get("total_duration", 0.0) or 0.0
    )
    if source_duration <= 0 or target_duration <= 0:
        return 0.5
    return 1.0 - min(
        abs(source_duration - target_duration) / max(source_duration, target_duration),
        1.0,
    )


def retrieve_course_candidates(source_channel, limit=20):
    source_channel.ensure_one()
    source_channel.check_access("read")
    limit = max(0, int(limit or 0))
    if not limit:
        return source_channel.env["slide.channel"]

    domain = [
        ("id", "!=", source_channel.id),
        ("active", "=", True),
    ]
    if source_channel.website_id:
        domain.extend(
            [
                "|",
                ("website_id", "=", False),
                ("website_id", "=", source_channel.website_id.id),
            ]
        )
    return source_channel.env["slide.channel"].search(
        domain,
        order="sequence, id",
        limit=limit,
    )


def rank_course_pair(source_profile, target_profile):
    source_tags = [tag["id"] for tag in source_profile.get("course_tags", [])]
    target_tags = [tag["id"] for tag in target_profile.get("course_tags", [])]

    title_overlap = course_title_similarity(
        source_profile.get("channel", {}).get("name", ""),
        target_profile.get("channel", {}).get("name", ""),
    )
    tag_overlap = _jaccard(source_tags, target_tags)
    language_compatibility = _language_compatibility(source_profile, target_profile)
    duration_similarity = _duration_similarity(source_profile, target_profile)

    signals = {
        "title_overlap": round(title_overlap, 4),
        "tag_overlap": round(tag_overlap, 4),
        "language_compatibility": round(language_compatibility, 4),
        "duration_similarity": round(duration_similarity, 4),
    }
    confidence = round(
        0.30 * title_overlap
        + 0.40 * tag_overlap
        + 0.20 * language_compatibility
        + 0.10 * duration_similarity,
        4,
    )
    reasons = [
        f"Title overlap: {signals['title_overlap']:.4f}",
        f"Course-tag overlap: {signals['tag_overlap']:.4f}",
        f"Language compatibility: {signals['language_compatibility']:.4f}",
        f"Duration similarity: {signals['duration_similarity']:.4f}",
    ]
    return {
        "signals": signals,
        "confidence": confidence,
        "mapping_type": "related",
        "ranking_version": COURSE_MAPPING_RANKING_VERSION,
        "reasons": reasons,
    }


def course_mapping_candidates(source_channel, limit=20):
    source_channel.ensure_one()
    source_profile = source_channel._facodi_course_profile()
    ranked = []
    for target in retrieve_course_candidates(source_channel, limit=limit):
        result = rank_course_pair(source_profile, target._facodi_course_profile())
        ranked.append(
            {
                "target_channel_id": target.id,
                **result,
            }
        )
    return sorted(
        ranked,
        key=lambda item: (-item["confidence"], item["target_channel_id"]),
    )


def propose_course_mappings(source_channel, limit=20):
    source_channel.ensure_one()
    source_channel.check_access("read")
    source_channel.check_access("write")
    Mapping = source_channel.env["facodi.learning.course.mapping"]
    proposals = Mapping.browse()

    for candidate in course_mapping_candidates(source_channel, limit=limit):
        if candidate["confidence"] < PROPOSAL_MIN_CONFIDENCE:
            continue
        domain = [
            ("source_channel_id", "=", source_channel.id),
            ("target_channel_id", "=", candidate["target_channel_id"]),
            ("mapping_type", "=", candidate["mapping_type"]),
        ]
        mapping = Mapping.search(domain, limit=1)
        if not mapping:
            mapping = Mapping._create_generated(
                {
                    "source_channel_id": source_channel.id,
                    "target_channel_id": candidate["target_channel_id"],
                    "mapping_type": candidate["mapping_type"],
                    "confidence": candidate["confidence"],
                    "evidence": {
                        "signals": candidate["signals"],
                        "reasons": candidate["reasons"],
                        "source_profile_version": COURSE_PROFILE_VERSION,
                    },
                    "ranking_version": candidate["ranking_version"],
                }
            )
        if mapping.origin == "analysis" and mapping.state == "proposed":
            mapping._maybe_auto_approve()
            mapping.invalidate_recordset()
        proposals |= mapping
    return proposals
