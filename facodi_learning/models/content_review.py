import hashlib
import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


_CONTENT_HASH_FIELD_ORDER = (
    "name",
    "description",
    "html_content",
    "url",
    "binary_content",
    "slide_category",
    "source_type",
    "channel_id",
)
_CONTENT_HASH_FIELDS = frozenset(_CONTENT_HASH_FIELD_ORDER)
_PUBLICATION_FIELDS = frozenset({"is_published", "website_published"})
_PUBLICATION_SCOPE_FIELDS = frozenset({"channel_id"})
_QUESTION_HASH_FIELD_ORDER = ("sequence", "question")
_QUESTION_HASH_FIELDS = frozenset(
    {"sequence", "question", "slide_id", "answer_ids"}
)
_ANSWER_HASH_FIELD_ORDER = ("sequence", "text_value", "is_correct", "comment")
_ANSWER_HASH_FIELDS = frozenset(
    {"sequence", "text_value", "is_correct", "comment", "question_id"}
)


def _field_hash_payload(record, field_name):
    """Return a language-independent, deterministic payload for one field."""
    field = record._fields[field_name]

    # Odoo stores translated textual fields as their complete JSONB translation
    # mapping. Hash that canonical mapping instead of the caller-language value.
    if field.translate and field.store:
        translations = field._get_stored_translations(record) or {}
        return json.dumps(
            translations,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    value = record[field_name]
    if field.type == "many2one":
        return str(value.id if value else 0).encode("ascii")
    if isinstance(value, bytes):
        return value
    return str(value or "").encode("utf-8")


def _update_hash_fields(digest, record, field_names):
    for field_name in field_names:
        digest.update(field_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_field_hash_payload(record, field_name))
        digest.update(b"\0")


def _update_quiz_hash(digest, slide):
    """Add the complete learner-visible quiz payload in deterministic order."""
    questions = (
        slide.env["slide.question"]
        .sudo()
        .search([("slide_id", "=", slide.id)], order="sequence, id")
    )
    digest.update(b"quiz_payload\0")
    for question in questions:
        digest.update(b"question\0")
        _update_hash_fields(digest, question, _QUESTION_HASH_FIELD_ORDER)
        answers = question.answer_ids.sudo().sorted(
            key=lambda answer: (answer.sequence, answer.id)
        )
        for answer in answers:
            digest.update(b"answer\0")
            _update_hash_fields(digest, answer, _ANSWER_HASH_FIELD_ORDER)
        digest.update(b"end_question\0")
    digest.update(b"end_quiz_payload\0")


def _slide_hash(slide):
    """Hash reviewed content, translations, course scope and quiz payload."""
    slide.ensure_one()
    digest = hashlib.sha256()
    _update_hash_fields(digest, slide, _CONTENT_HASH_FIELD_ORDER)
    _update_quiz_hash(digest, slide)
    return digest.hexdigest()


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
            if review.source_id.channel_id != review.slide_id.channel_id:
                raise ValidationError(
                    "The canonical source must belong to the reviewed content course."
                )
            if review.source_id.slide_id and review.source_id.slide_id != review.slide_id:
                raise ValidationError(
                    "The canonical source must point to the content being reviewed."
                )

    def _require_manager(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError("Only eLearning Managers can decide content reviews.")

    def _lock_pending_for_decision(self):
        self.check_access("write")
        records = self.try_lock_for_update()
        records.invalidate_recordset()
        if len(records) != len(self) or any(
            review.state != "pending" for review in records
        ):
            raise ValidationError(
                "Only available pending content reviews can be decided."
            )
        return records

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
        if self.source_id and (
            self.source_id.state != "imported"
            or self.source_id.slide_id != self.slide_id
        ):
            missing.append("canonical source imported for this content")
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
        with self.env.cr.savepoint():
            records = self._lock_pending_for_decision()
            records._check_source_consistency()
            for review in records:
                review._check_approval_evidence()
            reviewed_at = fields.Datetime.now()
            for review in records:
                super(ContentReview, review).write(
                    {
                        "state": "approved",
                        "content_hash": _slide_hash(review.slide_id),
                        "reviewed_by_id": self.env.user.id,
                        "reviewed_at": reviewed_at,
                    }
                )
                review.slide_id.write({"facodi_legacy_review_pending": False})
        return True

    def action_reject(self):
        self._require_manager()
        with self.env.cr.savepoint():
            records = self._lock_pending_for_decision()
            if any(not (review.decision_note or "").strip() for review in records):
                raise ValidationError(
                    "A decision note is required when rejecting content."
                )
            reviewed_at = fields.Datetime.now()
            for review in records:
                super(ContentReview, review).write(
                    {
                        "state": "rejected",
                        "content_hash": _slide_hash(review.slide_id),
                        "reviewed_by_id": self.env.user.id,
                        "reviewed_at": reviewed_at,
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
        return self.website_id or self.channel_id.website_id

    def _facodi_requires_review(self):
        return any(
            bool(
                slide._facodi_review_website()
                and slide._facodi_review_website().facodi_publication_review_enabled
            )
            for slide in self
        )

    def _facodi_has_approved_review(self):
        """Check only the approval marker with elevated read access.

        Content-review rows remain Manager-only. Officers may publish content they
        can edit after a Manager approval without gaining access to private review
        evidence.
        """
        self.ensure_one()
        return self.id in self._facodi_current_approved_slide_ids()

    def _facodi_current_approved_slide_ids(self):
        if not self:
            return set()
        current_hashes = {slide.id: _slide_hash(slide) for slide in self}
        approved_reviews = (
            self.env["facodi.learning.content.review"]
            .sudo()
            .search(
                [
                    ("slide_id", "in", list(current_hashes)),
                    ("state", "=", "approved"),
                ]
            )
        )
        return {
            review.slide_id.id
            for review in approved_reviews
            if review.content_hash == current_hashes.get(review.slide_id.id)
        }

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
        with self.env.cr.savepoint():
            records = super().create(vals_list)
            records._facodi_check_publication_review()
        return records

    def write(self, vals):
        guarded_fields = (
            _CONTENT_HASH_FIELDS | _PUBLICATION_FIELDS | _PUBLICATION_SCOPE_FIELDS
        )
        if not guarded_fields.intersection(vals):
            return super().write(vals)
        with self.env.cr.savepoint():
            result = super().write(vals)
            self._facodi_check_publication_review()
        return result

    def update_field_translations(self, field_name, translations, source_lang=""):
        if field_name not in _CONTENT_HASH_FIELDS:
            return super().update_field_translations(
                field_name,
                translations,
                source_lang=source_lang,
            )
        # Base Odoo updates the JSONB translation payload before it re-enters
        # write(). Start the savepoint here so a rejected public-content change
        # rolls back the translation SQL as well.
        with self.env.cr.savepoint():
            result = super().update_field_translations(
                field_name,
                translations,
                source_lang=source_lang,
            )
            self._facodi_check_publication_review()
        return result


class SlideQuestion(models.Model):
    _inherit = "slide.question"

    @api.model_create_multi
    def create(self, vals_list):
        with self.env.cr.savepoint():
            records = super().create(vals_list)
            records.mapped("slide_id")._facodi_check_publication_review()
        return records

    def write(self, vals):
        if not _QUESTION_HASH_FIELDS.intersection(vals):
            return super().write(vals)
        slides_before = self.mapped("slide_id")
        with self.env.cr.savepoint():
            result = super().write(vals)
            (slides_before | self.mapped("slide_id"))._facodi_check_publication_review()
        return result

    def unlink(self):
        slides = self.mapped("slide_id")
        with self.env.cr.savepoint():
            result = super().unlink()
            slides.exists()._facodi_check_publication_review()
        return result

    def update_field_translations(self, field_name, translations, source_lang=""):
        if field_name != "question":
            return super().update_field_translations(
                field_name,
                translations,
                source_lang=source_lang,
            )
        # The base method mutates the JSONB translation payload before it
        # re-enters write(); keep that mutation inside the governance savepoint.
        slides = self.mapped("slide_id")
        with self.env.cr.savepoint():
            result = super().update_field_translations(
                field_name,
                translations,
                source_lang=source_lang,
            )
            slides._facodi_check_publication_review()
        return result


class SlideAnswer(models.Model):
    _inherit = "slide.answer"

    @api.model_create_multi
    def create(self, vals_list):
        with self.env.cr.savepoint():
            records = super().create(vals_list)
            records.mapped("question_id.slide_id")._facodi_check_publication_review()
        return records

    def write(self, vals):
        if not _ANSWER_HASH_FIELDS.intersection(vals):
            return super().write(vals)
        slides_before = self.mapped("question_id.slide_id")
        with self.env.cr.savepoint():
            result = super().write(vals)
            (
                slides_before | self.mapped("question_id.slide_id")
            )._facodi_check_publication_review()
        return result

    def unlink(self):
        slides = self.mapped("question_id.slide_id")
        with self.env.cr.savepoint():
            result = super().unlink()
            slides.exists()._facodi_check_publication_review()
        return result

    def update_field_translations(self, field_name, translations, source_lang=""):
        if field_name not in {"text_value", "comment"}:
            return super().update_field_translations(
                field_name,
                translations,
                source_lang=source_lang,
            )
        slides = self.mapped("question_id.slide_id")
        with self.env.cr.savepoint():
            result = super().update_field_translations(
                field_name,
                translations,
                source_lang=source_lang,
            )
            slides._facodi_check_publication_review()
        return result


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    def write(self, vals):
        if "website_id" not in vals:
            return super().write(vals)
        with self.env.cr.savepoint():
            result = super().write(vals)
            self.mapped("slide_ids")._facodi_check_publication_review()
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

    def _facodi_backfill_legacy_publications(self):
        if not self:
            return
        website_by_id = {website.id: website for website in self}
        public_slides = self.env["slide.slide"].search(
            [
                "&",
                "|",
                ("is_published", "=", True),
                ("website_published", "=", True),
                "|",
                ("website_id", "in", self.ids),
                "&",
                ("website_id", "=", False),
                ("channel_id.website_id", "in", self.ids),
            ]
        )
        candidate_slides = self.env["slide.slide"]
        candidate_slides_by_website = {
            website_id: self.env["slide.slide"] for website_id in website_by_id
        }
        for slide in public_slides:
            review_website = slide._facodi_review_website()
            if (
                review_website
                and review_website.id in website_by_id
                and not slide.facodi_legacy_review_pending
            ):
                candidate_slides |= slide
                candidate_slides_by_website[review_website.id] |= slide
        approved_slide_ids = candidate_slides._facodi_current_approved_slide_ids()
        for candidate_slides in candidate_slides_by_website.values():
            slides_to_flag = candidate_slides.filtered(
                lambda slide: slide.id not in approved_slide_ids
            )
            if slides_to_flag:
                slides_to_flag.write({"facodi_legacy_review_pending": True})

    def write(self, vals):
        enabling = (
            "facodi_publication_review_enabled" in vals
            and vals["facodi_publication_review_enabled"]
        )
        disabled_before_ids = self.filtered(
            lambda website: not website.facodi_publication_review_enabled
        ).ids
        if (
            "facodi_publication_review_enabled" in vals
            and not vals["facodi_publication_review_enabled"]
            and not self.env.su
        ):
            raise AccessError(
                "FACODI publication review cannot be disabled through ordinary writes."
            )
        result = super().write(vals)
        if enabling and disabled_before_ids:
            self.browse(disabled_before_ids).filtered(
                "facodi_publication_review_enabled"
            )._facodi_backfill_legacy_publications()
        return result

    def action_facodi_enable_publication_review(self):
        for website in self:
            if not website.facodi_publication_review_enabled:
                website.write({"facodi_publication_review_enabled": True})
            else:
                website._facodi_backfill_legacy_publications()
        return True
