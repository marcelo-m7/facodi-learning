from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


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

    _mapping_unique = models.Constraint(
        "unique(source_channel_id, target_channel_id, mapping_type)",
        "This course mapping already exists.",
    )

    @api.constrains("source_channel_id", "target_channel_id")
    def _check_distinct_channels(self):
        if any(
            mapping.source_channel_id == mapping.target_channel_id
            for mapping in self
        ):
            raise ValidationError("Source and target courses must be different.")

    @api.constrains("confidence")
    def _check_confidence(self):
        for mapping in self:
            if not 0 <= mapping.confidence <= 1:
                raise ValidationError("Confidence must be between zero and one.")

    def _check_manager(self):
        if not self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        ):
            raise AccessError(
                "Only eLearning Managers can review FACODI course mappings."
            )

    @api.model_create_multi
    def create(self, vals_list):
        protected = (
            "reviewed_by_id",
            "reviewed_at",
            "policy_version",
            "decision_snapshot",
            "native_applied_by_id",
            "native_applied_at",
        )
        for vals in vals_list:
            if vals.get("state", "proposed") != "proposed" or any(
                vals.get(field_name) for field_name in protected
            ):
                raise AccessError("Use the explicit course mapping review actions.")
            vals.update(
                state="proposed",
                reviewed_by_id=False,
                reviewed_at=False,
                policy_version=False,
                decision_snapshot=False,
                native_applied_by_id=False,
                native_applied_at=False,
            )
        return super().create(vals_list)

    def write(self, vals):
        protected = {
            "state",
            "reviewed_by_id",
            "reviewed_at",
            "source_channel_id",
            "target_channel_id",
            "mapping_type",
            "origin",
            "ranking_version",
            "policy_version",
            "decision_snapshot",
            "native_applied_by_id",
            "native_applied_at",
        }
        if protected & vals.keys():
            raise AccessError("Use the explicit course mapping review actions.")
        if any(mapping.state != "proposed" for mapping in self):
            raise AccessError("Reviewed course mappings are historical evidence.")
        return super().write(vals)

    def unlink(self):
        if any(
            mapping.state != "proposed" or mapping.origin != "manual"
            for mapping in self
        ):
            raise AccessError("Reviewed and generated course mappings are audit history.")
        return super().unlink()

    def _review(self, state):
        if state not in {"approved", "rejected"}:
            raise ValidationError("Unsupported course mapping review state.")
        self._check_manager()
        self.check_access("write")
        records = self.try_lock_for_update()
        records.invalidate_recordset()
        if len(records) != len(self) or any(
            mapping.state != "proposed" for mapping in records
        ):
            raise ValidationError(
                "Only available proposed course mappings can be reviewed."
            )
        return super(FacodiLearningCourseMapping, records).write(
            {
                "state": state,
                "reviewed_by_id": self.env.uid,
                "reviewed_at": fields.Datetime.now(),
            }
        )

    def action_approve(self):
        return self._review("approved")

    def action_reject(self):
        return self._review("rejected")
