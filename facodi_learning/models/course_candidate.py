from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..services.course_selection import (
    candidate_is_auto_approve_eligible,
    evaluate_course_candidate,
    get_course_selection_policy,
)


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
        identities = set()
        for vals in vals_list:
            if vals.keys() - self._source_fields:
                raise AccessError(
                    "Course candidates must be created from normalized source metadata."
                )
            if vals.get("requested_by_id", self.env.uid) != self.env.uid:
                raise AccessError("The candidate requester cannot be forged.")

            provider = (vals.get("provider") or "manual").strip()
            external_id = (vals.get("external_id") or "").strip()
            identity = (provider, external_id)
            if identity in identities or self.search_count(
                [("provider", "=", provider), ("external_id", "=", external_id)],
                limit=1,
            ):
                raise ValidationError(
                    "This external course candidate is already registered."
                )
            identities.add(identity)

            vals.update(
                provider=provider,
                external_id=external_id,
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
            if any(
                record.state not in {"discovered", "evaluated", "shortlisted"}
                for record in self
            ):
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
        if any(
            record.state in {"approved", "rejected", "resolved"} for record in self
        ):
            raise AccessError("Reviewed course candidates are audit history.")
        return super().unlink()

    def _is_manager(self):
        return self.env.uid == SUPERUSER_ID or self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        )

    def _is_officer_or_manager(self):
        return self._is_manager() or self.env.user.has_group(
            "website_slides.group_website_slides_officer"
        )

    def _decision_snapshot_for_policy(self, policy=None):
        self.ensure_one()
        policy = policy or get_course_selection_policy(self.env)
        return {
            "relevance_score": self.relevance_score,
            "metadata_quality_score": self.metadata_quality_score,
            "language_fit_score": self.language_fit_score,
            "coverage_score": self.coverage_score,
            "duplication_risk": self.duplication_risk,
            "recommendation": self.recommendation or False,
            "evaluation_policy_version": self.evaluation_policy_version or False,
            "selection_policy": {
                "mode": policy["mode"],
                "min_relevance": policy["min_relevance"],
                "min_metadata_quality": policy["min_metadata_quality"],
                "min_language_fit": policy["min_language_fit"],
                "min_coverage": policy["min_coverage"],
                "max_duplication_risk": policy["max_duplication_risk"],
                "languages": sorted(policy["languages"]),
                "trusted_providers": sorted(policy["trusted_providers"]),
                "policy_version": policy["policy_version"],
            },
        }

    def action_evaluate(self):
        policy = get_course_selection_policy(self.env)
        existing_channels = self.env["slide.channel"].search([])
        for candidate in self:
            if candidate.state in {"approved", "rejected", "resolved"}:
                raise ValidationError("Reviewed course candidates cannot be reevaluated.")
            result = evaluate_course_candidate(
                candidate, existing_channels, policy["languages"]
            )
            super(FacodiLearningCourseCandidate, candidate).write(
                {
                    "state": "evaluated",
                    "relevance_score": result["relevance_score"],
                    "metadata_quality_score": result["metadata_quality_score"],
                    "language_fit_score": result["language_fit_score"],
                    "coverage_score": result["coverage_score"],
                    "duplication_risk": result["duplication_risk"],
                    "recommendation": result["recommendation"],
                    "evaluation_reasons": result["reasons"],
                    "evaluation_policy_version": result["policy_version"],
                    "evaluated_at": fields.Datetime.now(),
                    "matched_channel_id": result["matched_channel_id"] or False,
                    "last_error": False,
                }
            )
            candidate._apply_selection_policy(policy)
        return True

    def _apply_selection_policy(self, policy=None):
        policy = policy or get_course_selection_policy(self.env)
        for candidate in self:
            if candidate.state != "evaluated":
                continue

            if policy["mode"] == "manual":
                continue

            if policy["mode"] == "assisted":
                if candidate.recommendation in {
                    "shortlist",
                    "review_existing_match",
                }:
                    super(FacodiLearningCourseCandidate, candidate).write(
                        {"state": "shortlisted"}
                    )
                continue

            eligible, _reasons = candidate_is_auto_approve_eligible(
                candidate, policy
            )
            if eligible and candidate._is_manager():
                candidate._resolve(
                    "new",
                    decision_origin="automatic",
                    policy_version=policy["policy_version"],
                    decision_snapshot=candidate._decision_snapshot_for_policy(policy),
                )
            elif candidate.recommendation in {
                "review",
                "shortlist",
                "review_existing_match",
            }:
                super(FacodiLearningCourseCandidate, candidate).write(
                    {"state": "shortlisted"}
                )
        return True

    def action_shortlist(self):
        if not self._is_officer_or_manager():
            raise AccessError("Only eLearning Officers or Managers can shortlist candidates.")
        for candidate in self:
            if candidate.state != "evaluated" or not candidate.evaluated_at:
                raise ValidationError("Evaluate the candidate before shortlisting it.")
            super(FacodiLearningCourseCandidate, candidate).write(
                {"state": "shortlisted", "last_error": False}
            )
        return True

    def action_reject(self):
        if not self._is_manager():
            raise AccessError("Only eLearning Managers can reject course candidates.")
        for candidate in self:
            locked = candidate.try_lock_for_update()
            if not locked:
                raise ValidationError(
                    "This candidate is being resolved; retry shortly."
                )
            candidate.invalidate_recordset()
            if candidate.state == "rejected":
                continue
            if candidate.state in {"approved", "resolved"}:
                raise ValidationError("This candidate already has a conflicting decision.")
            if not candidate.evaluated_at or candidate.state not in {
                "evaluated",
                "shortlisted",
            }:
                raise ValidationError("Evaluate the candidate before rejecting it.")
            policy = get_course_selection_policy(candidate.env)
            super(FacodiLearningCourseCandidate, candidate).write(
                {
                    "state": "rejected",
                    "resolved_channel_id": False,
                    "resolution_type": False,
                    "decision_origin": "manual",
                    "decision_policy_version": False,
                    "decision_at": fields.Datetime.now(),
                    "reviewed_by_id": candidate.env.uid,
                    "decision_snapshot": candidate._decision_snapshot_for_policy(policy),
                    "last_error": False,
                }
            )
        return True

    def action_resolve_new(self):
        if not self._is_manager():
            raise AccessError("Only eLearning Managers can resolve course candidates.")
        channels = self.env["slide.channel"]
        for candidate in self:
            channel = candidate._resolve("new", decision_origin="manual")
            if channel:
                channels |= channel
        return channels

    def action_resolve_existing(self):
        if not self._is_manager():
            raise AccessError("Only eLearning Managers can resolve course candidates.")
        channels = self.env["slide.channel"]
        for candidate in self:
            if not candidate.matched_channel_id:
                raise ValidationError("Choose an existing course before resolving.")
            channel = candidate._resolve(
                "existing",
                channel=candidate.matched_channel_id,
                decision_origin="manual",
            )
            if channel:
                channels |= channel
        return channels

    def _resolve(
        self,
        resolution_type,
        channel=None,
        decision_origin="manual",
        policy_version=None,
        decision_snapshot=None,
    ):
        self.ensure_one()
        if resolution_type not in {"existing", "new"}:
            raise ValidationError("Unsupported course resolution type.")
        if decision_origin not in {"manual", "automatic"}:
            raise ValidationError("Unsupported course decision origin.")
        if decision_origin == "manual" and not self._is_manager():
            raise AccessError("Only eLearning Managers can resolve course candidates.")
        if decision_origin == "automatic" and not self._is_manager():
            raise AccessError(
                "Automatic resolution requires the current eLearning Manager context."
            )

        if resolution_type == "existing":
            channel = channel.exists() if channel else self.env["slide.channel"]
            if len(channel) != 1:
                raise ValidationError("Choose one existing course before resolving.")
            channel.check_access("write")
        elif channel:
            raise ValidationError("A new-course resolution cannot reuse an existing course.")

        locked = self.try_lock_for_update()
        if not locked:
            raise ValidationError("This candidate is being resolved; retry shortly.")
        self.invalidate_recordset()

        if self.state == "resolved":
            same_resolution = self.resolution_type == resolution_type
            if resolution_type == "existing":
                same_resolution = same_resolution and self.resolved_channel_id == channel
            if same_resolution:
                return self.resolved_channel_id
            raise ValidationError("This candidate already has a conflicting resolution.")
        if self.state in {"approved", "rejected"}:
            raise ValidationError("This candidate already has a conflicting decision.")
        if not self.evaluated_at or self.state not in {"evaluated", "shortlisted"}:
            raise ValidationError("Evaluate the candidate before resolving it.")

        policy = get_course_selection_policy(self.env)
        if decision_origin == "automatic":
            eligible, reasons = candidate_is_auto_approve_eligible(self, policy)
            if not eligible:
                raise ValidationError(
                    "Candidate no longer satisfies Auto Approve guardrails: %s"
                    % "; ".join(reasons)
                )
            policy_version = policy["policy_version"]
        else:
            policy_version = False

        snapshot = decision_snapshot or self._decision_snapshot_for_policy(policy)
        try:
            with self.env.cr.savepoint():
                resolved_channel = channel
                if resolution_type == "new":
                    resolved_channel = self.env["slide.channel"].create(
                        {
                            "name": self.name,
                            "description": self.description or False,
                            "description_short": self.description or False,
                            "user_id": self.requested_by_id.id or self.env.uid,
                            "website_published": False,
                        }
                    )
                super(FacodiLearningCourseCandidate, self).write(
                    {
                        "state": "resolved",
                        "resolved_channel_id": resolved_channel.id,
                        "resolution_type": resolution_type,
                        "decision_origin": decision_origin,
                        "decision_policy_version": policy_version,
                        "decision_at": fields.Datetime.now(),
                        "reviewed_by_id": (
                            self.env.uid if decision_origin == "manual" else False
                        ),
                        "decision_snapshot": snapshot,
                        "last_error": False,
                    }
                )
            return resolved_channel
        except Exception as error:  # rollback canonical mutation, expose no provider details
            self.invalidate_recordset()
            super(FacodiLearningCourseCandidate, self).write(
                {
                    "last_error": (
                        f"{type(error).__name__}: operation failed; "
                        "inspect course selection configuration."
                    )
                }
            )
            return self.env["slide.channel"]
