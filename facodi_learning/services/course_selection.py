import re
import unicodedata


EVALUATION_POLICY_VERSION = "course-evaluation-v1"
SELECTION_POLICY_VERSION = "course-selection-v1"

_SELECTION_DEFAULTS = {
    "mode": "manual",
    "min_relevance": 0.80,
    "min_metadata_quality": 0.70,
    "min_language_fit": 0.90,
    "min_coverage": 0.65,
    "max_duplication_risk": 0.30,
    "languages": "pt,en",
    "trusted_providers": "manual",
}


def normalize_course_title(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def course_title_similarity(left, right):
    left_tokens = set(normalize_course_title(left).split())
    right_tokens = set(normalize_course_title(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    if left_tokens == right_tokens:
        return 1.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _normalized_identifier_set(value, default):
    raw = value if value is not None else default
    return {
        item.strip().lower()
        for item in str(raw).split(",")
        if item and item.strip()
    }


def _normalized_threshold(value, default):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    return max(0.0, min(parsed, 1.0))


def get_course_selection_policy(env):
    parameters = env["ir.config_parameter"].sudo()
    mode = parameters.get_param(
        "facodi_learning.course_selection_mode", _SELECTION_DEFAULTS["mode"]
    )
    if mode not in {"manual", "assisted", "auto"}:
        mode = "manual"

    return {
        "mode": mode,
        "min_relevance": _normalized_threshold(
            parameters.get_param(
                "facodi_learning.auto_approve_min_relevance",
                str(_SELECTION_DEFAULTS["min_relevance"]),
            ),
            _SELECTION_DEFAULTS["min_relevance"],
        ),
        "min_metadata_quality": _normalized_threshold(
            parameters.get_param(
                "facodi_learning.auto_approve_min_metadata_quality",
                str(_SELECTION_DEFAULTS["min_metadata_quality"]),
            ),
            _SELECTION_DEFAULTS["min_metadata_quality"],
        ),
        "min_language_fit": _normalized_threshold(
            parameters.get_param(
                "facodi_learning.auto_approve_min_language_fit",
                str(_SELECTION_DEFAULTS["min_language_fit"]),
            ),
            _SELECTION_DEFAULTS["min_language_fit"],
        ),
        "min_coverage": _normalized_threshold(
            parameters.get_param(
                "facodi_learning.auto_approve_min_coverage",
                str(_SELECTION_DEFAULTS["min_coverage"]),
            ),
            _SELECTION_DEFAULTS["min_coverage"],
        ),
        "max_duplication_risk": _normalized_threshold(
            parameters.get_param(
                "facodi_learning.auto_approve_max_duplication_risk",
                str(_SELECTION_DEFAULTS["max_duplication_risk"]),
            ),
            _SELECTION_DEFAULTS["max_duplication_risk"],
        ),
        "languages": _normalized_identifier_set(
            parameters.get_param(
                "facodi_learning.course_selection_languages",
                _SELECTION_DEFAULTS["languages"],
            ),
            _SELECTION_DEFAULTS["languages"],
        ),
        "trusted_providers": _normalized_identifier_set(
            parameters.get_param(
                "facodi_learning.auto_approve_trusted_providers",
                _SELECTION_DEFAULTS["trusted_providers"],
            ),
            _SELECTION_DEFAULTS["trusted_providers"],
        ),
        "policy_version": SELECTION_POLICY_VERSION,
    }


def candidate_is_auto_approve_eligible(candidate, policy):
    reasons = []
    if policy.get("mode") != "auto":
        reasons.append("Course selection mode is not Auto Approve.")
    if (candidate.provider or "").strip().lower() not in policy.get(
        "trusted_providers", set()
    ):
        reasons.append("Candidate provider is not trusted for Auto Approve.")
    if candidate.state in {"approved", "rejected", "resolved"}:
        reasons.append("Candidate has already reached a terminal decision state.")
    if candidate.recommendation in {"review_existing_match", "ignore"}:
        reasons.append(
            "Candidate recommendation requires review or exclusion before approval."
        )
    if candidate.relevance_score < policy["min_relevance"]:
        reasons.append("Relevance score is below the Auto Approve minimum.")
    if candidate.metadata_quality_score < policy["min_metadata_quality"]:
        reasons.append("Metadata quality score is below the Auto Approve minimum.")
    if candidate.language_fit_score < policy["min_language_fit"]:
        reasons.append("Language fit score is below the Auto Approve minimum.")
    if candidate.coverage_score < policy["min_coverage"]:
        reasons.append("Coverage score is below the Auto Approve minimum.")
    if candidate.duplication_risk > policy["max_duplication_risk"]:
        reasons.append("Duplicate risk exceeds the Auto Approve maximum.")
    return not reasons, reasons


def evaluate_course_candidate(candidate, existing_channels, accepted_languages):
    accepted_languages = {
        str(language).strip().lower()
        for language in (accepted_languages or ())
        if str(language).strip()
    }

    metadata_fields = (
        candidate.name,
        candidate.description,
        candidate.institution,
        candidate.language,
        candidate.level,
        candidate.duration_minutes,
    )
    metadata_quality = sum(bool(value) for value in metadata_fields) / len(
        metadata_fields
    )

    relevance = (
        1.0
        if candidate.provider == "manual"
        else 0.5 * metadata_quality + 0.5 * bool(candidate.description)
    )

    language = (candidate.language or "").strip().lower()
    language_fit = (
        1.0
        if language and language in accepted_languages
        else 0.5
        if not language
        else 0.0
    )

    # M3.1 has no external curriculum reference yet. M3.4 will replace this
    # neutral/full local baseline with curriculum-aware evidence.
    coverage = 1.0

    best_channel = None
    duplication_risk = 0.0
    for channel in existing_channels:
        similarity = course_title_similarity(candidate.name, channel.name)
        if similarity > duplication_risk:
            duplication_risk = similarity
            best_channel = channel

    matched_channel_id = (
        best_channel.id if best_channel and duplication_risk >= 0.5 else False
    )

    if duplication_risk >= 0.8:
        recommendation = "review_existing_match"
    elif relevance < 0.4:
        recommendation = "ignore"
    elif relevance >= 0.7 and language_fit >= 0.7:
        recommendation = "shortlist"
    else:
        recommendation = "review"

    present_count = sum(bool(value) for value in metadata_fields)
    reasons = [
        f"{present_count} of {len(metadata_fields)} baseline metadata fields are available.",
        (
            f"Language {language} is accepted by the current local policy."
            if language and language_fit == 1.0
            else "Language is not supplied; the local baseline uses a neutral fit."
            if not language
            else f"Language {language} is outside the currently accepted set."
        ),
        "No curriculum reference is active in M3.1; coverage uses the local baseline.",
    ]
    if best_channel and duplication_risk >= 0.5:
        reasons.append(
            f"Possible existing course match: {best_channel.name} "
            f"({duplication_risk:.4f} title similarity)."
        )
    else:
        reasons.append("No strong existing-course title match was found.")

    return {
        "relevance_score": round(float(relevance), 4),
        "metadata_quality_score": round(float(metadata_quality), 4),
        "language_fit_score": round(float(language_fit), 4),
        "coverage_score": round(float(coverage), 4),
        "duplication_risk": round(float(duplication_risk), 4),
        "matched_channel_id": matched_channel_id,
        "recommendation": recommendation,
        "reasons": reasons,
        "policy_version": EVALUATION_POLICY_VERSION,
    }
