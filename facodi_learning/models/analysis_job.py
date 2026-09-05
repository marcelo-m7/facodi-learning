import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError
from ..services.analysis import normalize_output

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

    attempt_ids = fields.One2many(
        "facodi.learning.analysis.attempt", "job_id", readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        allowed = {"slide_id", "provider", "requested_by_id"}
        for vals in vals_list:
            if (
                vals.keys() - allowed
                or vals.get("requested_by_id", self.env.uid) != self.env.uid
            ):
                raise AccessError(
                    "Only content and provider can be supplied for a new request."
                )
            vals.update(
                requested_by_id=self.env.uid,
                state="pending",
                attempt_count=0,
                result_id=False,
                started_at=False,
                completed_at=False,
                last_error=False,
                model_name=False,
                attempt_ids=[],
            )
        return super().create(vals_list)

    def write(self, vals):
        if vals.keys() - {"provider"} or any(job.state != "pending" for job in self):
            raise AccessError("Use job actions to change processing state.")
        return super().write(vals)

    def unlink(self):
        raise AccessError("Analysis jobs are audit history and cannot be deleted.")

    def action_process(self):
        if not self.env.su and not self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        ):
            raise AccessError("Only eLearning Managers can run analysis jobs.")
        self.check_access("write")
        for job in self.try_lock_for_update():
            job.invalidate_recordset()
            if job.state != "pending":
                continue
            started = fields.Datetime.now()
            super(FacodiLearningAnalysisJob, job).write(
                {
                    "state": "processing",
                    "attempt_count": job.attempt_count + 1,
                    "started_at": started,
                }
            )
            result = self.env["facodi.learning.analysis.result"]
            error = False
            try:
                with self.env.cr.savepoint():
                    provider = job._get_provider_registry().get(job.provider)
                    if not provider:
                        raise ValueError(f"Unknown analysis provider: {job.provider}")
                    normalized = normalize_output(provider(job.slide_id), self.env)
                    result = result._record_output(
                        dict(
                            normalized,
                            job_id=job.id,
                            slide_id=job.slide_id.id,
                            provider=job.provider,
                        )
                    )
                    for proposal in normalized["proposed_mappings"]:
                        domain = [
                            ("source_slide_id", "=", job.slide_id.id),
                            ("target_slide_id", "=", proposal["target_slide_id"]),
                            ("mapping_type", "=", proposal["mapping_type"]),
                        ]
                        if not self.env["facodi.learning.mapping"].search_count(domain):
                            self.env["facodi.learning.mapping"].create(
                                dict(
                                    proposal,
                                    source_slide_id=job.slide_id.id,
                                    origin="analysis",
                                    analysis_result_id=result.id,
                                )
                            )
            except Exception as exc:
                # Provider failures are data; the savepoint discards all partial output.
                _logger.warning(
                    "FACODI analysis job %s failed (%s)", job.id, type(exc).__name__
                )
                error = f"{type(exc).__name__}: operation failed; inspect the provider configuration."
                result = self.env["facodi.learning.analysis.result"]
            completed = fields.Datetime.now()
            values = {
                "state": "failed" if error else "completed",
                "completed_at": completed,
                "last_error": error,
                "result_id": result.id,
                "model_name": result.model_name if result else False,
            }
            super(FacodiLearningAnalysisJob, job).write(values)
            self.env["facodi.learning.analysis.attempt"]._record_attempt(
                {
                    "job_id": job.id,
                    "provider": job.provider,
                    "number": job.attempt_count,
                    "started_at": started,
                    "completed_at": completed,
                    "state": values["state"],
                    "error": error,
                    "result_id": result.id,
                }
            )
        return True

    def action_retry(self):
        self.check_access("write")
        for job in self.try_lock_for_update():
            job.invalidate_recordset()
            if job.state == "failed":
                super(FacodiLearningAnalysisJob, job).write({"state": "pending"})
        return True

    @api.model
    def _cron_process_pending_jobs(self):
        parameter = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("facodi_learning.analysis_batch_size", "10")
        )
        try:
            batch_size = max(1, min(int(parameter), 100))
        except (TypeError, ValueError):
            batch_size = 10
        jobs = self.search([("state", "=", "pending")], limit=batch_size, order="id")
        for job in jobs:
            job.action_process()
            if self.env.context.get("cron_id"):
                remaining = self.search_count([("state", "=", "pending")])
                if not self.env["ir.cron"]._commit_progress(1, remaining=remaining):
                    break
        return True
