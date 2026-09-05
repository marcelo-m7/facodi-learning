from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FacodiLearningMapping(models.Model):
    _name = "facodi.learning.mapping"
    _description = "FACODI Learning Mapping"
    _order = "create_date desc, id desc"

    source_slide_id = fields.Many2one(
        "slide.slide",
        required=True,
        ondelete="restrict",
        index=True,
        string="Source Content",
    )
    target_slide_id = fields.Many2one(
        "slide.slide",
        required=True,
        ondelete="restrict",
        index=True,
        string="Target Content",
    )
    mapping_type = fields.Selection(
        [
            ("related", "Related"),
            ("prerequisite", "Prerequisite"),
            ("recommended", "Recommended"),
            ("supports", "Supports"),
        ],
        required=True,
        default="related",
    )
    confidence = fields.Float(digits=(5, 4))
    origin = fields.Selection(
        [("manual", "Manual"), ("analysis", "Analysis")],
        required=True,
        default="manual",
    )
    state = fields.Selection(
        [("proposed", "Proposed"), ("approved", "Approved"), ("rejected", "Rejected")],
        required=True,
        default="proposed",
        index=True,
    )
    analysis_result_id = fields.Many2one(
        "facodi.learning.analysis.result",
        ondelete="set null",
        string="Analysis Provenance",
    )
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)

    _mapping_unique = models.Constraint(
        "unique(source_slide_id, target_slide_id, mapping_type)",
        "This learning mapping already exists.",
    )

    @api.constrains("source_slide_id", "target_slide_id")
    def _check_distinct_slides(self):
        if any(mapping.source_slide_id == mapping.target_slide_id for mapping in self):
            raise ValidationError("Source and target content must be different.")

    def _check_manager(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError("Only eLearning Managers can review FACODI mappings.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            origin = vals.get(
                "origin", self.env.context.get("default_origin", "manual")
            )
            result_id = vals.get(
                "analysis_result_id", self.env.context.get("default_analysis_result_id")
            )
            if origin == "analysis" and not result_id:
                raise ValidationError("Analysis mappings require result provenance.")
            if result_id and origin != "analysis":
                raise ValidationError("Result provenance requires analysis origin.")
            if (
                vals.get("state", "proposed") != "proposed"
                or vals.get("reviewed_by_id")
                or vals.get("reviewed_at")
            ):
                raise AccessError("Use the explicit Manager review actions.")
            vals.update(state="proposed", reviewed_by_id=False, reviewed_at=False)
        return super().create(vals_list)

    def write(self, vals):
        if {
            "state",
            "reviewed_by_id",
            "reviewed_at",
            "source_slide_id",
            "analysis_result_id",
            "origin",
        } & vals.keys():
            raise AccessError("Use the explicit Manager review actions.")
        if any(record.state != "proposed" for record in self):
            raise AccessError("Reviewed mappings are historical evidence.")
        return super().write(vals)

    def unlink(self):
        if any(
            record.state != "proposed" or record.analysis_result_id for record in self
        ):
            raise AccessError("Reviewed and analysis mappings are audit history.")
        return super().unlink()

    @api.constrains("confidence", "analysis_result_id", "source_slide_id")
    def _check_provenance(self):
        for record in self:
            if not 0 <= record.confidence <= 1:
                raise ValidationError("Confidence must be between zero and one.")
            if (
                record.analysis_result_id
                and record.analysis_result_id.slide_id != record.source_slide_id
            ):
                raise ValidationError(
                    "Analysis provenance must match the source content."
                )

    def _review(self, state):
        self._check_manager()
        self.check_access("write")
        records = self.try_lock_for_update()
        records.invalidate_recordset()
        if len(records) != len(self) or any(
            record.state != "proposed" for record in records
        ):
            raise ValidationError("Only available proposed mappings can be reviewed.")
        return super(FacodiLearningMapping, records).write(
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
