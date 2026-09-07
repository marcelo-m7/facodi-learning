from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


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
