"""Verify M3.1-M3.3 records survive a real main -> M3.4 addon upgrade."""


course_id = int(
    env["ir.config_parameter"].get_param(
        "facodi_learning.m34_upgrade_sentinel_course_id", "0"
    )
)
course = env["slide.channel"].browse(course_id).exists()
if not course:
    raise AssertionError("Canonical course sentinel was lost during M3.4 upgrade.")

prerequisite = env["slide.channel"].search(
    [("name", "=", "M3.4 Upgrade Sentinel Prerequisite")], limit=1
)
if not prerequisite or prerequisite not in course.prerequisite_channel_ids:
    raise AssertionError("Native Odoo prerequisite sentinel was changed by M3.4 upgrade.")

source_slide = env["slide.slide"].search(
    [("name", "=", "M3.4 Upgrade Sentinel Source")], limit=1
)
target_slide = env["slide.slide"].search(
    [("name", "=", "M3.4 Upgrade Sentinel Target")], limit=1
)
if not source_slide or not target_slide:
    raise AssertionError("Standard eLearning content sentinels were lost during upgrade.")
if source_slide.description != "Pre-M3.4 editorial sentinel content.":
    raise AssertionError("Editorial content was rewritten during M3.4 upgrade.")

candidate = env["facodi.learning.course.candidate"].search(
    [
        ("provider", "=", "manual"),
        ("external_id", "=", "m34-upgrade-sentinel-candidate"),
    ],
    limit=1,
)
if not candidate:
    raise AssertionError("M3.1 course candidate sentinel was lost during upgrade.")

source = env["facodi.learning.source"].search(
    [
        ("provider", "=", "manual"),
        ("external_id", "=", "m34-upgrade-sentinel-source"),
        ("channel_id", "=", course.id),
    ],
    limit=1,
)
if not source or source.state != "imported" or source.slide_id != source_slide:
    raise AssertionError("Content provenance sentinel was changed during upgrade.")

analysis_results = env["facodi.learning.analysis.result"].search(
    [("slide_id", "=", source_slide.id)]
)
if not analysis_results:
    raise AssertionError("Analysis history sentinel was lost during M3.4 upgrade.")

content_mapping = env["facodi.learning.mapping"].search(
    [
        ("source_slide_id", "=", source_slide.id),
        ("target_slide_id", "=", target_slide.id),
        ("mapping_type", "=", "related"),
    ],
    limit=1,
)
if not content_mapping or content_mapping.state != "approved":
    raise AssertionError("Approved content mapping sentinel was changed during upgrade.")

course_mapping = env["facodi.learning.course.mapping"].search(
    [
        ("source_channel_id", "=", course.id),
        ("target_channel_id", "=", prerequisite.id),
        ("mapping_type", "=", "related"),
    ],
    limit=1,
)
if not course_mapping or course_mapping.state != "approved":
    raise AssertionError("Approved course mapping sentinel was changed during upgrade.")

for model_name in (
    "facodi.learning.curriculum.reference",
    "facodi.learning.curriculum.unit",
    "facodi.learning.curriculum.coverage",
):
    if model_name not in env.registry.models:
        raise AssertionError(f"M3.4 model was not installed: {model_name}")

lesti = env["facodi.learning.curriculum.reference"].search(
    [
        ("provider", "=", "ualg"),
        ("external_id", "=", "ualg-1941-2026-27"),
    ]
)
if len(lesti) != 1:
    raise AssertionError(
        f"Expected exactly one curated UAlg LESTI reference after upgrade, got {len(lesti)}."
    )
if (
    lesti.external_programme_code != "1941"
    or lesti.academic_year != "2026/27"
    or not lesti.validated_at
    or not lesti.website_published
):
    raise AssertionError("Curated UAlg LESTI reference has an invalid public identity/state.")

units = env["facodi.learning.curriculum.unit"].search(
    [("reference_id", "=", lesti.id)]
)
if len(units) != 43 or len(set(units.mapped("external_unit_code"))) != 43:
    raise AssertionError(
        f"Expected 43 distinct curated LESTI curricular units after upgrade, got {len(units)}."
    )
design_refs = {}
for programme_code, external_id, expected_units in (
    ("1930", "ualg-1930-2026-27", 19),
    ("1454", "ualg-1454-2026-27", 41),
):
    reference = env["facodi.learning.curriculum.reference"].search(
        [
            ("provider", "=", "ualg"),
            ("external_id", "=", external_id),
        ]
    )
    if len(reference) != 1:
        raise AssertionError(
            f"Expected one curated UAlg design reference {external_id}, got {len(reference)}."
        )
    if (
        reference.external_programme_code != programme_code
        or reference.academic_year != "2026/27"
        or not reference.validated_at
        or not reference.website_published
    ):
        raise AssertionError(
            f"Curated UAlg design reference {external_id} has an invalid public identity/state."
        )
    programme_units = env["facodi.learning.curriculum.unit"].search(
        [("reference_id", "=", reference.id)]
    )
    if (
        len(programme_units) != expected_units
        or len(set(programme_units.mapped("external_unit_code"))) != expected_units
    ):
        raise AssertionError(
            f"Expected {expected_units} distinct units for {external_id}, got {len(programme_units)}."
        )
    design_refs[programme_code] = reference

expected_reference_ids = {lesti.id, design_refs["1930"].id, design_refs["1454"].id}
if set(env["facodi.learning.curriculum.reference"].search([]).ids) != expected_reference_ids:
    raise AssertionError("Upgrade created curriculum references outside the curated 2026/27 set.")

design_coverage = env["facodi.learning.curriculum.coverage"].search([])
if len(design_coverage) != 4:
    raise AssertionError(
        f"Expected four seeded DTM supports relations on a clean upgrade, got {len(design_coverage)}."
    )
if set(design_coverage.mapped("state")) != {"approved"}:
    raise AssertionError("Seeded DTM coverage must be explicitly approved supports relations.")
if set(design_coverage.mapped("coverage_type")) != {"supports"}:
    raise AssertionError("Seeded design coverage may only use supports relations.")
if set(design_coverage.mapped("curriculum_unit_id.external_unit_code")) != {
    "19301001",
    "19301006",
    "19301008",
    "19301009",
}:
    raise AssertionError(
        "Clean-upgrade DTM coverage must target Design Foundations, Interaction Design, Motion Design and Web Design."
    )
