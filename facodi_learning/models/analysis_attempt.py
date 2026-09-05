from odoo import api, fields, models
from odoo.exceptions import AccessError


class AnalysisAttempt(models.Model):
    _name = "facodi.learning.analysis.attempt"
    _description = "Analysis attempt evidence"
    _order = "id desc"

    job_id = fields.Many2one(
        "facodi.learning.analysis.job", required=True, ondelete="restrict", index=True
    )
    provider = fields.Char(required=True)
    number = fields.Integer(required=True)
    started_at = fields.Datetime(required=True)
    completed_at = fields.Datetime(required=True)
    state = fields.Selection(
        [("completed", "Completed"), ("failed", "Failed")], required=True
    )
    error = fields.Text()
    result_id = fields.Many2one("facodi.learning.analysis.result", ondelete="restrict")

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError("Attempts can only be recorded by the processor.")

    @api.model
    def _record_attempt(self, values):
        return super().create(values)

    def write(self, values):
        raise AccessError("Attempt evidence is immutable.")

    def unlink(self):
        raise AccessError("Attempt evidence cannot be deleted.")
