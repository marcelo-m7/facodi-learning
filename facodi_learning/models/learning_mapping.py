from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FacodiLearningMapping(models.Model):
    _name = "facodi.learning.mapping"
    _description = "FACODI Learning Mapping"
    _order = "create_date desc, id desc"

    source_slide_id = fields.Many2one(
        "slide.slide", required=True, ondelete="cascade", index=True, string="Source Content"
    )
    target_slide_id = fields.Many2one(
        "slide.slide", required=True, ondelete="cascade", index=True, string="Target Content"
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
        "facodi.learning.analysis.result", ondelete="set null", string="Analysis Provenance"
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

    def action_approve(self):
        self._check_manager()
        self.write({
            "state": "approved",
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })
        return True

    def action_reject(self):
        self._check_manager()
        self.write({
            "state": "rejected",
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })
        return True
