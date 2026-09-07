from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..services.course_discovery import normalize_discovery_item


class FacodiLearningDiscoveryRun(models.Model):
    _name = "facodi.learning.discovery.run"
    _description = "FACODI Course Discovery Run"
    _order = "create_date desc, id desc"

    provider = fields.Char(required=True, index=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        required=True,
        default="pending",
        readonly=True,
        index=True,
    )
    requested_by_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    items_seen = fields.Integer(readonly=True)
    candidates_created = fields.Integer(readonly=True)
    candidates_refreshed = fields.Integer(readonly=True)
    candidates_ignored = fields.Integer(readonly=True)
    last_error = fields.Text(readonly=True)

    _AUDIT_FIELDS = {
        "state",
        "requested_by_id",
        "started_at",
        "completed_at",
        "items_seen",
        "candidates_created",
        "candidates_refreshed",
        "candidates_ignored",
        "last_error",
    }

    @api.model
    def _manual_discovery_provider(self, run, limit):
        return []

    @api.model
    def _get_course_discovery_registry(self):
        return {"manual": self._manual_discovery_provider}

    def _is_manager(self):
        return self.env.uid == SUPERUSER_ID or self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        )

    def _check_manager(self):
        if not self._is_manager():
            raise AccessError("Only eLearning Managers can operate discovery runs.")

    def _write_execution(self, values):
        """Server-only audit write boundary."""
        return models.Model.write(self, values)

    @api.model
    def _discovery_batch_size(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("facodi_learning.discovery_batch_size", "20")
        )
        try:
            return max(1, min(int(raw), 100))
        except (TypeError, ValueError):
            return 20

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            if self._AUDIT_FIELDS & vals.keys():
                raise AccessError("Discovery run execution evidence is server-owned.")
            provider = vals.get("provider")
            if not isinstance(provider, str) or not provider.strip():
                raise ValidationError("Discovery provider is required.")
            vals.update(
                provider=provider.strip(),
                state="pending",
                requested_by_id=self.env.uid,
                started_at=False,
                completed_at=False,
                items_seen=0,
                candidates_created=0,
                candidates_refreshed=0,
                candidates_ignored=0,
                last_error=False,
            )
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if self._AUDIT_FIELDS & vals.keys():
            raise AccessError("Discovery run execution evidence is server-owned.")
        if "provider" in vals:
            provider = vals.get("provider")
            if not isinstance(provider, str) or not provider.strip():
                raise ValidationError("Discovery provider is required.")
            if any(run.state != "pending" for run in self):
                raise AccessError("Only pending discovery runs can change provider.")
            vals = dict(vals, provider=provider.strip())
        return super().write(vals)

    def unlink(self):
        if any(run.state != "pending" for run in self):
            raise AccessError("Completed discovery execution history cannot be deleted.")
        return super().unlink()

    def action_process(self):
        self._check_manager()
        self.check_access("write")
        Candidate = self.env["facodi.learning.course.candidate"]

        for run in self:
            locked = run.try_lock_for_update()
            if not locked:
                raise ValidationError("This discovery run is already being processed. Please retry.")
            locked.invalidate_recordset()
            if locked.state != "pending":
                raise ValidationError("Only pending discovery runs can be processed.")

            started_at = fields.Datetime.now()
            locked._write_execution(
                {
                    "state": "processing",
                    "started_at": started_at,
                    "completed_at": False,
                    "items_seen": 0,
                    "candidates_created": 0,
                    "candidates_refreshed": 0,
                    "candidates_ignored": 0,
                    "last_error": False,
                }
            )

            registry = locked._get_course_discovery_registry()
            provider = registry.get(locked.provider)
            if not callable(provider):
                locked._write_execution(
                    {
                        "state": "failed",
                        "completed_at": fields.Datetime.now(),
                        "last_error": "ValidationError: discovery provider is not registered.",
                    }
                )
                continue

            counts = {"seen": 0, "created": 0, "refreshed": 0, "ignored": 0}
            try:
                with self.env.cr.savepoint():
                    for item in provider(locked, locked._discovery_batch_size()):
                        counts["seen"] += 1
                        try:
                            normalized = normalize_discovery_item(locked.provider, item)
                        except (TypeError, ValueError):
                            counts["ignored"] += 1
                            continue

                        candidate, outcome = Candidate._upsert_from_discovery(
                            normalized, locked
                        )
                        counts[outcome] += 1
                        if outcome in {"created", "refreshed"}:
                            candidate.action_evaluate()
            except Exception as error:
                locked.invalidate_recordset()
                locked._write_execution(
                    {
                        "state": "failed",
                        "completed_at": fields.Datetime.now(),
                        "items_seen": counts["seen"],
                        "candidates_created": 0,
                        "candidates_refreshed": 0,
                        "candidates_ignored": counts["ignored"],
                        "last_error": (
                            f"{type(error).__name__}: discovery provider failed; "
                            "inspect provider configuration."
                        ),
                    }
                )
                continue

            locked._write_execution(
                {
                    "state": "completed",
                    "completed_at": fields.Datetime.now(),
                    "items_seen": counts["seen"],
                    "candidates_created": counts["created"],
                    "candidates_refreshed": counts["refreshed"],
                    "candidates_ignored": counts["ignored"],
                    "last_error": False,
                }
            )
        return True
