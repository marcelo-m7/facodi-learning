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
            ("withdrawn", "Withdrawn"),
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
    source_state = fields.Selection(
        related="source_id.state",
        string="Source Status",
        readonly=True,
        compute_sudo=True,
    )
    slide_id = fields.Many2one(
        related="source_id.slide_id",
        string="Learning Content",
        readonly=True,
        compute_sudo=True,
    )
    analysis_job_id = fields.Many2one(
        "facodi.learning.analysis.job",
        string="Analysis Job",
        compute="_compute_processing_trace",
        readonly=True,
        compute_sudo=True,
    )
    analysis_result_id = fields.Many2one(
        "facodi.learning.analysis.result",
        string="Analysis Result",
        compute="_compute_processing_trace",
        readonly=True,
        compute_sudo=True,
    )
    processing_state = fields.Selection(
        [
            ("not_queued", "Not Queued"),
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        string="Processing Status",
        compute="_compute_processing_trace",
        readonly=True,
        compute_sudo=True,
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

    @api.depends(
        "source_id",
        "source_id.slide_id",
        "source_id.slide_id.facodi_analysis_job_ids.state",
        "source_id.slide_id.facodi_analysis_job_ids.provider",
        "source_id.slide_id.facodi_analysis_job_ids.result_id",
    )
    def _compute_processing_trace(self):
        for submission in self:
            submission.analysis_job_id = False
            submission.analysis_result_id = False
            submission.processing_state = "not_queued"

            slide = submission.source_id.slide_id
            if not slide:
                continue

            jobs = slide.facodi_analysis_job_ids
            job = jobs.sorted(
                key=lambda item: item.id,
                reverse=True,
            )[:1]
            if not job:
                continue

            submission.analysis_job_id = job
            submission.analysis_result_id = job.result_id
            submission.processing_state = job.state

    def _link_canonical_source(self, source, candidate=None):
        """Link reviewed submission audit records to their canonical source.

        Candidate ingestion owns this transition. It is intentionally separate
        from ordinary editorial writes so resolved submissions remain immutable
        while downstream processing provenance can still be completed.
        """
        source = source.exists()
        if len(source) != 1:
            raise ValidationError("An existing canonical source is required.")

        candidate = candidate.exists() if candidate else source.candidate_id
        if candidate and len(candidate) != 1:
            raise ValidationError("An existing course candidate is required.")

        if candidate:
            expected = candidate._get_ingestion_identity()
            if (
                source.provider != expected["provider"]
                or source.external_id != expected["external_id"]
                or source.channel_id != candidate.resolved_channel_id
            ):
                raise ValidationError(
                    "Canonical source identity does not match the submission candidate."
                )

        locked = self.try_lock_for_update()
        locked.invalidate_recordset()
        if len(locked) != len(self):
            raise ValidationError(
                "This submission is being updated; retry shortly."
            )

        for submission in locked:
            if submission.state not in {"accepted", "resolved"}:
                raise ValidationError(
                    "Only accepted or resolved submissions can link a canonical source."
                )
            if candidate and submission.candidate_id != candidate:
                raise ValidationError(
                    "The canonical source does not belong to this submission candidate."
                )
            if submission.source_id:
                if submission.source_id != source:
                    raise ValidationError(
                        "This submission is already linked to another canonical source."
                    )
                continue
            super(FacodiLearningSubmission, submission).write(
                {"source_id": source.id}
            )
        return True

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
        if any(record.state in {"rejected", "resolved", "withdrawn"} for record in self):
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

    def _lock_for_state_transition(self):
        locked = self.try_lock_for_update()
        locked.invalidate_recordset()
        if len(locked) != len(self):
            raise ValidationError(
                "This submission is being updated; retry shortly."
            )
        return locked

    def _require_contributor(self, user):
        self.ensure_one()
        user = user.exists()
        if not user or self.submitted_by_id != user:
            raise AccessError("You can manage only your own submissions.")
        return True

    def action_update_by_contributor(self, user, values):
        self.ensure_one()
        submission = self._lock_for_state_transition()
        submission._require_contributor(user)
        if submission.state != "submitted":
            raise ValidationError(
                "Only submissions waiting for review can be edited."
            )

        allowed = {"name", "source_url", "context", "language"}
        unknown = set(values) - allowed
        if unknown:
            raise AccessError("Only contributor-editable fields may be changed.")

        cleaned = {}
        if "name" in values:
            cleaned["name"] = (values.get("name") or "").strip()[:200]
        if "source_url" in values:
            cleaned["source_url"] = (values.get("source_url") or "").strip()[:2048]
        if "context" in values:
            cleaned["context"] = (values.get("context") or "").strip()[:4000]
        if "language" in values:
            cleaned["language"] = (values.get("language") or "").strip().lower()[:16]

        if not cleaned.get("name", submission.name):
            raise ValidationError("A submission title is required.")
        if "source_url" in cleaned and not _is_public_http_url(cleaned["source_url"]):
            raise ValidationError("Enter a valid public HTTP or HTTPS URL.")

        super(FacodiLearningSubmission, submission).write(cleaned)
        return True

    def action_withdraw_by_contributor(self, user):
        self.ensure_one()
        submission = self._lock_for_state_transition()
        submission._require_contributor(user)
        if submission.state not in {"submitted", "reviewing"}:
            raise ValidationError(
                "Only pending or reviewing submissions can be withdrawn."
            )
        super(FacodiLearningSubmission, submission).write({"state": "withdrawn"})
        return True

    def _require_manager(self):
        if not self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        ):
            raise AccessError(
                "Only eLearning Managers can make submission review decisions."
            )

    def action_start_review(self):
        self._require_manager()
        locked = self._lock_for_state_transition()
        for submission in locked:
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
        locked = self._lock_for_state_transition()
        now = fields.Datetime.now()
        for submission in locked:
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
        locked = self._lock_for_state_transition()
        now = fields.Datetime.now()
        for submission in locked:
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
        submission = self._lock_for_state_transition()

        if submission.state == "resolved" and submission.candidate_id:
            candidate = submission.candidate_id
        else:
            if submission.state != "accepted":
                raise ValidationError(
                    "Accept the submission before routing it to the candidate pipeline."
                )
            if submission.source_id:
                raise ValidationError(
                    "This submission is already linked to a canonical source."
                )

            Candidate = self.env["facodi.learning.course.candidate"]
            canonical_url = submission.normalized_source_url or submission.source_url
            candidate = submission.candidate_id
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
                if submission.curriculum_unit_id:
                    metadata.update(
                        {
                            "curriculum_unit_id": submission.curriculum_unit_id.id,
                            "curriculum_unit_code": (
                                submission.curriculum_unit_id.external_unit_code
                            ),
                            "curriculum_reference_id": (
                                submission.curriculum_unit_id.reference_id.id
                            ),
                        }
                    )
                    institution = submission.curriculum_unit_id.reference_id.institution

                candidate = Candidate.create(
                    {
                        "provider": "facodi-submission",
                        "external_id": f"submission-{submission.id}",
                        "source_url": canonical_url,
                        "name": submission.name,
                        "description": submission.context or False,
                        "institution": institution,
                        "language": submission.language or False,
                        "metadata": metadata,
                    }
                )

            super(FacodiLearningSubmission, submission).write(
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
        locked = self._lock_for_state_transition()
        for submission in locked:
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
