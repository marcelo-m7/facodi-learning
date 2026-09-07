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
    if env[model_name].search_count([]):
        raise AssertionError(f"M3.4 fabricated curriculum rows during upgrade: {model_name}")
