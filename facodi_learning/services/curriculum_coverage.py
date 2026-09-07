from .course_selection import course_title_similarity


CURRICULUM_COVERAGE_VERSION = "curriculum-coverage-v1"
COVERAGE_STRENGTH = {
    "equivalent": 1.0,
    "covers": 1.0,
    "partial": 0.5,
    "supports": 0.25,
}


def build_curriculum_unit_coverage(unit):
    """Return approved coverage evidence for one external curriculum unit."""
    unit.ensure_one()
    unit.check_access("read")
    Coverage = unit.env["facodi.learning.curriculum.coverage"]
    relations = Coverage.search(
        [
            ("curriculum_unit_id", "=", unit.id),
            ("state", "=", "approved"),
        ],
        order="channel_id, coverage_type, id",
    )

    relation_rows = [
        {
            "channel_id": relation.channel_id.id,
            "coverage_type": relation.coverage_type,
            "confidence": relation.confidence,
            "origin": relation.origin,
        }
        for relation in relations
    ]
    relation_types = {row["coverage_type"] for row in relation_rows}
    if relation_types & {"covers", "equivalent"}:
        status = "covered"
    elif relation_types & {"partial", "supports"}:
        status = "partial"
    else:
        status = "gap"

    return {
        "schema_version": CURRICULUM_COVERAGE_VERSION,
        "unit_id": unit.id,
        "reference_id": unit.reference_id.id,
        "status": status,
        "approved_relations": relation_rows,
    }


def build_curriculum_reference_coverage(reference):
    """Summarize approved FACODI coverage for an external curriculum reference."""
    reference.ensure_one()
    reference.check_access("read")
    units = reference.unit_ids.sorted(key=lambda unit: (unit.sequence, unit.id))
    unit_rows = [build_curriculum_unit_coverage(unit) for unit in units]
    counts = {"gap": 0, "partial": 0, "covered": 0}
    for row in unit_rows:
        counts[row["status"]] += 1

    return {
        "schema_version": CURRICULUM_COVERAGE_VERSION,
        "reference_id": reference.id,
        "unit_count": len(unit_rows),
        "gap_count": counts["gap"],
        "partial_count": counts["partial"],
        "covered_count": counts["covered"],
        "units": unit_rows,
    }


def coverage_strength_for_unit(unit):
    """Return the strongest approved coverage signal for one curriculum unit."""
    unit.ensure_one()
    unit.check_access("read")
    Coverage = unit.env["facodi.learning.curriculum.coverage"]
    relations = Coverage.search(
        [
            ("curriculum_unit_id", "=", unit.id),
            ("state", "=", "approved"),
        ]
    )
    strengths = [
        float(relation.confidence or 0.0)
        * COVERAGE_STRENGTH.get(relation.coverage_type, 0.0)
        for relation in relations
    ]
    return round(max(strengths, default=0.0), 4)


def build_curriculum_selection_context(env):
    """Build deterministic, audit-safe candidate selection context."""
    Reference = env["facodi.learning.curriculum.reference"]
    references = Reference.search(
        [("selection_enabled", "=", True)],
        order="id",
    )
    units = []
    for reference in references:
        for unit in reference.unit_ids.sorted(key=lambda item: (item.sequence, item.id)):
            units.append(
                {
                    "reference_id": reference.id,
                    "programme_name": reference.programme_name,
                    "academic_year": reference.academic_year,
                    "unit_id": unit.id,
                    "unit_code": unit.external_unit_code,
                    "unit_name": unit.name,
                    "approved_coverage_strength": coverage_strength_for_unit(unit),
                }
            )
    return {
        "schema_version": CURRICULUM_COVERAGE_VERSION,
        "reference_ids": references.ids,
        "units": units,
    }


def score_candidate_curriculum_gap(candidate_name, context):
    """Score uncovered curriculum need for a course candidate."""
    reference_ids = list((context or {}).get("reference_ids") or [])
    units = list((context or {}).get("units") or [])
    if not reference_ids or not units:
        return {
            "score": 1.0,
            "evidence": {
                "mode": "baseline",
                "reference_ids": reference_ids,
            },
        }

    best = None
    best_need = -1.0
    for unit in units:
        similarity = course_title_similarity(candidate_name, unit.get("unit_name"))
        strength = max(
            0.0,
            min(float(unit.get("approved_coverage_strength") or 0.0), 1.0),
        )
        uncovered_gap = 1.0 - strength
        need = similarity * uncovered_gap
        if need > best_need:
            best_need = need
            best = {
                "reference_id": unit.get("reference_id"),
                "programme_name": unit.get("programme_name"),
                "academic_year": unit.get("academic_year"),
                "unit_id": unit.get("unit_id"),
                "unit_code": unit.get("unit_code"),
                "unit_name": unit.get("unit_name"),
                "title_similarity": similarity,
                "approved_coverage_strength": strength,
                "uncovered_gap": uncovered_gap,
            }

    score = max(0.0, min(best_need if best is not None else 0.0, 1.0))
    evidence = {
        "mode": "curriculum-gap",
        "reference_ids": reference_ids,
        "best_reference_id": best.get("reference_id") if best else False,
        "best_programme": best.get("programme_name") if best else False,
        "best_academic_year": best.get("academic_year") if best else False,
        "best_unit_id": best.get("unit_id") if best else False,
        "best_unit_code": best.get("unit_code") if best else False,
        "best_unit_name": best.get("unit_name") if best else False,
        "title_similarity": round(float(best.get("title_similarity") or 0.0), 4)
        if best
        else 0.0,
        "approved_coverage_strength": round(
            float(best.get("approved_coverage_strength") or 0.0), 4
        )
        if best
        else 0.0,
        "uncovered_gap": round(float(best.get("uncovered_gap") or 0.0), 4)
        if best
        else 0.0,
    }
    return {"score": round(float(score), 4), "evidence": evidence}
