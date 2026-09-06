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
        string="Curricular Unit",
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
    evaluation_version = fields.Char(readonly=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)

    _coverage_unique = models.Constraint(
        "unique(channel_id, curriculum_unit_id, coverage_type)",
        "This curriculum coverage relation already exists.",
    )

    @api.constrains("confidence")
    def _check_confidence(self):
        if any(not 0 <= coverage.confidence <= 1 for coverage in self):
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
    def _coverage_exists(
        self, channel_id, curriculum_unit_id, coverage_type, exclude_ids=None
    ):
        domain = [
            ("channel_id", "=", channel_id),
            ("curriculum_unit_id", "=", curriculum_unit_id),
            ("coverage_type", "=", coverage_type),
        ]
        if exclude_ids:
            domain.append(("id", "not in", exclude_ids))
        return bool(self.search_count(domain, limit=1))

    @api.model
    def _prepare_proposal_create_vals(self, vals_list, *, generated):
        identities = set()
        prepared = []
        for incoming_vals in vals_list:
            vals = dict(incoming_vals)
            if vals.get("state", "proposed") != "proposed" or any(
                vals.get(field_name)
                for field_name in ("reviewed_by_id", "reviewed_at")
            ):
                raise AccessError("Use the explicit curriculum coverage review actions.")

            if generated:
                vals["origin"] = "analysis"
            else:
                if (
                    vals.get("origin", "manual") != "manual"
                    or vals.get("evaluation_version")
                ):
                    raise AccessError(
                        "Generated curriculum coverage provenance is server-owned."
                    )
                vals["origin"] = "manual"
                vals["evaluation_version"] = False

            channel_id = vals.get("channel_id")
            curriculum_unit_id = vals.get("curriculum_unit_id")
            coverage_type = vals.get("coverage_type", "covers")
            identity = (channel_id, curriculum_unit_id, coverage_type)
            if identity in identities or self._coverage_exists(
                channel_id, curriculum_unit_id, coverage_type
            ):
                raise ValidationError(
                    "This curriculum coverage relation already exists."
                )
            identities.add(identity)

            vals.update(
                state="proposed",
                reviewed_by_id=False,
                reviewed_at=False,
            )
            prepared.append(vals)
        return prepared

    @api.model_create_multi
    def create(self, vals_list):
        prepared = self._prepare_proposal_create_vals(vals_list, generated=False)
        return super().create(prepared)

    @api.model
    def _create_generated(self, vals):
        prepared = self._prepare_proposal_create_vals([vals], generated=True)
        return super().create(prepared)

    def write(self, vals):
        protected = {
            "channel_id",
            "curriculum_unit_id",
            "coverage_type",
            "origin",
            "state",
            "evaluation_version",
            "reviewed_by_id",
            "reviewed_at",
        }
        if protected & vals.keys():
            raise AccessError("Use the explicit curriculum coverage review actions.")
        if any(coverage.origin == "analysis" for coverage in self):
            raise AccessError(
                "Generated curriculum coverage proposals are immutable evidence."
            )
        if any(coverage.state != "proposed" for coverage in self):
            raise AccessError("Reviewed curriculum coverage is historical evidence.")
        if vals.keys() - {"confidence", "evidence"}:
            raise AccessError("Unsupported direct curriculum coverage update.")
        return super().write(vals)

    def unlink(self):
        if any(
            coverage.state != "proposed" or coverage.origin != "manual"
            for coverage in self
        ):
            raise AccessError(
                "Reviewed and generated curriculum coverage is audit history."
            )
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
        super(FacodiLearningCurriculumCoverage, records).write(
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
