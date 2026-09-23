"""Reviewed reusable mapping for UAlg LESTI unit 19411018."""

from odoo.exceptions import ValidationError


REFERENCE_IDENTITY = {
    "provider": "ualg",
    "external_id": "ualg-1941-2026-27",
}
UNIT_CODE = "19411018"

MODULES = (
    (
        10,
        "Eventos e probabilidade condicional",
        ("Probabilidade e Estatística: Fundamentos",),
    ),
    (
        20,
        "Variáveis aleatórias e distribuições",
        ("Probabilidade: variáveis aleatórias e distribuições",),
    ),
    (
        30,
        "Estatística descritiva e amostragem",
        ("Probabilidade e Estatística: Fundamentos",),
    ),
    (
        40,
        "Estimação e testes de hipóteses",
        ("Estatística: dos dados à inferência e regressão",),
    ),
    (
        50,
        "ANOVA, correlação e regressão",
        ("Estatística: dos dados à inferência e regressão",),
    ),
)

COURSE_NAMES = tuple(sorted({course for _, _, courses in MODULES for course in courses}))


def _required_course_by_name(env):
    courses = env["slide.channel"].search([("name", "in", COURSE_NAMES)])
    by_name = {course.name: course for course in courses}
    missing = [name for name in COURSE_NAMES if name not in by_name]
    unpublished = [
        course.name
        for course in by_name.values()
        if not course.is_published or not course.website_published
    ]
    if missing or unpublished:
        details = []
        if missing:
            details.append("missing: %s" % ", ".join(missing))
        if unpublished:
            details.append("not published: %s" % ", ".join(unpublished))
        raise ValidationError("Cannot map probability and statistics courses (%s)." % "; ".join(details))
    return by_name


def apply_probability_statistics_mapping(env):
    """Create only missing reviewed mappings for the validated public LESTI UC."""
    reference = env["facodi.learning.curriculum.reference"].search(
        [
            ("provider", "=", REFERENCE_IDENTITY["provider"]),
            ("external_id", "=", REFERENCE_IDENTITY["external_id"]),
        ],
        limit=1,
    )
    if not reference or not reference._facodi_is_public():
        raise ValidationError("The validated public UAlg LESTI reference is required.")
    unit = env["facodi.learning.curriculum.unit"].search(
        [("reference_id", "=", reference.id), ("external_unit_code", "=", UNIT_CODE)],
        limit=1,
    )
    if not unit:
        raise ValidationError("Curricular unit 19411018 is required.")

    courses = _required_course_by_name(env)
    Module = env["facodi.learning.curriculum.module"]
    Assignment = env["facodi.learning.curriculum.module.assignment"]
    Item = env["facodi.learning.curriculum.module.item"]
    Coverage = env["facodi.learning.curriculum.coverage"]

    rejected_coverage = Coverage.search(
        [
            ("channel_id", "in", [course.id for course in courses.values()]),
            ("curriculum_unit_id", "=", unit.id),
            ("coverage_type", "=", "partial"),
            ("state", "=", "rejected"),
        ],
        limit=1,
    )
    if rejected_coverage:
        raise ValidationError("A rejected probability and statistics coverage must be reviewed first.")

    for sequence, module_name, course_names in MODULES:
        module = Module.search([("name", "=", module_name)], limit=1)
        if not module:
            module = Module.create({"name": module_name, "website_published": True})
        elif not module.website_published:
            module.write({"website_published": True})

        assignment = Assignment.search(
            [("curriculum_unit_id", "=", unit.id), ("module_id", "=", module.id)],
            limit=1,
        )
        if not assignment:
            Assignment.create(
                {"curriculum_unit_id": unit.id, "module_id": module.id, "sequence": sequence}
            )

        for course_name in course_names:
            course = courses[course_name]
            if not Item.search_count(
                [("module_id", "=", module.id), ("channel_id", "=", course.id)], limit=1
            ):
                Item.create({"module_id": module.id, "channel_id": course.id, "sequence": sequence})

            coverage = Coverage.search(
                [
                    ("channel_id", "=", course.id),
                    ("curriculum_unit_id", "=", unit.id),
                    ("coverage_type", "=", "partial"),
                ],
                limit=1,
            )
            if not coverage:
                coverage = Coverage.create(
                    {
                        "channel_id": course.id,
                        "curriculum_unit_id": unit.id,
                        "coverage_type": "partial",
                        "confidence": 1.0,
                        "evidence": {"mapping": "ualg-1941-2026-27-19411018"},
                    }
                )
            if coverage.state == "proposed":
                coverage.action_approve()

    return unit