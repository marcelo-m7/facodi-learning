from odoo import api, Command, fields, models
from odoo.exceptions import AccessError, ValidationError


class FacodiLearningAnalysisResult(models.Model):
    _name = "facodi.learning.analysis.result"
    _description = "FACODI Learning Analysis Result"
    _order = "create_date desc, id desc"

    job_id = fields.Many2one(
        "facodi.learning.analysis.job", required=True, ondelete="restrict", index=True
    )
    slide_id = fields.Many2one(
        "slide.slide", required=True, ondelete="restrict", index=True, string="Content"
    )
    provider = fields.Char(required=True, readonly=True)
    model_name = fields.Char(readonly=True)
    summary = fields.Text(readonly=True)
    detected_language = fields.Char(readonly=True)
    suggested_tag_ids = fields.Many2many(
        "slide.tag",
        "facodi_analysis_result_slide_tag_rel",
        "result_id",
        "tag_id",
        string="Suggested eLearning Tags",
        readonly=True,
    )
    raw_payload = fields.Json(readonly=True)

    transcript = fields.Text(readonly=True)
    suggested_tags = fields.Json(readonly=True)
    proposed_mappings = fields.Json(readonly=True)
    tags_applied_by_id = fields.Many2one("res.users", readonly=True)
    tags_applied_at = fields.Datetime(readonly=True)

    tags_review_state = fields.Selection(
        [("pending", "Pending"), ("applied", "Applied"), ("rejected", "Rejected")],
        default="pending",
        required=True,
        readonly=True,
    )
    tags_reviewed_by_id = fields.Many2one("res.users", readonly=True)
    tags_reviewed_at = fields.Datetime(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError("Analysis results can only be created by the processor.")

    @api.model
    def _record_output(self, values):
        values = dict(
            values,
            tags_review_state="pending",
            tags_applied_by_id=False,
            tags_applied_at=False,
            tags_reviewed_by_id=False,
            tags_reviewed_at=False,
        )
        return super().create(values)

    def write(self, values):
        raise AccessError("Analysis output is immutable.")

    def unlink(self):
        raise AccessError("Analysis history cannot be deleted.")

    def action_apply_suggested_tags(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError("Only eLearning Managers can apply analysis suggestions.")
        self.check_access("read")
        for result in self.try_lock_for_update():
            result.invalidate_recordset()
            if result.tags_review_state == "rejected":
                raise ValidationError(
                    "Rejected suggestions cannot be applied. Request a new analysis."
                )
            if result.tags_applied_at:
                continue
            tags = result.suggested_tag_ids
            for name in result.suggested_tags or []:
                tag = self.env["slide.tag"].search([("name", "=", name)], limit=1)
                tags |= tag or self.env["slide.tag"].create({"name": name})
            result.slide_id.write({"tag_ids": [Command.link(tag.id) for tag in tags]})
            super(FacodiLearningAnalysisResult, result).write(
                {
                    "tags_applied_by_id": self.env.uid,
                    "tags_applied_at": fields.Datetime.now(),
                    "tags_review_state": "applied",
                    "tags_reviewed_by_id": self.env.uid,
                    "tags_reviewed_at": fields.Datetime.now(),
                }
            )
        return True

    def action_reject_suggested_tags(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError(
                "Only eLearning Managers can review analysis suggestions."
            )
        self.check_access("read")
        records = self.try_lock_for_update()
        records.invalidate_recordset()
        if len(records) != len(self) or any(
            record.tags_review_state != "pending" for record in records
        ):
            raise ValidationError("Only available pending suggestions can be rejected.")
        return super(FacodiLearningAnalysisResult, records).write(
            {
                "tags_review_state": "rejected",
                "tags_reviewed_by_id": self.env.uid,
                "tags_reviewed_at": fields.Datetime.now(),
            }
        )
