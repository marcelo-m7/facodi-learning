import re
import unicodedata


EVALUATION_POLICY_VERSION = "course-evaluation-v1"


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
