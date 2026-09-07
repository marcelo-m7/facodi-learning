from odoo import fields, models
from odoo.exceptions import ValidationError


class FacodiLearningCourseCandidateDiscovery(models.Model):
    _inherit = "facodi.learning.course.candidate"

    discovered_at = fields.Datetime(readonly=True, index=True)
    last_discovered_at = fields.Datetime(readonly=True, index=True)
    last_discovery_run_id = fields.Many2one(
        "facodi.learning.discovery.run",
        readonly=True,
        ondelete="restrict",
        index=True,
    )

    def _write_discovery_values(self, values):
        """Server-only write boundary for discovery metadata and audit evidence."""
        return models.Model.write(self, values)

    @classmethod
    def _discovery_source_fields(cls):
        return {
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

    def _upsert_from_discovery(self, normalized, discovery_run):
        """Create/refresh one candidate without rewriting terminal decisions."""
        if not isinstance(normalized, dict):
            raise ValidationError("Normalized discovery data must be a dictionary.")
        discovery_run.ensure_one()

        provider = normalized.get("provider")
        external_id = normalized.get("external_id")
        if provider != discovery_run.provider:
            raise ValidationError("Discovery provider identity does not match the run.")

        Candidate = self.env["facodi.learning.course.candidate"]
        candidate = Candidate.search(
            [("provider", "=", provider), ("external_id", "=", external_id)],
            limit=1,
        )
        if candidate and candidate.state in {"approved", "rejected", "resolved"}:
            return candidate, "ignored"

        now = fields.Datetime.now()
        source_values = {
            field_name: normalized.get(field_name, False)
            for field_name in self._discovery_source_fields()
        }

        if not candidate:
            candidate = Candidate.create(
                {
                    "provider": provider,
                    "external_id": external_id,
                    **source_values,
                }
            )
            candidate._write_discovery_values(
                {
                    "discovered_at": now,
                    "last_discovered_at": now,
                    "last_discovery_run_id": discovery_run.id,
                }
            )
            return candidate, "created"

        candidate._write_discovery_values(
            {
                **source_values,
                "last_discovered_at": now,
                "last_discovery_run_id": discovery_run.id,
            }
        )
        return candidate, "refreshed"
