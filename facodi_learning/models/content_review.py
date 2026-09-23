import hashlib

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


def _slide_hash(slide):
    values = "\0".join(str(getattr(slide, field, "") or "") for field in ("name", "description", "html_content", "url"))
    return hashlib.sha256(values.encode()).hexdigest()


class ContentReview(models.Model):
    _name = "facodi.learning.content.review"
    _description = "Content publication review"
    slide_id = fields.Many2one("slide.slide", required=True, ondelete="cascade")
    author = fields.Char(required=True)
    rights_mode = fields.Selection([("original", "Original"), ("licensed", "Licensed"), ("external", "External")], required=True)
    purpose = fields.Text(required=True)
    source_url = fields.Char()
    state = fields.Selection([("pending", "Pending"), ("approved", "Approved")], default="pending", readonly=True)
    content_hash = fields.Char(readonly=True)

    def write(self, vals):
        if {"state", "content_hash"} & set(vals):
            raise AccessError("Use review actions to approve content.")
        if any(review.state == "approved" for review in self):
            raise AccessError("Approved reviews are immutable.")
        return super().write(vals)

    def action_approve(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError("Only eLearning Managers can approve content reviews.")
        for review in self:
            super(ContentReview, review).write({"state": "approved", "content_hash": _slide_hash(review.slide_id)})


class SlideSlide(models.Model):
    _inherit = "slide.slide"
    facodi_content_review_ids = fields.One2many("facodi.learning.content.review", "slide_id")
    facodi_legacy_review_pending = fields.Boolean(default=False)

    def _facodi_requires_review(self):
        return any((slide.website_id or slide.channel_id.website_id).facodi_publication_review_enabled for slide in self)

    def _facodi_has_approved_review(self):
        return any(review.state == "approved" and review.content_hash == _slide_hash(self) for review in self.facodi_content_review_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any(record.is_published and record._facodi_requires_review() and not record._facodi_has_approved_review() for record in records):
            raise ValidationError("Publishing requires an approved content review.")
        return records

    def write(self, vals):
        if vals.get("is_published") and any(slide._facodi_requires_review() and not slide._facodi_has_approved_review() for slide in self):
            raise ValidationError("Publishing requires an approved content review.")
        return super().write(vals)


class Website(models.Model):
    _inherit = "website"
    facodi_publication_review_enabled = fields.Boolean(default=False)

    def action_facodi_enable_publication_review(self):
        for website in self:
            website.facodi_publication_review_enabled = True
            self.env["slide.slide"].search([("website_id", "=", website.id), ("is_published", "=", True)]).write({"facodi_legacy_review_pending": True})