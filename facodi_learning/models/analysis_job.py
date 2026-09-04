import logging

from odoo import api, fields, models

from ..services import analyze_local_metadata

_logger = logging.getLogger(__name__)


class FacodiLearningAnalysisJob(models.Model):
    _name = "facodi.learning.analysis.job"
    _description = "FACODI Learning Analysis Job"
    _order = "create_date desc, id desc"

    slide_id = fields.Many2one(
        "slide.slide", required=True, ondelete="cascade", index=True, string="Content"
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        required=True,
        default="pending",
        index=True,
    )
    provider = fields.Char(required=True, default="local_metadata", index=True)
    model_name = fields.Char(readonly=True)
    requested_by_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, readonly=True
    )
    attempt_count = fields.Integer(default=0, readonly=True)
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)
    result_id = fields.Many2one(
        "facodi.learning.analysis.result", readonly=True, ondelete="set null"
    )

    def _get_provider_registry(self):
        """Extension point for provider addons.

        Provider addons should inherit this model, call ``super()``, and update
        the returned mapping with their own normalized adapter callable.
        """
        return {
            "local_metadata": analyze_local_metadata,
        }

    def action_process(self):
        Result = self.env["facodi.learning.analysis.result"]
        for job in self:
            if job.state == "completed":
                continue

            job.write({
                "state": "processing",
                "attempt_count": job.attempt_count + 1,
                "started_at": fields.Datetime.now(),
                "completed_at": False,
                "last_error": False,
            })
            try:
                provider = job._get_provider_registry().get(job.provider)
                if not provider:
                    raise ValueError(f"Unknown analysis provider: {job.provider}")

                with self.env.cr.savepoint():
                    normalized = provider(job.slide_id)
                    result = Result.create({
                        "job_id": job.id,
                        "slide_id": job.slide_id.id,
                        "provider": job.provider,
                        "model_name": normalized.get("model_name"),
                        "summary": normalized.get("summary"),
                        "detected_language": normalized.get("detected_language"),
                        "suggested_tag_ids": [(6, 0, normalized.get("suggested_tag_ids", []))],
                        "raw_payload": normalized.get("raw_payload") or {},
                    })
                job.write({
                    "state": "completed",
                    "completed_at": fields.Datetime.now(),
                    "model_name": result.model_name,
                    "result_id": result.id,
                })
            except Exception as exc:  # provider boundary: preserve content and job history
                _logger.exception("FACODI analysis job %s failed", job.id)
                job.write({
                    "state": "failed",
                    "completed_at": fields.Datetime.now(),
                    "last_error": str(exc)[:2000],
                })
        return True

    def action_retry(self):
        for job in self:
            if job.state == "failed":
                job.write({
                    "state": "pending",
                    "started_at": False,
                    "completed_at": False,
                    "last_error": False,
                    "result_id": False,
                })
        return True

    @api.model
    def _cron_process_pending_jobs(self):
        parameter = self.env["ir.config_parameter"].sudo().get_param(
            "facodi_learning.analysis_batch_size", "10"
        )
        try:
            batch_size = max(1, min(int(parameter), 100))
        except (TypeError, ValueError):
            batch_size = 10

        jobs = self.search([("state", "=", "pending")], limit=batch_size, order="id")
        jobs.action_process()

        # Odoo 19's native cron progress API is used when this method executes
        # inside a scheduled-action worker.  Direct calls (tests/manual RPC) do
        # not need to manufacture cron context.
        if self.env.context.get("cron_id"):
            remaining = self.search_count([("state", "=", "pending")])
            self.env["ir.cron"]._commit_progress(len(jobs), remaining=remaining)
        return True
