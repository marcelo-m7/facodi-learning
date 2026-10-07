"""Real registry acceptance for the opt-in processing adapter."""
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'facodi_api_consumers')
class TestApiConsumers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.actor = cls.env['res.users'].create({
            'name': 'API consumer actor', 'login': 'api-consumer-actor',
            'group_ids': [Command.set([cls.env.ref('facodi_api.group_pipeline_reviewer').id])],
        })
        cls.params = cls.env['ir.config_parameter'].sudo()
        cls.params.set_param('facodi_api.pipeline_enabled', 'true')
        cls.params.set_param('facodi_learning.analysis_provider', 'odoo_python')
        cls.params.set_param('facodi_learning.pipeline_user_id', str(cls.actor.id))
        cls.course = cls.env['slide.channel'].with_user(cls.actor).create({
            'name': 'Private consumer course', 'user_id': cls.actor.id,
            'website_id': cls.env['website'].search([('company_id', '=', cls.env.company.id)], limit=1).id,
            'website_published': False, 'visibility': 'members', 'enroll': 'invite',
        })
        cls.slide = cls.env['slide.slide'].with_user(cls.actor).create({
            'name': 'Original consumer evidence', 'channel_id': cls.course.id,
            'slide_category': 'article', 'html_content': '<p>Learning evidence and native review remain separate from publication.</p>',
            'is_published': False, 'website_published': False,
        })

    def request(self):
        return self.slide.with_user(self.actor).action_facodi_request_analysis()

    def test_request_queues_one_run_without_processing_or_result(self):
        job = self.request()
        self.assertEqual(job.provider, 'odoo_python')
        self.assertEqual(job.pipeline_run_id.status, 'received')
        self.assertEqual(job.state, 'pending')
        self.assertFalse(job.result_id)
        self.assertFalse(job.pipeline_run_id.metadata_json)
        self.assertEqual(job.pipeline_run_id.existing_slide_id, self.slide)

    def test_legacy_scheduler_never_executes_delegated_run(self):
        job = self.request()
        self.env['facodi.learning.analysis.job']._cron_process_pending_jobs()
        job.invalidate_recordset()
        self.assertEqual(job.state, 'pending')
        self.assertEqual(job.pipeline_run_id.status, 'received')
        self.assertFalse(job.attempt_ids)

    def test_api_worker_records_one_native_result_and_attempt(self):
        job = self.request()
        run = job.pipeline_run_id.with_user(self.actor)
        self.assertTrue(run.action_execute_pipeline())
        job.invalidate_recordset()
        self.assertEqual(job.state, 'completed')
        self.assertTrue(job.result_id.summary)
        self.assertEqual(job.result_id.provider, 'odoo_python')
        self.assertEqual(len(job.attempt_ids), 1)
        job.with_user(self.actor).action_process()
        self.assertEqual(len(job.attempt_ids), 1)
        self.assertEqual(len(self.slide.facodi_analysis_result_ids), 1)
        self.assertFalse(self.slide.is_published)

    def test_publication_reuses_canonical_slide_and_native_review(self):
        job = self.request()
        run = job.pipeline_run_id.with_user(self.actor)
        count = self.env['slide.slide'].search_count([])
        run.action_execute_pipeline()
        run.action_approve_and_publish(publication_evidence={
            'author': 'FACODI original acceptance fixture', 'rights_mode': 'original',
            'usage_basis': 'Original text authored exclusively for disposable acceptance.',
            'purpose': 'Validate native editorial publication without duplicating content.',
        })
        run.action_approve_and_publish()
        self.assertEqual(run.published_slide_id, self.slide)
        self.assertEqual(self.env['slide.slide'].search_count([]), count)
        self.assertTrue(self.slide.is_published)
        self.assertTrue(self.slide.website_published)
        self.assertEqual(self.env['facodi.learning.content.review'].search_count([
            ('slide_id', '=', self.slide.id), ('state', '=', 'approved')]), 1)
        self.assertFalse(self.course.website_published)

    def test_provider_is_frozen_even_before_processing(self):
        job = self.request()
        with self.assertRaises(AccessError):
            job.write({'provider': 'local_metadata'})

    def test_legacy_job_cannot_be_switched_into_api_processing(self):
        job = self.env['facodi.learning.analysis.job'].with_user(self.actor).create({
            'slide_id': self.slide.id, 'provider': 'local_metadata',
        })
        with self.assertRaises(AccessError):
            job.write({'provider': 'odoo_python'})
        self.assertFalse(job.pipeline_run_id)

    def test_stale_content_does_not_create_an_analysis_result(self):
        job = self.request()
        self.slide.write({'html_content': '<p>Changed after acceptance.</p>'})
        self.assertFalse(job.pipeline_run_id.with_user(self.actor).action_execute_pipeline())
        job.invalidate_recordset()
        self.assertEqual(job.state, 'waiting_input')
        self.assertFalse(job.result_id)
        self.assertEqual(job.pipeline_run_id.error_message, 'CANONICAL_INPUT_CHANGED')

    def test_local_origin_survives_selector_change_and_prevents_legacy_sync(self):
        with patch.object(type(self.slide), '_facodi_sync_supabase_video', autospec=True, return_value=True) as transport:
            video = self.env['slide.slide'].with_user(self.actor).with_context(website_slides_skip_fetch_metadata=True).create({
                'name': 'Local video fixture', 'channel_id': self.course.id,
                'slide_category': 'video', 'source_type': 'external',
                'video_url': 'https://www.youtube.com/watch?v=4GVbqYFmGBw',
                'is_published': False, 'website_published': False,
            })
            self.assertEqual(transport.call_count, 0)
        self.assertEqual(video.facodi_processing_origin, 'odoo_python')
        self.params.set_param('facodi_learning.analysis_provider', 'local_metadata')
        with patch.object(type(video), '_facodi_sync_supabase_video', autospec=True, return_value=True) as transport:
            video.write({'description': '<p>Changed after provider selection.</p>'})
            video.write({'description': '<p>Replayed change after provider selection.</p>'})
            self.assertEqual(transport.call_count, 0)

    def test_legacy_origin_with_api_receipt_never_requeues_supabase(self):
        self.params.set_param('facodi_learning.analysis_provider', 'local_metadata')
        slide = self.env['slide.slide'].with_user(self.actor).create({
            'name': 'Originally legacy article', 'channel_id': self.course.id,
            'slide_category': 'article', 'html_content': '<p>Accepted API receipt evidence.</p>',
            'is_published': False, 'website_published': False,
        })
        source = self.env['facodi.learning.source'].with_user(self.actor).create({
            'name': 'Receipt replay source', 'provider': 'manual',
            'external_id': 'receipt-replay-source', 'channel_id': self.course.id,
            'metadata': {'description': 'Accepted API receipt evidence.'},
        })
        source._ingest(slide_id=slide.id)
        self.params.set_param('facodi_learning.analysis_provider', 'odoo_python')
        api_job = slide.with_user(self.actor).action_facodi_request_analysis()
        self.assertTrue(api_job.pipeline_run_id)

        self.params.set_param('facodi_learning.analysis_provider', 'local_metadata')
        with patch.dict('os.environ', {
                'SUPABASE_URL': 'https://example.supabase.co',
                'SUPABASE_SECRET_KEY': 'fixture',
        }):
            jobs = source._queue_supabase_analysis()
        self.assertIn(api_job, jobs)
        self.assertFalse(self.env['facodi.learning.analysis.job'].search([
            ('slide_id', '=', slide.id), ('provider', '=', 'supabase_edge'),
        ]))

    def test_client_cannot_inject_run_or_processing_origin(self):
        with self.assertRaises(AccessError):
            self.env['facodi.learning.analysis.job'].with_user(self.actor).create({
                'slide_id': self.slide.id, 'provider': 'odoo_python', 'pipeline_run_id': 123456,
            })
        with self.assertRaises(AccessError):
            self.slide.write({'facodi_processing_origin': 'legacy'})

    def test_transcript_change_invalidates_the_accepted_source(self):
        job = self.request()
        self.slide.write({'facodi_transcript': 'A new transcript after acceptance.'})
        self.assertFalse(job.pipeline_run_id.with_user(self.actor).action_execute_pipeline())
        self.assertEqual(job.pipeline_run_id.status, 'waiting_input')
        self.assertFalse(job.result_id)

    def test_source_ingestion_queues_local_job_without_legacy_secrets(self):
        source = self.env['facodi.learning.source'].with_user(self.actor).create({
            'name': 'Local source fixture', 'provider': 'manual', 'external_id': 'api-consumer-source',
            'channel_id': self.course.id, 'metadata': {'description': 'Original source learning evidence.'},
        })
        with patch.dict('os.environ', {'SUPABASE_URL': '', 'SUPABASE_SECRET_KEY': ''}):
            source._ingest(slide_id=self.slide.id)
            source.action_ingest()
        self.assertEqual(len(source.slide_id.facodi_analysis_job_ids), 1)
        job = source.slide_id.facodi_analysis_job_ids
        self.assertEqual(job.provider, 'odoo_python')
        self.assertEqual(job.pipeline_run_id.existing_slide_id, source.slide_id)

    def test_reconciliation_uses_the_accepted_actor_after_config_change(self):
        job = self.request()
        job.pipeline_run_id.with_user(self.actor).action_execute_pipeline()
        self.params.set_param('facodi_learning.pipeline_user_id', '')
        job.with_user(self.actor).action_process()
        self.assertEqual(job.state, 'completed')
        self.assertEqual(len(job.attempt_ids), 1)

    def test_editorial_projection_failure_rolls_back_partial_result(self):
        from odoo.exceptions import ValidationError
        job = self.request()
        Attempt = self.env['facodi.learning.analysis.attempt']
        with patch.object(type(Attempt), '_record_attempt', side_effect=ValidationError('Controlled persistence failure')):
            self.assertTrue(job.pipeline_run_id.with_user(self.actor).action_execute_pipeline())
        self.assertEqual(job.state, 'failed')
        self.assertEqual(job.last_error, 'EDITORIAL_PROJECTION_FAILED')
        self.assertFalse(job.result_id)
        self.assertFalse(self.slide.facodi_analysis_result_ids)
        self.assertEqual(job.pipeline_receipt_revision, -1)
        self.assertEqual(job.attempt_count, 0)
        with self.assertRaises(ValidationError):
            job.pipeline_run_id.with_user(self.actor).action_approve_and_publish(publication_evidence={
                'author': 'Original fixture', 'rights_mode': 'original',
                'usage_basis': 'Original acceptance fixture.', 'purpose': 'Validate incomplete editorial handoff.'})
        job.with_user(self.actor).action_process()
        self.assertEqual(job.state, 'completed')
        self.assertTrue(job.result_id)
        self.assertEqual(len(job.attempt_ids), 1)

    def test_cancelled_job_records_command_without_a_fake_processing_attempt(self):
        job = self.request()
        revision = job.pipeline_run_id.revision
        job.with_user(self.actor).action_cancel(expected_revision=revision)
        job.with_user(self.actor).action_cancel(expected_revision=revision)
        self.assertEqual(job.state, 'cancelled')
        self.assertEqual(job.pipeline_run_id.status, 'cancelled')
        self.assertFalse(job.result_id)
        self.assertFalse(job.attempt_ids)

    def test_cancelling_completed_projection_reconciles_newer_receipt(self):
        job = self.request()
        run = job.pipeline_run_id.with_user(self.actor)
        self.assertTrue(run.action_execute_pipeline())
        self.assertEqual(job.state, 'completed')
        run.action_cancel(expected_revision=run.revision)
        job.invalidate_recordset()
        self.assertEqual(job.state, 'cancelled')
        self.assertEqual(job.pipeline_receipt_revision, run.revision)
        self.assertEqual(len(job.attempt_ids), 1)

    def test_non_learning_operator_run_skips_editorial_hook(self):
        operator = self.env['res.users'].create({
            'name': 'API-only operator', 'login': 'api-only-operator',
            'group_ids': [Command.set([self.env.ref('facodi_api.group_pipeline_operator').id])],
        })
        course = self.env['slide.channel'].create({
            'name': 'API-only course', 'user_id': operator.id,
            'website_id': self.course.website_id.id, 'website_published': True,
        })
        run = self.env['facodi.pipeline.run'].with_user(operator).create({
            'source_type': 'manual', 'raw_content': 'Independent API evidence.',
            'idempotency_key': 'api-only-hook', 'target_channel_id': course.id,
        })
        self.assertTrue(run.action_execute_pipeline())
        self.assertEqual(run.status, 'waiting_review')

    def test_reconciliation_isolates_actor_who_lost_api_access(self):
        blocked = self.request()
        blocked.pipeline_run_id.with_user(self.actor)._set_execution_values({'status': 'waiting_input', 'error_message': 'INPUT_REQUIRED'})

        replacement = self.env['res.users'].create({
            'name': 'Second API consumer actor', 'login': 'second-api-consumer-actor',
            'group_ids': [Command.set([self.env.ref('facodi_api.group_pipeline_reviewer').id])],
        })
        self.params.set_param('facodi_learning.pipeline_user_id', str(replacement.id))
        valid = self.env['facodi.learning.analysis.job'].create({
            'slide_id': self.slide.id, 'provider': 'odoo_python',
        })
        valid.pipeline_run_id.with_user(replacement)._set_execution_values({'status': 'waiting_input', 'error_message': 'INPUT_REQUIRED'})
        self.actor.group_ids = [Command.unlink(self.env.ref('facodi_api.group_pipeline_reviewer').id)]

        self.env['facodi.pipeline.run']._reconcile_processing_receipts()
        blocked.invalidate_recordset()
        valid.invalidate_recordset()
        self.assertNotEqual(blocked.pipeline_receipt_revision, blocked.pipeline_run_id.revision)
        self.assertEqual(valid.state, 'waiting_input')
        self.assertEqual(valid.pipeline_receipt_revision, valid.pipeline_run_id.revision)
