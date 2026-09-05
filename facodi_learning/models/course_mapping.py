from odoo import fields, models


class FacodiLearningCourseMapping(models.Model):
    _name = "facodi.learning.course.mapping"
    _description = "FACODI Course Mapping"
    _order = "create_date desc, id desc"

    source_channel_id = fields.Many2one(
        "slide.channel",
        required=True,
        ondelete="restrict",
        index=True,
        string="Source Course",
    )
    target_channel_id = fields.Many2one(
        "slide.channel",
        required=True,
        ondelete="restrict",
        index=True,
        string="Target Course",
    )
    mapping_type = fields.Selection(
        [
            ("related", "Related"),
            ("alternative", "Alternative"),
            ("continuation", "Continuation"),
            ("complements", "Complements"),
            ("equivalent", "Equivalent"),
            ("prerequisite", "Prerequisite"),
        ],
        required=True,
        default="related",
        index=True,
    )
    confidence = fields.Float(digits=(5, 4))
    origin = fields.Selection(
        [("manual", "Manual"), ("analysis", "Analysis")],
        required=True,
        default="manual",
        index=True,
    )
    state = fields.Selection(
        [
            ("proposed", "Proposed"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        required=True,
        default="proposed",
        index=True,
    )
    evidence = fields.Json()
    ranking_version = fields.Char(readonly=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    policy_version = fields.Char(readonly=True)
    decision_snapshot = fields.Json(readonly=True)
    native_applied_by_id = fields.Many2one("res.users", readonly=True)
    native_applied_at = fields.Datetime(readonly=True)
