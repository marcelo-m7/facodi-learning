from .course_selection import course_title_similarity


COVERAGE_STRENGTH = {
    "equivalent": 1.0,
    "covers": 1.0,
    "partial": 0.5,
    "supports": 0.25,
}


def coverage_strength_for_unit(unit):
    """Return the strongest approved FACODI coverage evidence for one unit."""
    unit.ensure_one()
    Coverage = unit.env["facodi.learning.curriculum.coverage"]
    approved = Coverage.search(
        [
            ("curriculum_unit_id", "=", unit.id),
            ("state", "=", "approved"),
        ]
    )
    strength = 0.0
    for coverage in approved:
        type_strength = COVERAGE_STRENGTH.get(coverage.coverage_type, 0.0)
        strength = max(strength, coverage.confidence * type_strength)
    return round(max(0.0, min(strength, 1.0)), 4)


def build_curriculum_selection_context(env):
    """Build a safe deterministic snapshot of enabled external curricula."""
    Reference = env["facodi.learning.curriculum.reference"]
    references = Reference.search(
        [("selection_enabled", "=", True)],
        order="institution, programme_name, academic_year desc, id",
    )
    if not references:
        return {
            "mode": "baseline",
            "reference_ids": [],
            "units": [],
        }

    units = []
    for reference in references:
        for unit in reference.unit_ids.sorted(key=lambda item: (item.sequence, item.id)):
            units.append(
                {
                    "unit_id": unit.id,
                    "reference_id": reference.id,
                    "programme": reference.programme_name,
                    "academic_year": reference.academic_year,
                    "external_unit_code": unit.external_unit_code or False,
                    "name": unit.name,
                    "approved_coverage_strength": coverage_strength_for_unit(unit),
                }
            )
    return {
        "mode": "curriculum-gap",
        "reference_ids": references.ids,
        "units": units,
    }


def score_candidate_curriculum_gap(candidate_name, context):
    """Score the uncovered gap of the curriculum unit most related to a candidate."""
    if not context or context.get("mode") != "curriculum-gap" or not context.get("units"):
        return {
            "score": 1.0,
            "evidence": {
                "mode": "baseline",
                "reference_ids": list((context or {}).get("reference_ids", [])),
            },
        }

    best = None
    best_key = None
    for unit in context["units"]:
        title_similarity = course_title_similarity(candidate_name or "", unit["name"] or "")
        coverage_strength = max(
            0.0,
            min(float(unit.get("approved_coverage_strength", 0.0) or 0.0), 1.0),
        )
        uncovered_gap = 1.0 - coverage_strength
        need = title_similarity * uncovered_gap
        # Relevance to the curriculum unit is primary. Coverage is considered only
        # after selecting the strongest semantic/title match, so an unrelated gap
        # cannot outrank a fully covered exact match. For equal matches across
        # references, prioritize the larger remaining gap deterministically.
        ranking_key = (title_similarity, need, -unit["unit_id"])
        if best is None or ranking_key > best_key:
            best_key = ranking_key
            best = {
                "unit": unit,
                "title_similarity": title_similarity,
                "coverage_strength": coverage_strength,
                "uncovered_gap": uncovered_gap,
                "need": need,
            }

    unit = best["unit"]
    score = round(max(0.0, min(best["need"], 1.0)), 4)
    evidence = {
        "mode": "curriculum-gap",
        "reference_ids": list(context.get("reference_ids", [])),
        "best_reference_id": unit["reference_id"],
        "best_programme": unit["programme"],
        "best_academic_year": unit["academic_year"],
        "best_unit_id": unit["unit_id"],
        "best_unit_code": unit["external_unit_code"],
        "best_unit_name": unit["name"],
        "title_similarity": round(best["title_similarity"], 4),
        "approved_coverage_strength": round(best["coverage_strength"], 4),
        "uncovered_gap": round(best["uncovered_gap"], 4),
    }
    return {"score": score, "evidence": evidence}
