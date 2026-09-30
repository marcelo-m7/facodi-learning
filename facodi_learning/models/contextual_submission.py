import hashlib
import re
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.tools import LazyTranslate
from odoo.exceptions import AccessError, ValidationError

from .submission import FacodiLearningSubmission as _BaseSubmission


_lt = LazyTranslate(__name__)


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


_SOURCE_CTA_LABELS = {
    "community_margin": _lt("Community margin"),
    "unit_resource_cta": _lt("Curricular unit resources"),
    "unit_correction_cta": _lt("Curricular unit provenance"),
    "roadmap_resource_cta": _lt("Roadmap resources"),
    "roadmap_correction_cta": _lt("Roadmap provenance"),
    "roadmaps_catalog_cta": _lt("Roadmaps catalogue"),
    "curricular_units_catalog_cta": _lt("Curricular units catalogue"),
    "curricular_units_empty_state": _lt("Curricular units · open shelf"),
    "module_resource_cta": _lt("Learning module resources"),
    "course_resource_cta": _lt("Course resources"),
    "course_contact_cta": _lt("Course contribution"),
    "course_catalog_cta": _lt("Course catalogue"),
    "course_gap": _lt("Course coverage gap"),
    "study_player_resource_cta": _lt("Lesson resources"),
    "study_player_correction_cta": _lt("Lesson problem report"),
    "study_player_question_cta": _lt("Lesson question"),
    "explore_empty_shelf": _lt("Explore empty shelf"),
    "explore_map_resource_cta": _lt("Explore learning map"),
    "area_resource_cta": _lt("Learning area resources"),
    "community_video_cta": _lt("Community videos"),
    "community_resource_cta": _lt("Community resource"),
    "portal_resource_cta": _lt("My FACODI"),
    "main_nav_contribute": _lt("Main navigation"),
    "faq_contribution_cta": _lt("FAQ contribution"),
    "faq_contact_cta": _lt("FAQ contact"),
    "forum_postit_contact_cta": _lt("Community notebook"),
    "community_collaboration_cta": _lt("Community collaboration"),
    "editorial_routes_contact_cta": _lt("Contact and contribute"),
    "ecosystem_contact_cta": _lt("FACODI ecosystem"),
    "ecosystem_resource_cta": _lt("Ecosystem contribution"),
    "institutional_contact_cta": _lt("FACODI project"),
    "cta_sheet_resource_cta": _lt("Shared learning notebook"),
    "contact_sheet_resource_cta": _lt("Contact page resource"),
    "contact_page": _lt("Contact FACODI"),
    "contribution_board_resource_cta": _lt("Contribution board"),
    "contribution_board_correction_cta": _lt("Contribution board correction"),
    "contribution_board_collaboration_cta": _lt("Contribution board collaboration"),
    "translation_correction_cta": _lt("Translation correction"),
    "folder_tabs_contribute": _lt("Learning navigation"),
    "course_showcase_contribute": _lt("Learning catalogue"),
    "closing_cta": _lt("Homepage closing call"),
    "submission_status_followup": _lt("Submission follow-up"),
    "legacy_submission_followup": _lt("Submission follow-up"),
    "my_submissions_new": _lt("My submissions"),
    "my_submissions_empty": _lt("My submissions empty state"),
}


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
    resource_type = fields.Selection(_RESOURCE_TYPES)
    resource_level = fields.Selection(_RESOURCE_LEVELS)
    permission_to_contact = fields.Boolean(default=False)

    @api.model
    def _facodi_source_cta_label(self, source_cta):
        source_cta = self._clean_context_slug(source_cta)
        if not source_cta:
            return ""
        label = _SOURCE_CTA_LABELS.get(source_cta)
        if label:
            return self.env._(label)
        return source_cta.replace("_", " ").replace("-", " ").title()

    def _facodi_contributor_context_rows(self, website=None):
        """Return a safe human-readable projection of captured contribution context.

        The private tracking page must not expose raw source_page_url values, tokens,
        internal notes or context records that are no longer publicly visible.
        """
        self.ensure_one()
        website = website or self.env["website"].get_current_website()
        rows = []

        def add(label, value, key):
            if value:
                rows.append({"label": label, "value": value, "key": key})

        submission_type_label = dict(
            self._fields["submission_type"]._description_selection(self.env)
        ).get(self.submission_type, self.submission_type)
        add(self.env._("Contribution type"), submission_type_label, "type")

        if self.source_cta:
            source_label = self._facodi_source_cta_label(self.source_cta)
            add(self.env._("Started from"), source_label, "source")

        if self.source_section:
            add(
                self.env._("Section"),
                self.source_section.replace("-", " ").replace("_", " ").title(),
                "section",
            )

        if self.area_tag_id and self.area_tag_id.group_id.website_published:
            public_course = self.env["slide.channel"].sudo().search_count(
                [
                    ("active", "=", True),
                    ("website_published", "=", True),
                    ("visibility", "=", "public"),
                    ("tag_ids", "in", [self.area_tag_id.id]),
                    "|",
                    ("website_id", "=", False),
                    ("website_id", "=", website.id),
                ],
                limit=1,
            )
            if public_course:
                add(self.env._("Learning area"), self.area_tag_id.name, "area")

        if self.curriculum_unit_id and self.curriculum_unit_id._facodi_public_path():
            add(
                self.env._("Curricular unit"),
                self.curriculum_unit_id.name,
                "unit",
            )

        if (
            self.roadmap_id
            and self.roadmap_id.website_published
            and self.roadmap_id.validated_at
        ):
            add(self.env._("Roadmap"), self.roadmap_id.display_name, "roadmap")

        if self.module_id and self.module_id._facodi_public_path():
            add(self.env._("Learning module"), self.module_id.name, "module")

        if (
            self.course_id
            and self.course_id.active
            and self.course_id.website_published
            and self.course_id.visibility == "public"
            and (not self.course_id.website_id or self.course_id.website_id == website)
        ):
            add(self.env._("Course"), self.course_id.name, "course")

        if (
            self.suggested_slide_id
            and self.suggested_slide_id.active
            and self.suggested_slide_id.website_published
            and self.suggested_slide_id.channel_id.active
            and self.suggested_slide_id.channel_id.website_published
            and self.suggested_slide_id.channel_id.visibility == "public"
            and (
                not self.suggested_slide_id.channel_id.website_id
                or self.suggested_slide_id.channel_id.website_id == website
            )
        ):
            add(
                self.env._("Learning item"),
                self.suggested_slide_id.name,
                "slide",
            )

        if self.submission_type == "resource":
            resource_type_label = dict(
                self._fields["resource_type"]._description_selection(self.env)
            ).get(self.resource_type, self.resource_type)
            resource_level_label = dict(
                self._fields["resource_level"]._description_selection(self.env)
            ).get(self.resource_level, self.resource_level)
            add(self.env._("Resource type"), resource_type_label, "resource_type")
            add(self.env._("Level"), resource_level_label, "resource_level")
            if self.language:
                add(self.env._("Language"), self.language.upper(), "language")
        elif self.submission_type == "contact":
            contact_topic_label = dict(
                self._fields["contact_topic"]._description_selection(self.env)
            ).get(self.contact_topic, self.contact_topic)
            add(self.env._("Contact topic"), contact_topic_label, "contact_topic")

        return rows

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
