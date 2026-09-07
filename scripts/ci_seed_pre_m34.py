"""Seed M3.1-M3.3 records before the M3.4 upgrade CI gate.

Executed through `odoo shell` against the addon at the merge-base with main.
"""

from odoo import Command


prerequisite = env["slide.channel"].create(
    {"name": "M3.4 Upgrade Sentinel Prerequisite"}
)
course = env["slide.channel"].create(
    {
        "name": "M3.4 Upgrade Sentinel Course",
        "prerequisite_channel_ids": [Command.link(prerequisite.id)],
    }
)
source_slide = env["slide.slide"].create(
    {
        "name": "M3.4 Upgrade Sentinel Source",
        "channel_id": course.id,
        "slide_category": "article",
        "description": "Pre-M3.4 editorial sentinel content.",
    }
)
target_slide = env["slide.slide"].create(
    {
        "name": "M3.4 Upgrade Sentinel Target",
        "channel_id": course.id,
        "slide_category": "article",
    }
)

env["facodi.learning.course.candidate"].create(
    {
        "provider": "manual",
        "external_id": "m34-upgrade-sentinel-candidate",
        "name": "M3.4 Upgrade Sentinel Candidate",
    }
)

env["facodi.learning.source"].ingest(
    {
        "name": "M3.4 Upgrade Sentinel Source Provenance",
        "provider": "manual",
        "external_id": "m34-upgrade-sentinel-source",
        "channel_id": course.id,
        "url": "https://example.invalid/m34-upgrade-sentinel",
    },
    slide_id=source_slide.id,
)

analysis_job = source_slide.action_facodi_request_analysis()
analysis_job.action_process()
if analysis_job.state != "completed" or not analysis_job.result_id:
    raise AssertionError("Pre-M3.4 analysis sentinel did not complete.")

content_mapping = env["facodi.learning.mapping"].create(
    {
        "source_slide_id": source_slide.id,
        "target_slide_id": target_slide.id,
        "mapping_type": "related",
        "origin": "manual",
        "confidence": 0.75,
    }
)
content_mapping.action_approve()

course_mapping = env["facodi.learning.course.mapping"].create(
    {
        "source_channel_id": course.id,
        "target_channel_id": prerequisite.id,
        "mapping_type": "related",
        "origin": "manual",
        "confidence": 0.8,
        "evidence": {"sentinel": "pre-m3.4"},
    }
)
course_mapping.action_approve()

env["ir.config_parameter"].set_param(
    "facodi_learning.m34_upgrade_sentinel_course_id", str(course.id)
)
env.cr.commit()
