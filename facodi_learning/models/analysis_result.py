from odoo import Command, fields, models


class FacodiLearningAnalysisResult(models.Model):
    _name = "facodi.learning.analysis.result"
    _description = "FACODI Learning Analysis Result"
    _order = "create_date desc, id desc"

    job_id = fields.Many2one(
        "facodi.learning.analysis.job", required=True, ondelete="restrict", index=True
    )
    slide_id = fields.Many2one(
        "slide.slide", required=True, ondelete="cascade", index=True, string="Content"
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

    def action_apply_suggested_tags(self):
        for result in self:
            if result.suggested_tag_ids:
                result.slide_id.write({
                    "tag_ids": [Command.link(tag_id) for tag_id in result.suggested_tag_ids.ids],
                })
        return True
