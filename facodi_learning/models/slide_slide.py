from odoo import fields, models


class SlideSlide(models.Model):
    _inherit = "slide.slide"

    facodi_transcript = fields.Text(
        string="Transcript",
        help="Optional transcript used by FACODI analysis. The eLearning content remains the canonical record.",
    )
    facodi_analysis_job_ids = fields.One2many(
        "facodi.learning.analysis.job", "slide_id", string="FACODI Analysis Jobs"
    )
    facodi_analysis_result_ids = fields.One2many(
        "facodi.learning.analysis.result", "slide_id", string="FACODI Analysis Results"
    )
    facodi_source_mapping_ids = fields.One2many(
        "facodi.learning.mapping", "source_slide_id", string="FACODI Outgoing Mappings"
    )
    facodi_target_mapping_ids = fields.One2many(
        "facodi.learning.mapping", "target_slide_id", string="FACODI Incoming Mappings"
    )

    def action_facodi_request_analysis(self):
        """Create an auditable analysis request for this standard eLearning item."""
        self.ensure_one()
        provider = self.env["ir.config_parameter"].sudo().get_param(
            "facodi_learning.analysis_provider", "local_metadata"
        )
        return self.env["facodi.learning.analysis.job"].create({
            "slide_id": self.id,
            "provider": provider,
        })
