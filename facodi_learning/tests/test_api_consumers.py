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
        run.action_execute_pipeline()
        count = self.env['slide.slide'].search_count([])
        run.action_approve_and_publish(publication_evidence={
            'author': 'FACODI original acceptance fixture', 'rights_mode': 'original',
            'usage_basis': 'Original text authored exclusively for disposable acceptance.',
            'purpose': 'Validate native editorial publication without duplicating content.',
        })
        run.action_approve_and_publish()
        self.assertEqual(run.published_slide_id, self.slide)
        self.assertEqual(self.env['slide.slide'].search_count([]), count)
        self.assertEqual(self.env['facodi.learning.content.review'].search_count([
            ('slide_id', '=', self.slide.id), ('state', '=', 'approved')]), 1)
        self.assertFalse(self.course.website_published)

    def test_provider_is_frozen_even_before_processing(self):
        job = self.request()
        with self.assertRaises(AccessError):
            job.write({'provider': 'local_metadata'})

    def test_stale_content_does_not_create_an_analysis_result(self):
        job = self.request()
        self.slide.write({'html_content': '<p>Changed after acceptance.</p>'})
        self.assertFalse(job.pipeline_run_id.with_user(self.actor).action_execute_pipeline())
        job.invalidate_recordset()
        self.assertEqual(job.state, 'waiting_input')
        self.assertFalse(job.result_id)
        self.assertEqual(job.pipeline_run_id.error_message, 'CANONICAL_INPUT_CHANGED')

    def test_local_origin_survives_selector_change_and_prevents_legacy_sync(self):
        with patch.object(type(self.slide), '_facodi_sync_supabase_video', autospec=True, return_value=True):
            video = self.env['slide.slide'].with_user(self.actor).with_context(website_slides_skip_fetch_metadata=True).create({
                'name': 'Local video fixture', 'channel_id': self.course.id,
                'slide_category': 'video', 'source_type': 'external',
                'video_url': 'https://www.youtube.com/watch?v=4GVbqYFmGBw',
                'is_published': False, 'website_published': False,
            })
        self.assertEqual(video.facodi_processing_origin, 'odoo_python')
        self.params.set_param('facodi_learning.analysis_provider', 'local_metadata')
        with patch.object(type(video), '_facodi_sync_supabase_video', autospec=True, return_value=True) as transport:
            video.write({'description': '<p>Changed after provider selection.</p>'})
            self.assertFalse(transport.call_count)

    def test_client_cannot_inject_run_or_processing_origin(self):
        with self.assertRaises(AccessError):
            self.env['facodi.learning.analysis.job'].with_user(self.actor).create({
                'slide_id': self.slide.id, 'provider': 'odoo_python', 'pipeline_run_id': 123456,
            })
        with self.assertRaises(AccessError):
            self.slide.write({'facodi_processing_origin': 'legacy'})
