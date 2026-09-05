from odoo.tests import TransactionCase


class TestFacodiLearningAnalysis(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["slide.channel"].create({"name": "FACODI Test Course"})
        cls.slide = cls.env["slide.slide"].create(
            {
                "name": "Open learning introduction",
                "channel_id": cls.channel.id,
                "slide_category": "article",
                "description": "An introduction to open learning, digital education, and community knowledge.",
                "tag_ids": [(0, 0, {"name": "Open Learning"})],
            }
        )

    def test_analysis_uses_standard_slide_and_preserves_history(self):
        first_job = self.slide.action_facodi_request_analysis()
        self.assertEqual(first_job.state, "pending")

        first_job.action_process()
        self.assertEqual(first_job.state, "completed")
        self.assertEqual(first_job.result_id.slide_id, self.slide)
        self.assertEqual(first_job.result_id.provider, "local_metadata")
        self.assertIn(
            "Open Learning", first_job.result_id.suggested_tag_ids.mapped("name")
        )

        second_job = self.slide.action_facodi_request_analysis()
        second_job.action_process()
        self.assertEqual(len(self.slide.facodi_analysis_result_ids), 2)
        self.assertNotEqual(first_job.result_id, second_job.result_id)

    def test_failed_job_can_be_retried(self):
        job = self.slide.action_facodi_request_analysis()
        job.write({"provider": "missing_provider"})
        job.action_process()
        self.assertEqual(job.state, "failed")
        self.assertTrue(job.last_error)

        job.action_retry()
        self.assertEqual(job.state, "pending")
        job.write({"provider": "local_metadata"})
        job.action_process()
        self.assertEqual(job.state, "completed")
        self.assertEqual(job.attempt_count, 2)

    def test_applying_suggested_tags_reuses_standard_slide_tags(self):
        job = self.slide.action_facodi_request_analysis()
        job.action_process()
        result = job.result_id
        self.slide.tag_ids = [(5, 0, 0)]

        result.action_apply_suggested_tags()

        self.assertEqual(self.slide.tag_ids, result.suggested_tag_ids)
