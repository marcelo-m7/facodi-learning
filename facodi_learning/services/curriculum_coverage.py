CURRICULUM_COVERAGE_VERSION = "curriculum-coverage-v1"


def build_curriculum_unit_coverage(unit):
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
