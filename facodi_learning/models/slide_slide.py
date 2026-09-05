from odoo import fields, models


class SlideSlide(models.Model):
    _inherit = "slide.slide"

    facodi_transcript = fields.Text(
        groups="website_slides.group_website_slides_officer",
        string="Transcript",
        help="Optional transcript used by FACODI analysis. The eLearning content remains the canonical record.",
    )
    facodi_analysis_job_ids = fields.One2many(
        "facodi.learning.analysis.job",
        "slide_id",
        groups="website_slides.group_website_slides_officer",
        string="FACODI Analysis Jobs",
    )
    facodi_analysis_result_ids = fields.One2many(
        "facodi.learning.analysis.result",
        "slide_id",
        groups="website_slides.group_website_slides_officer",
        string="FACODI Analysis Results",
    )
    facodi_source_mapping_ids = fields.One2many(
        "facodi.learning.mapping",
        "source_slide_id",
        groups="website_slides.group_website_slides_officer",
        string="FACODI Outgoing Mappings",
    )
    facodi_target_mapping_ids = fields.One2many(
        "facodi.learning.mapping",
        "target_slide_id",
        groups="website_slides.group_website_slides_officer",
        string="FACODI Incoming Mappings",
    )

    def action_facodi_request_analysis(self):
        """Create an auditable analysis request for this standard eLearning item."""
        self.ensure_one()
        provider = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("facodi_learning.analysis_provider", "local_metadata")
        )
        return self.env["facodi.learning.analysis.job"].create(
            {
                "slide_id": self.id,
                "provider": provider,
            }
        )

    def action_facodi_request_analysis_ui(self):
        self.ensure_one()
        job = self.action_facodi_request_analysis()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("FACODI Analysis"),
                "message": self.env._("Analysis job %(job)s was queued.", job=job.id),
                "type": "success",
                "sticky": False,
            },
        }

    def _facodi_related_slides(self, website):
        """Expose only approved links, then apply standard learner access rules.

        Elevation is limited to relation lookup: students cannot read audit models.
        Returned slide records never retain sudo and are filtered by publication,
        website and native course visibility, including link-only courses.
        """
        self.ensure_one()
        slide = self.sudo(False)
        slide.check_access("read")
        targets = (
            self.env["facodi.learning.mapping"]
            .sudo()
            .search(
                [
                    ("source_slide_id", "=", slide.id),
                    ("state", "=", "approved"),
                ]
            )
            .mapped("target_slide_id")
            .ids
        )
        return slide.search(
            [
                ("id", "in", targets),
                ("is_published", "=", True),
                ("channel_id.is_published", "=", True),
                ("channel_id.is_visible", "=", True),
                ("website_id", "in", [False, website.id]),
            ],
            limit=8,
        )
