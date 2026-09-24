import ipaddress
import secrets
from urllib.parse import urlsplit, urlunsplit

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


def _is_public_http_url(value):
    try:
        parsed = urlsplit((value or "").strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False

    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        return False
    if parsed.username or parsed.password:
        return False

    normalized_host = hostname.lower().rstrip(".")
    if normalized_host == "localhost":
        return False

    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        address = None

    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False

    return port is None or 0 < port <= 65535


class FacodiLearningSubmission(models.Model):
    _name = "facodi.learning.submission"
    _description = "FACODI learning resource submission"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    source_url = fields.Char(required=True, index=True)
    context = fields.Text()
    language = fields.Char(index=True)
    curriculum_unit_id = fields.Many2one(
        "facodi.learning.curriculum.unit",
        string="Curricular Unit Context",
        ondelete="set null",
        index=True,
        help=(
            "Optional contributor context only. This relation does not create "
            "curriculum coverage or an approved academic mapping."
        ),
    )
    normalized_source_url = fields.Char(
        compute="_compute_normalized_source_url",
        store=True,
        index=True,
        readonly=True,
    )
    submitted_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        ondelete="set null",
        index=True,
    )
    state = fields.Selection(
        [
            ("submitted", "Submitted"),
            ("reviewing", "Reviewing"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("resolved", "Resolved"),
        ],
        required=True,
        default="submitted",
        readonly=True,
        index=True,
    )
    access_token = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )
    reviewed_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        ondelete="set null",
    )
    reviewed_at = fields.Datetime(readonly=True)
    decision_note = fields.Text(
        help="Internal editorial note. Never render this field on public status pages."
    )
    candidate_id = fields.Many2one(
        "facodi.learning.course.candidate",
        string="Course Candidate",
        ondelete="restrict",
    )
    source_id = fields.Many2one(
        "facodi.learning.source",
        string="Canonical Source",
        ondelete="restrict",
    )

    _token_unique = models.Constraint(
        "unique(access_token)",
        "Submission tracking tokens must be unique.",
    )

    _audit_fields = {
        "state",
        "access_token",
        "reviewed_by_id",
        "reviewed_at",
    }

    @api.model
    def _new_access_token(self):
        return secrets.token_urlsafe(32)

    @api.model
    def _is_valid_source_url(self, value):
        return _is_public_http_url(value)

    @api.model
    def _normalize_source_url(self, value):
        raw = (value or "").strip()
        if not _is_public_http_url(raw):
            return ""
        parsed = urlsplit(raw)
        hostname = (parsed.hostname or "").lower()
        try:
            port = parsed.port
        except ValueError:
            return ""
        if port and not (
            (parsed.scheme.lower() == "http" and port == 80)
            or (parsed.scheme.lower() == "https" and port == 443)
        ):
            hostname = f"{hostname}:{port}"
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/") or "/"
        return urlunsplit(
            (
                parsed.scheme.lower(),
                hostname,
                path,
                parsed.query,
                "",
            )
        )

    @api.depends("source_url")
    def _compute_normalized_source_url(self):
        for submission in self:
            submission.normalized_source_url = self._normalize_source_url(
                submission.source_url
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
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
                vals["name"] = vals["name"].strip()
            if vals.get("source_url"):
                vals["source_url"] = vals["source_url"].strip()
            if vals.get("language"):
                vals["language"] = vals["language"].strip().lower()
        return super().create(vals_list)

    def write(self, vals):
        protected = self._audit_fields | {"submitted_by_id"}
        if protected & vals.keys():
            raise AccessError(
                "Submission audit state is managed by FACODI review actions."
            )
        if any(record.state in {"rejected", "resolved"} for record in self):
            raise AccessError("Terminal submissions are audit history.")
        return super().write(vals)

    def unlink(self):
        self._require_manager()
        if any(record.state != "submitted" for record in self):
            raise AccessError("Reviewed submissions are audit history.")
        return super().unlink()

    @api.constrains("name")
    def _check_name(self):
        if any(not (record.name or "").strip() for record in self):
            raise ValidationError("A submission title is required.")

    @api.constrains("source_url")
    def _check_source_url(self):
        if any(not _is_public_http_url(record.source_url) for record in self):
            raise ValidationError("Enter a valid public HTTP or HTTPS URL.")

    def _require_manager(self):
        if not self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        ):
            raise AccessError(
                "Only eLearning Managers can make submission review decisions."
            )

    def action_start_review(self):
        self._require_manager()
        for submission in self:
            if submission.state != "submitted":
                raise ValidationError(
                    "Only submitted resources can enter editorial review."
                )
            super(FacodiLearningSubmission, submission).write(
                {"state": "reviewing"}
            )
        return True

    def action_accept(self):
        self._require_manager()
        now = fields.Datetime.now()
        for submission in self:
            if submission.state not in {"submitted", "reviewing"}:
                raise ValidationError(
                    "Only submitted or reviewing resources can be accepted."
                )
            super(FacodiLearningSubmission, submission).write(
                {
                    "state": "accepted",
                    "reviewed_by_id": self.env.user.id,
                    "reviewed_at": now,
                }
            )
        return True

    def action_reject(self):
        self._require_manager()
        now = fields.Datetime.now()
        for submission in self:
            if submission.state not in {"submitted", "reviewing"}:
                raise ValidationError(
                    "Only submitted or reviewing resources can be rejected."
                )
            super(FacodiLearningSubmission, submission).write(
                {
                    "state": "rejected",
                    "reviewed_by_id": self.env.user.id,
                    "reviewed_at": now,
                }
            )
        return True

    def action_handoff_candidate(self):
        self.ensure_one()
        self._require_manager()

        if self.state == "resolved" and self.candidate_id:
            candidate = self.candidate_id
        else:
            if self.state != "accepted":
                raise ValidationError(
                    "Accept the submission before routing it to the candidate pipeline."
                )
            if self.source_id:
                raise ValidationError(
                    "This submission is already linked to a canonical source."
                )

            Candidate = self.env["facodi.learning.course.candidate"]
            canonical_url = self.normalized_source_url or self.source_url
            candidate = self.candidate_id
            if not candidate:
                candidate = Candidate.search(
                    [
                        ("source_url", "in", [canonical_url, self.source_url]),
                        ("state", "!=", "rejected"),
                    ],
                    order="id",
                    limit=1,
                )

            if not candidate:
                metadata = {
                    "submission_id": self.id,
                    "submission_context": self.context or False,
                }
                institution = False
                if self.curriculum_unit_id:
                    metadata.update(
                        {
                            "curriculum_unit_id": self.curriculum_unit_id.id,
                            "curriculum_unit_code": (
                                self.curriculum_unit_id.external_unit_code
                            ),
                            "curriculum_reference_id": (
                                self.curriculum_unit_id.reference_id.id
                            ),
                        }
                    )
                    institution = self.curriculum_unit_id.reference_id.institution

                candidate = Candidate.create(
                    {
                        "provider": "facodi-submission",
                        "external_id": f"submission-{self.id}",
                        "source_url": canonical_url,
                        "name": self.name,
                        "description": self.context or False,
                        "institution": institution,
                        "language": self.language or False,
                        "metadata": metadata,
                    }
                )

            super(FacodiLearningSubmission, self).write(
                {
                    "candidate_id": candidate.id,
                    "state": "resolved",
                }
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Course Candidate",
            "res_model": "facodi.learning.course.candidate",
            "res_id": candidate.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_resolve(self):
        self._require_manager()
        for submission in self:
            if submission.state != "accepted":
                raise ValidationError(
                    "Only accepted submissions can be resolved."
                )
            if not submission.candidate_id and not submission.source_id:
                raise ValidationError(
                    "Link a canonical course candidate or content source before resolving."
                )
            super(FacodiLearningSubmission, submission).write(
                {"state": "resolved"}
            )
        return True
