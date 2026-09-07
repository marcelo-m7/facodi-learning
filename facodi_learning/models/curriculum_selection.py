from odoo import fields, models


class FacodiLearningCurriculumReference(models.Model):
    _inherit = "facodi.learning.curriculum.reference"

    # Selection policy is operational configuration for M3.1 gap scoring, not an
    # external curriculum fact. Keep it separate from immutable source identity.
    selection_enabled = fields.Boolean(default=False, index=True)
