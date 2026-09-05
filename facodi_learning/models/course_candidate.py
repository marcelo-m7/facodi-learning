from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FacodiLearningCourseCandidate(models.Model):
    _name = "facodi.learning.course.candidate"
    _description = "FACODI Course Candidate"
    _order = "create_date desc, id desc"

    provider = fields.Char(required=True, default="manual", index=True)
    external_id = fields.Char(required=True, index=True)
    source_url = fields.Char()
    name = fields.Char(required=True)
    description = fields.Text()
    institution = fields.Char()
    language = fields.Char(index=True)
    level = fields.Char()
    duration_minutes = fields.Integer()
    license_name = fields.Char()
    metadata = fields.Json()

    requested_by_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, readonly=True
    )
    state = fields.Selection(
        [
            ("discovered", "Discovered"),
            ("evaluated", "Evaluated"),
            ("shortlisted", "Shortlisted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("resolved", "Resolved"),
        ],
        required=True,
        default="discovered",
        readonly=True,
        index=True,
    )

    relevance_score = fields.Float(digits=(5, 4), readonly=True)
    metadata_quality_score = fields.Float(digits=(5, 4), readonly=True)
    language_fit_score = fields.Float(digits=(5, 4), readonly=True)
    coverage_score = fields.Float(digits=(5, 4), readonly=True)
    duplication_risk = fields.Float(digits=(5, 4), readonly=True)
    recommendation = fields.Selection(
        [
            ("ignore", "Ignore"),
            ("review", "Review"),
            ("shortlist", "Shortlist"),
            ("review_existing_match", "Review Existing Match"),
        ],
        readonly=True,
    )
    evaluation_reasons = fields.Json(readonly=True)
    evaluation_policy_version = fields.Char(readonly=True)
    evaluated_at = fields.Datetime(readonly=True)

    matched_channel_id = fields.Many2one("slide.channel", ondelete="set null")
    resolved_channel_id = fields.Many2one(
        "slide.channel", readonly=True, ondelete="restrict"
    )
    resolution_type = fields.Selection(
        [("existing", "Existing Course"), ("new", "New Draft Course")],
        readonly=True,
    )
    decision_origin = fields.Selection(
        [("manual", "Manual"), ("automatic", "Automatic")], readonly=True
    )
    decision_policy_version = fields.Char(readonly=True)
    decision_at = fields.Datetime(readonly=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    decision_snapshot = fields.Json(readonly=True)
    last_error = fields.Text(readonly=True)

    _identity_unique = models.Constraint(
        "unique(provider, external_id)",
        "This external course candidate is already registered.",
    )

    _source_fields = {
        "provider",
        "external_id",
        "source_url",
        "name",
        "description",
        "institution",
        "language",
        "level",
        "duration_minutes",
        "license_name",
        "metadata",
        "requested_by_id",
    }
    _metadata_fields = {
        "source_url",
        "name",
        "description",
        "institution",
        "language",
        "level",
        "duration_minutes",
        "license_name",
        "metadata",
    }
    _evaluation_fields = {
        "relevance_score",
        "metadata_quality_score",
        "language_fit_score",
        "coverage_score",
        "duplication_risk",
        "recommendation",
        "evaluation_reasons",
        "evaluation_policy_version",
        "evaluated_at",
    }
    _decision_fields = {
        "state",
        "resolved_channel_id",
        "resolution_type",
        "decision_origin",
        "decision_policy_version",
        "decision_at",
        "reviewed_by_id",
        "decision_snapshot",
        "last_error",
    }

    @api.constrains("provider", "external_id", "name")
    def _check_required_text(self):
        if any(
            not (record.provider or "").strip()
            or not (record.external_id or "").strip()
            or not (record.name or "").strip()
            for record in self
        ):
            raise ValidationError(
                "Provider, external identity and name must not be blank."
            )

    @api.constrains("duration_minutes")
    def _check_duration(self):
        if any(record.duration_minutes < 0 for record in self):
            raise ValidationError("Course duration cannot be negative.")

    @api.constrains(
        "relevance_score",
        "metadata_quality_score",
        "language_fit_score",
        "coverage_score",
        "duplication_risk",
    )
    def _check_scores(self):
        for record in self:
            for value in (
                record.relevance_score,
                record.metadata_quality_score,
                record.language_fit_score,
                record.coverage_score,
                record.duplication_risk,
            ):
                if not 0 <= value <= 1:
                    raise ValidationError(
                        "Course-selection scores must be between zero and one."
                    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.keys() - self._source_fields:
                raise AccessError(
                    "Course candidates must be created from normalized source metadata."
                )
            if vals.get("requested_by_id", self.env.uid) != self.env.uid:
                raise AccessError("The candidate requester cannot be forged.")
            vals.update(
                requested_by_id=self.env.uid,
                state="discovered",
                relevance_score=0.0,
                metadata_quality_score=0.0,
                language_fit_score=0.0,
                coverage_score=0.0,
                duplication_risk=0.0,
                recommendation=False,
                evaluation_reasons=False,
                evaluation_policy_version=False,
                evaluated_at=False,
                matched_channel_id=False,
                resolved_channel_id=False,
                resolution_type=False,
                decision_origin=False,
                decision_policy_version=False,
                decision_at=False,
                reviewed_by_id=False,
                decision_snapshot=False,
                last_error=False,
            )
        return super().create(vals_list)

    def write(self, vals):
        protected = {
            "provider",
            "external_id",
            "requested_by_id",
        } | self._evaluation_fields | self._decision_fields
        if protected & vals.keys():
            raise AccessError("Use FACODI course-selection actions to change evidence.")

        if "matched_channel_id" in vals:
            if not self.env.user.has_group(
                "website_slides.group_website_slides_manager"
            ):
                raise AccessError("Only eLearning Managers can choose course matches.")
            if any(record.state not in {"discovered", "evaluated", "shortlisted"} for record in self):
                raise AccessError("Resolved course matches are audit history.")

        if self._metadata_fields & vals.keys() and any(
            record.state not in {"discovered", "evaluated", "shortlisted"}
            for record in self
        ):
            raise AccessError("Reviewed course candidate metadata is audit history.")

        extra = vals.keys() - self._metadata_fields - {"matched_channel_id"}
        if extra:
            raise AccessError("Unsupported direct course candidate update.")
        return super().write(vals)

    def unlink(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError("Only eLearning Managers can remove course candidates.")
        if any(record.state in {"approved", "rejected", "resolved"} for record in self):
            raise AccessError("Reviewed course candidates are audit history.")
        return super().unlink()

    def action_evaluate(self):
        raise ValidationError("Evaluate the candidate before this action.")

    def action_shortlist(self):
        raise ValidationError("Evaluate the candidate before this action.")

    def action_reject(self):
        raise ValidationError("Evaluate the candidate before this action.")

    def action_resolve_new(self):
        raise ValidationError("Evaluate the candidate before this action.")

    def action_resolve_existing(self):
        raise ValidationError("Evaluate the candidate before this action.")

    def _resolve(
        self,
        resolution_type,
        channel=None,
        decision_origin="manual",
        policy_version=None,
        decision_snapshot=None,
    ):
        raise ValidationError("Evaluate the candidate before this action.")
