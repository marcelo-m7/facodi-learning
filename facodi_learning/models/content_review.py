import hashlib

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


_CONTENT_HASH_FIELDS = frozenset({"name", "description", "html_content", "url"})
_PUBLICATION_FIELDS = frozenset({"is_published", "website_published"})


def _slide_hash(slide):
    values = "\0".join(
        str(getattr(slide, field, "") or "")
        for field in ("name", "description", "html_content", "url")
    )
    return hashlib.sha256(values.encode()).hexdigest()


class ContentReview(models.Model):
    _name = "facodi.learning.content.review"
    _description = "Content publication review"
    _order = "id desc"

    slide_id = fields.Many2one(
        "slide.slide",
        required=True,
        ondelete="restrict",
        index=True,
    )
    source_id = fields.Many2one(
        "facodi.learning.source",
        ondelete="restrict",
        index=True,
        help="Canonical FACODI source when this review originated from ingestion.",
    )
    origin = fields.Selection(
        [
            ("manual", "Manual"),
            ("source_ingestion", "Source ingestion"),
            ("legacy_reconciliation", "Legacy reconciliation"),
        ],
        default="manual",
        required=True,
        readonly=True,
    )
    author = fields.Char(
        help="Claimed creator or responsible author. Leave blank until verified."
    )
    rights_mode = fields.Selection(
        [
            ("original", "Original"),
            ("licensed", "Licensed"),
            ("external", "External"),
        ],
        help="How FACODI is permitted to use this material. Leave blank until verified.",
    )
    usage_basis = fields.Text(
        help="Evidence or rationale supporting the permitted use of this content."
    )
    purpose = fields.Text(help="Editorial purpose for including this content in FACODI.")
    source_url = fields.Char(
        help="Public provenance URL when one exists. Do not invent a source URL."
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="pending",
        required=True,
        readonly=True,
    )
    content_hash = fields.Char(readonly=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    decision_note = fields.Text(
        help="Manager decision note. Required when rejecting a review."
    )

    @api.model_create_multi
    def create(self, vals_list):
        protected = {"state", "content_hash", "reviewed_by_id", "reviewed_at"}
        if any(protected & set(vals) for vals in vals_list):
            raise AccessError("Review lifecycle evidence is managed by review actions.")
        records = super().create(vals_list)
        records._check_source_consistency()
        return records

    def write(self, vals):
        protected = {"state", "content_hash", "reviewed_by_id", "reviewed_at", "origin"}
        if protected & set(vals):
            raise AccessError("Use review actions to change review lifecycle evidence.")
        if any(review.state in {"approved", "rejected"} for review in self):
            raise AccessError("Completed content reviews are immutable.")
        result = super().write(vals)
        self._check_source_consistency()
        return result

    def unlink(self):
        if any(review.state in {"approved", "rejected"} for review in self):
            raise AccessError("Completed content reviews are immutable.")
        return super().unlink()

    @api.constrains("slide_id", "source_id")
    def _check_source_consistency(self):
        for review in self.filtered("source_id"):
            if review.source_id.slide_id and review.source_id.slide_id != review.slide_id:
                raise ValidationError(
                    "The canonical source must point to the content being reviewed."
                )

    def _require_manager(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError("Only eLearning Managers can decide content reviews.")

    def _check_approval_evidence(self):
        self.ensure_one()
        missing = []
        if not (self.author or "").strip():
            missing.append("author")
        if not self.rights_mode:
            missing.append("rights mode")
        if not (self.usage_basis or "").strip():
            missing.append("permitted-use evidence")
        if not (self.purpose or "").strip():
            missing.append("editorial purpose")
        if self.rights_mode in {"licensed", "external"} and not (
            self.source_id or (self.source_url or "").strip()
        ):
            missing.append("source provenance")
        if missing:
            raise ValidationError(
                "Complete the publication evidence before approval: %s."
                % ", ".join(missing)
            )

    def action_approve(self):
        self._require_manager()
        for review in self:
            if review.state != "pending":
                raise ValidationError("Only pending reviews can be approved.")
            review._check_source_consistency()
            review._check_approval_evidence()
            super(ContentReview, review).write(
                {
                    "state": "approved",
                    "content_hash": _slide_hash(review.slide_id),
                    "reviewed_by_id": self.env.user.id,
                    "reviewed_at": fields.Datetime.now(),
                }
            )
            review.slide_id.write({"facodi_legacy_review_pending": False})
        return True

    def action_reject(self):
        self._require_manager()
        for review in self:
            if review.state != "pending":
                raise ValidationError("Only pending reviews can be rejected.")
            if not (review.decision_note or "").strip():
                raise ValidationError("A decision note is required when rejecting content.")
            super(ContentReview, review).write(
                {
                    "state": "rejected",
                    "content_hash": _slide_hash(review.slide_id),
                    "reviewed_by_id": self.env.user.id,
                    "reviewed_at": fields.Datetime.now(),
                }
            )
        return True


class SlideSlide(models.Model):
    _inherit = "slide.slide"

    facodi_content_review_ids = fields.One2many(
        "facodi.learning.content.review",
        "slide_id",
        string="FACODI Publication Reviews",
    )
    facodi_legacy_review_pending = fields.Boolean(
        default=False,
        readonly=True,
        help=(
            "This content was already public when FACODI publication governance "
            "was enabled and still needs provenance review."
        ),
    )

    def _facodi_review_website(self):
        self.ensure_one()
        explicit = self.website_id or self.channel_id.website_id
        if explicit:
            return explicit
        return self.env["website"].search(
            [("facodi_publication_review_enabled", "=", True)],
            order="id",
            limit=1,
        )

    def _facodi_requires_review(self):
        return any(
            slide._facodi_review_website().facodi_publication_review_enabled
            for slide in self
        )

    def _facodi_has_approved_review(self):
        self.ensure_one()
        current_hash = _slide_hash(self)
        return any(
            review.state == "approved" and review.content_hash == current_hash
            for review in self.facodi_content_review_ids
        )

    def _facodi_is_public(self):
        self.ensure_one()
        return bool(
            getattr(self, "is_published", False)
            or getattr(self, "website_published", False)
        )

    def _facodi_check_publication_review(self):
        for slide in self:
            if (
                slide._facodi_is_public()
                and slide._facodi_requires_review()
                and not slide._facodi_has_approved_review()
            ):
                raise ValidationError(
                    "Publishing requires an approved FACODI content review for the current content."
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._facodi_check_publication_review()
        return records

    def write(self, vals):
        result = super().write(vals)
        if (_CONTENT_HASH_FIELDS | _PUBLICATION_FIELDS) & set(vals):
            self._facodi_check_publication_review()
        return result


class Website(models.Model):
    _inherit = "website"

    facodi_publication_review_enabled = fields.Boolean(
        default=True,
        readonly=True,
        help=(
            "FACODI requires provenance and Manager review before new learning "
            "content can be published."
        ),
    )

    def action_facodi_enable_publication_review(self):
        Slide = self.env["slide.slide"]
        for website in self:
            if not website.facodi_publication_review_enabled:
                website.write({"facodi_publication_review_enabled": True})
            for slide in Slide.search([("is_published", "=", True)]):
                if (
                    slide._facodi_review_website() == website
                    and not slide._facodi_has_approved_review()
                    and not slide.facodi_legacy_review_pending
                ):
                    slide.write({"facodi_legacy_review_pending": True})
        return True
