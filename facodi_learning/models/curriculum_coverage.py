from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FacodiLearningCurriculumCoverage(models.Model):
    _name = "facodi.learning.curriculum.coverage"
    _description = "FACODI Curriculum Coverage"
    _order = "create_date desc, id desc"

    channel_id = fields.Many2one(
        "slide.channel",
        required=True,
        ondelete="restrict",
        index=True,
        string="FACODI Course",
    )
    curriculum_unit_id = fields.Many2one(
        "facodi.learning.curriculum.unit",
        required=True,
        ondelete="restrict",
        index=True,
        string="Curriculum Unit",
    )
    coverage_type = fields.Selection(
        [
            ("covers", "Covers"),
            ("partial", "Partial"),
            ("supports", "Supports"),
            ("equivalent", "Equivalent"),
        ],
        required=True,
        default="covers",
        index=True,
    )
    confidence = fields.Float(digits=(5, 4))
    origin = fields.Selection(
        [("manual", "Manual"), ("analysis", "Analysis")],
        required=True,
        default="manual",
        index=True,
    )
    state = fields.Selection(
        [
            ("proposed", "Proposed"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        required=True,
        default="proposed",
        index=True,
    )
    evidence = fields.Json()
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    policy_version = fields.Char(readonly=True)
    decision_snapshot = fields.Json(readonly=True)

    _coverage_unique = models.Constraint(
        "unique(channel_id, curriculum_unit_id, coverage_type)",
        "This curriculum coverage relation already exists.",
    )

    @api.constrains("confidence")
    def _check_confidence(self):
        for coverage in self:
            if not 0 <= coverage.confidence <= 1:
                raise ValidationError("Confidence must be between zero and one.")

    def _is_manager(self):
        return self.env.uid == SUPERUSER_ID or self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        )

    def _check_manager(self):
        if not self._is_manager():
            raise AccessError(
                "Only eLearning Managers can review FACODI curriculum coverage."
            )

    @api.model
    def _prepare_create_vals(self, vals_list, *, generated):
        protected = (
            "reviewed_by_id",
            "reviewed_at",
            "policy_version",
            "decision_snapshot",
        )
        identities = set()
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            if vals.get("state", "proposed") != "proposed" or any(
                vals.get(field_name) for field_name in protected
            ):
                raise AccessError("Use the explicit curriculum coverage review actions.")

            if generated:
                vals["origin"] = "analysis"
            else:
                if vals.get("origin", "manual") != "manual":
                    raise AccessError("Generated curriculum coverage provenance is server-owned.")
                vals["origin"] = "manual"

            identity = (
                vals.get("channel_id"),
                vals.get("curriculum_unit_id"),
                vals.get("coverage_type", "covers"),
            )
            if identity in identities or self.search_count(
                [
                    ("channel_id", "=", identity[0]),
                    ("curriculum_unit_id", "=", identity[1]),
                    ("coverage_type", "=", identity[2]),
                ],
                limit=1,
            ):
                raise ValidationError("This curriculum coverage relation already exists.")
            identities.add(identity)
            vals.update(
                state="proposed",
                reviewed_by_id=False,
                reviewed_at=False,
                policy_version=False,
                decision_snapshot=False,
            )
            prepared.append(vals)
        return prepared

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(self._prepare_create_vals(vals_list, generated=False))

    @api.model
    def _create_generated(self, vals):
        prepared = self._prepare_create_vals([vals], generated=True)
        return super().create(prepared)

    def write(self, vals):
        protected = {
            "channel_id",
            "curriculum_unit_id",
            "coverage_type",
            "origin",
            "state",
            "reviewed_by_id",
            "reviewed_at",
            "policy_version",
            "decision_snapshot",
        }
        if protected & vals.keys():
            raise AccessError("Use the explicit curriculum coverage review actions.")
        if any(coverage.origin == "analysis" for coverage in self):
            raise AccessError("Generated curriculum coverage is immutable evidence.")
        if any(coverage.state != "proposed" for coverage in self):
            raise AccessError("Reviewed curriculum coverage is historical evidence.")
        return super().write(vals)

    def unlink(self):
        if any(
            coverage.state != "proposed" or coverage.origin != "manual"
            for coverage in self
        ):
            raise AccessError("Reviewed and generated curriculum coverage is audit history.")
        return super().unlink()

    def _review(self, state):
        if state not in {"approved", "rejected"}:
            raise ValidationError("Unsupported curriculum coverage review state.")
        self._check_manager()
        self.check_access("write")
        records = self.try_lock_for_update()
        records.invalidate_recordset()
        if len(records) != len(self) or any(
            coverage.state != "proposed" for coverage in records
        ):
            raise ValidationError(
                "Only available proposed curriculum coverage can be reviewed."
            )
        reviewed_at = fields.Datetime.now()
        for coverage in records:
            super(FacodiLearningCurriculumCoverage, coverage).write(
                {
                    "state": state,
                    "reviewed_by_id": self.env.uid,
                    "reviewed_at": reviewed_at,
                }
            )
        return True

    def action_approve(self):
        return self._review("approved")

    def action_reject(self):
        return self._review("rejected")
