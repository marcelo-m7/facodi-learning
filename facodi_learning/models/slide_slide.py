import logging

from odoo import api, fields, models

from ..services.supabase_edge import sync_slide_video_to_supabase

_logger = logging.getLogger(__name__)


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

    @api.model_create_multi
    def create(self, vals_list):
        slides = super().create(vals_list)
        for slide in slides:
            try:
                slide._facodi_sync_supabase_video_if_needed()
            except Exception as exc:  # pragma: no cover - should be logged, never block content creation.
                _logger.warning(
                    "FACODI Supabase video sync failed for slide %s (%s)",
                    slide.id,
                    type(exc).__name__,
                )
        return slides

    def write(self, vals):
        result = super().write(vals)
        if any(
            key in vals for key in ("video_url", "url", "name", "description", "slide_category")
        ):
            for slide in self:
                try:
                    slide._facodi_sync_supabase_video_if_needed()
                except Exception as exc:  # pragma: no cover - should be logged, never block updates.
                    _logger.warning(
                        "FACODI Supabase video sync failed for slide %s (%s)",
                        slide.id,
                        type(exc).__name__,
                    )
        return result

    def _facodi_sync_supabase_video_if_needed(self):
        self.ensure_one()
        if self.env.context.get("facodi_supabase_video_sync"):
            return False
        if self.slide_category != "video" and self.slide_type != "youtube_video":
            return False
        video_url = (self.video_url or self.url or "").strip()
        if not video_url:
            return False
        self.with_context(facodi_supabase_video_sync=True)._facodi_sync_supabase_video()
        return True

    def _facodi_sync_supabase_video(self):
        self.ensure_one()
        return sync_slide_video_to_supabase(self)

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
