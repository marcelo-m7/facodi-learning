import hashlib
import re
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .submission import FacodiLearningSubmission as _BaseSubmission


_CONTEXT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_VALID_SUBMISSION_TYPES = {"resource", "contact", "correction", "question"}
_RESOURCE_TYPES = [
    ("video", "Video"),
    ("article", "Article"),
    ("book", "Book"),
    ("tool", "Tool"),
    ("repository", "Repository"),
    ("course", "External Course"),
    ("other", "Other"),
]
_RESOURCE_LEVELS = [
    ("introductory", "Introductory"),
    ("intermediate", "Intermediate"),
    ("advanced", "Advanced"),
]
_CONTACT_TOPICS = [
    ("collaboration", "Collaboration"),
    ("partnership", "Partnership"),
    ("content", "Content / editorial"),
    ("technical", "Technical issue"),
    ("accessibility", "Accessibility"),
    ("other", "Other"),
]


class FacodiLearningSubmissionContext(models.Model):
    _inherit = "facodi.learning.submission"

    source_url = fields.Char(required=False, index=True)
    submission_type = fields.Selection(
        [
            ("resource", "Learning resource"),
            ("contact", "Contact"),
            ("correction", "Correction"),
            ("question", "Question"),
        ],
        required=True,
        default="resource",
        index=True,
    )
    source_cta = fields.Char(index=True)
    source_section = fields.Char(index=True)
    source_page_url = fields.Char()
    area_tag_id = fields.Many2one(
        "slide.channel.tag",
        string="Learning Area Context",
        ondelete="set null",
        index=True,
    )
    roadmap_id = fields.Many2one(
        "facodi.learning.curriculum.reference",
        string="Roadmap Context",
        ondelete="set null",
        index=True,
    )
    module_id = fields.Many2one(
        "facodi.learning.curriculum.module",
        string="Learning Module Context",
        ondelete="set null",
        index=True,
    )
    course_id = fields.Many2one(
        "slide.channel",
        string="Course Context",
        ondelete="set null",
        index=True,
    )
    suggested_slide_id = fields.Many2one(
        "slide.slide",
        string="Learning Item Context",
        ondelete="set null",
        index=True,
    )
    contact_name = fields.Char()
    contact_email = fields.Char(index=True)
    organization = fields.Char()
    contact_topic = fields.Selection(_CONTACT_TOPICS, string="Contact Topic", index=True)
    resource_type = fields.Selection(_RESOURCE_TYPES, default="video")
    resource_level = fields.Selection(_RESOURCE_LEVELS)
    permission_to_contact = fields.Boolean(default=False)

    @api.model
    def _normalize_submission_type(self, value):
        candidate = (value or "resource").strip().lower()
        return candidate if candidate in _VALID_SUBMISSION_TYPES else "resource"

    @api.model
    def _is_valid_context_slug(self, value):
        if not value:
            return True
        return bool(_CONTEXT_SLUG_RE.match((value or "").strip().lower()))

    @api.model
    def _clean_context_slug(self, value):
        cleaned = (value or "").strip().lower()[:64]
        return cleaned if self._is_valid_context_slug(cleaned) else ""

    @api.model
    def _clean_source_page_url(self, value):
        candidate = (value or "").strip()
        if not candidate or candidate.startswith("//") or "\\" in candidate:
            return ""
        parsed = urlsplit(candidate)
        if parsed.scheme or parsed.netloc:
            return ""
        path = parsed.path or "/"
        if not path.startswith("/"):
            return ""
        return path[:2048]

    @api.constrains("source_url", "submission_type")
    def _check_source_url(self):
        for record in self:
            if record.submission_type == "resource" and not self._is_valid_source_url(record.source_url):
                raise ValidationError("Enter a valid public HTTP or HTTPS URL.")

    @api.constrains("source_cta", "source_section")
    def _check_context_slugs(self):
        for record in self:
            if not self._is_valid_context_slug(record.source_cta):
                raise ValidationError("The CTA context is not valid.")
            if not self._is_valid_context_slug(record.source_section):
                raise ValidationError("The section context is not valid.")

    @api.model
    def _contextual_identity_key(self, source_url, curriculum_unit_id=False, module_id=False):
        normalized = self._normalize_source_url(source_url)
        payload = "%s\x1f%s\x1f%s" % (
            normalized,
            int(curriculum_unit_id or 0),
            int(module_id or 0),
        )
        raw = int.from_bytes(
            hashlib.blake2b(payload.encode("utf-8"), digest_size=8).digest(),
            byteorder="big",
            signed=False,
        )
        return raw - (1 << 64) if raw >= (1 << 63) else raw

    @api.model
    def _lock_contextual_identity(self, source_url, curriculum_unit_id=False, module_id=False):
        key = self._contextual_identity_key(source_url, curriculum_unit_id, module_id)
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [key])

    @api.model
    def _contextual_duplicate(
        self,
        source_url,
        curriculum_unit_id=False,
        module_id=False,
        exclude_id=False,
    ):
        domain = [
            ("normalized_source_url", "=", self._normalize_source_url(source_url)),
            ("state", "in", ("submitted", "reviewing", "changes_requested", "accepted")),
            ("curriculum_unit_id", "=", curriculum_unit_id or False),
            ("module_id", "=", module_id or False),
        ]
        if exclude_id:
            domain.append(("id", "!=", exclude_id))
        return self.search(domain, limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        cleaned_vals_list = []
        resource_identities = []
        for raw_vals in vals_list:
            vals = dict(raw_vals)
            vals["submission_type"] = self._normalize_submission_type(vals.get("submission_type"))
            vals["source_cta"] = self._clean_context_slug(vals.get("source_cta"))
            vals["source_section"] = self._clean_context_slug(vals.get("source_section"))
            vals["permission_to_contact"] = bool(vals.get("permission_to_contact"))
            if vals.get("language"):
                vals["language"] = vals["language"].strip().lower()[:16]
            if vals.get("contact_email"):
                vals["contact_email"] = vals["contact_email"].strip().lower()[:254]
            vals["source_page_url"] = self._clean_source_page_url(
                vals.get("source_page_url")
            ) or False
            if vals["submission_type"] == "resource":
                vals["source_url"] = (vals.get("source_url") or "").strip()[:2048]
                resource_identities.append(
                    (
                        vals["source_url"],
                        vals.get("curriculum_unit_id") or False,
                        vals.get("module_id") or False,
                    )
                )
            else:
                vals["source_url"] = (vals.get("source_url") or "").strip()[:2048]
            cleaned_vals_list.append(vals)

        seen_identity_keys = set()
        for source_url, curriculum_unit_id, module_id in sorted(
            resource_identities,
            key=lambda item: self._contextual_identity_key(item[0], item[1], item[2]),
        ):
            identity_key = self._contextual_identity_key(
                source_url,
                curriculum_unit_id,
                module_id,
            )
            if identity_key in seen_identity_keys:
                raise ValidationError(
                    "This resource is already under editorial review for this context."
                )
            seen_identity_keys.add(identity_key)
            self._lock_contextual_identity(source_url, curriculum_unit_id, module_id)
            if self._contextual_duplicate(source_url, curriculum_unit_id, module_id):
                raise ValidationError(
                    "This resource is already under editorial review for this context."
                )

        for vals in cleaned_vals_list:
            forged = self._audit_fields & vals.keys()
            if forged:
                raise AccessError(
                    "Submission audit state is managed by FACODI review actions."
                )
            vals.update(
                state="submitted",
                access_token=self._new_access_token(),
                reviewed_by_id=False,
                reviewed_at=False,
            )
            if vals.get("name"):
                vals["name"] = vals["name"].strip()[:200]
            if vals.get("context"):
                vals["context"] = vals["context"].strip()[:4000]
        return super(_BaseSubmission, self).create(cleaned_vals_list)
