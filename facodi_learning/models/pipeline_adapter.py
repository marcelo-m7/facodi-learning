"""Native editorial projection of API receipts. Only the API executes processing."""
import json

from odoo import api, fields, models, tools
from odoo.exceptions import AccessError, ValidationError

from ..services.analysis import normalize_output


class AnalysisJob(models.Model):
    _inherit = 'facodi.learning.analysis.job'

    state = fields.Selection(selection_add=[('waiting_input', 'Waiting for Input'), ('cancelled', 'Cancelled')],
                             ondelete={'waiting_input': 'set default', 'cancelled': 'set default'})
    pipeline_run_id = fields.Many2one('facodi.pipeline.run', readonly=True, ondelete='restrict', index=True,
                                     groups='website_slides.group_website_slides_officer')
    pipeline_receipt_revision = fields.Integer(readonly=True, default=-1,
                                               groups='website_slides.group_website_slides_officer')

    @api.model_create_multi
    def create(self, vals_list):
        jobs = super().create(vals_list)
        for job in jobs.filtered(lambda record: record.provider == 'odoo_python'):
            job._enqueue_pipeline_run()
        return jobs

    def write(self, values):
        if any(job.pipeline_run_id or job.provider == 'odoo_python' for job in self):
            raise AccessError('Accepted API jobs are immutable; use processing actions.')
        return super().write(values)

    def _pipeline_actor(self):
        self.ensure_one()
        value = self.env['ir.config_parameter'].sudo().get_param('facodi_learning.pipeline_user_id', '')
        if not isinstance(value, str) or not value.isdecimal():
            raise ValidationError('Configure an internal pipeline user before selecting API processing.')
        actor = self.env['res.users'].browse(int(value)).exists()
        company = self.slide_id.channel_id.website_id.company_id
        if (not actor or not actor.active or actor.share or company not in actor.company_ids
                or not actor.has_group('facodi_api.group_pipeline_operator')
                or not actor.has_group('website_slides.group_website_slides_manager')):
            raise AccessError('The configured processing user cannot process this course.')
        return actor, company

    def _enqueue_pipeline_run(self):
        self.ensure_one()
        self.slide_id.check_access('read')
        self.slide_id.check_access('write')
        actor, company = self._pipeline_actor()
        slide = self.slide_id.with_user(actor).with_company(company)
        slide.check_access('read')
        slide.check_access('write')
        Run = self.env['facodi.pipeline.run'].with_user(actor).with_company(company)
        values = {'idempotency_key': 'learning-job-%s' % self.id,
                  'target_channel_id': slide.channel_id.id, 'existing_slide_id': slide.id,
                  'title': slide.name or '', 'language': (slide.channel_id.website_id.default_lang_id.code or 'pt')[:20]}
        if slide.slide_category == 'video':
            values.update(source_type='youtube', source_url=slide.video_url or slide.url or '',
                          raw_content=slide.facodi_transcript or '',
                          is_manual_transcript=bool(slide.facodi_transcript and slide.facodi_transcript.strip()))
        elif slide.slide_category == 'document' and slide.binary_content:
            # Native binary fields already have an authorized attachment; do not duplicate files.
            attachment = self.env['ir.attachment'].with_user(actor).search([
                ('res_model', '=', 'slide.slide'), ('res_id', '=', slide.id), ('res_field', '=', 'binary_content')], limit=1)
            if not attachment:
                raise ValidationError('Canonical document attachment is missing.')
            values.update(source_type='document', attachment_id=attachment.id, raw_content='')
        else:
            text = tools.html2plaintext(slide.html_content or slide.description or '').strip()
            if not text:
                text = (slide.facodi_transcript or '').strip()
            values.update(source_type='manual', raw_content=text)
        receipt = Run.submit(values)
        run = Run.browse(receipt['id'])
        run._set_execution_values({'learning_job_id': self.id})
        self._set_processing_values({'pipeline_run_id': run.id, 'pipeline_receipt_revision': -1})

    def _reconcile_pipeline_receipt(self):
        self.ensure_one()
        run = self.pipeline_run_id
        if not run or run.learning_job_id != self:
            raise ValidationError('Processing receipt is not associated with this job.')
        self.check_access('write')
        run.check_access('read')
        if not self.try_lock_for_update():
            return False
        self.invalidate_recordset()
        if self.pipeline_receipt_revision == run.revision or self.state == 'completed':
            return True
        if run.status in ('received', 'running'):
            return True
        result = self.env['facodi.learning.analysis.result']
        error = run.error_message or False
        state = {'waiting_input': 'waiting_input', 'cancelled': 'cancelled', 'failed': 'failed'}.get(run.status, 'completed')
        if state == 'completed':
            if run.status not in ('waiting_review', 'published'):
                raise ValidationError('Processing receipt is not complete.')
            run._prepare_content_source()
            metadata = json.loads(run.metadata_json or '{}')
            document, enriched = metadata.get('document_data', {}), metadata.get('enriched_data', {})
            normalized = normalize_output({
                'summary': enriched.get('summary'), 'transcript': document.get('text_content'),
                'detected_language': document.get('language'), 'model_name': enriched.get('model_name'),
                'suggested_tags': enriched.get('keywords', []),
                'raw_payload': {'pipeline_run_id': run.run_id, 'provider': enriched.get('provider_name'),
                                'warnings': enriched.get('warnings', []), 'concepts': enriched.get('concepts', [])},
            }, self.env)
            if not normalized['summary'] or not normalized['transcript']:
                raise ValidationError('Processing output has no usable evidence.')
            result = result._record_output(dict(normalized, job_id=self.id, slide_id=self.slide_id.id, provider=self.provider))
        now = fields.Datetime.now()
        # Cancellation before execution is a command, not a processing attempt.
        if run.attempt_count > self.attempt_count:
            self.env['facodi.learning.analysis.attempt']._record_attempt({
                'job_id': self.id, 'provider': self.provider, 'number': run.attempt_count,
                'started_at': run.create_date, 'completed_at': now,
                'state': 'completed' if result else 'failed', 'error': error, 'result_id': result.id,
            })
        self._set_processing_values({'state': state, 'result_id': result.id, 'model_name': result.model_name if result else False,
                                     'attempt_count': run.attempt_count, 'completed_at': now,
                                     'last_error': error, 'pipeline_receipt_revision': run.revision})
        return True

    def action_process(self):
        local = self.filtered(lambda job: job.provider == 'odoo_python')
        for job in local:
            actor, company = job._pipeline_actor()
            job.check_access('write')
            if not self.env.su and not self.env.user.has_group('website_slides.group_website_slides_manager'):
                raise AccessError('Only eLearning Managers can reconcile processing jobs.')
            job.with_user(actor).with_company(company)._reconcile_pipeline_receipt()
        return super(AnalysisJob, self - local).action_process() if self - local else True

    def action_retry(self):
        local = self.filtered(lambda job: job.provider == 'odoo_python')
        for job in local:
            job.check_access('write')
            actor, company = job._pipeline_actor()
            run = job.pipeline_run_id.with_user(actor).with_company(company)
            run.action_retry(expected_revision=run.revision)
            job._set_processing_values({'state': 'pending'})
        return super(AnalysisJob, self - local).action_retry() if self - local else True


class PipelineRun(models.Model):
    _inherit = 'facodi.pipeline.run'

    learning_job_id = fields.Many2one('facodi.learning.analysis.job', readonly=True, ondelete='restrict', index=True,
                                    groups='website_slides.group_website_slides_officer')

    def _on_processing_complete(self):
        result = super()._on_processing_complete()
        for run in self.filtered('learning_job_id'):
            if run.learning_job_id.pipeline_run_id == run:
                run.learning_job_id._reconcile_pipeline_receipt()
        return result

    @api.model
    def _reconcile_processing_receipts(self):
        result = super()._reconcile_processing_receipts()
        runs = self.search([('learning_job_id', '!=', False), ('status', 'in', ['waiting_review', 'failed', 'waiting_input', 'cancelled'])], limit=100, order='id desc')
        for run in runs:
            actor = run.owner_id
            if actor.active and actor.has_group('website_slides.group_website_slides_manager'):
                run.with_user(actor).with_company(run.company_id)._on_processing_complete()
        return result
