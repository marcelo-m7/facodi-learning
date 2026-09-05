from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestPipelineSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Officer",
                "login": "pipeline-officer",
                "group_ids": [
                    (
                        6,
                        0,
                        [cls.env.ref("website_slides.group_website_slides_officer").id],
                    )
                ],
            }
        )
        cls.other_officer = cls.env["res.users"].create(
            {
                "name": "Other Officer",
                "login": "pipeline-other-officer",
                "group_ids": [
                    (
                        6,
                        0,
                        [cls.env.ref("website_slides.group_website_slides_officer").id],
                    )
                ],
            }
        )
        cls.channel = cls.env["slide.channel"].create(
            {"name": "Owned", "user_id": cls.officer.id}
        )
        cls.slide = cls.env["slide.slide"].create(
            {
                "name": "Source",
                "channel_id": cls.channel.id,
                "slide_category": "article",
            }
        )
        cls.target = cls.slide.copy({"name": "Target"})

    def test_review_direct_orm_denied(self):
        mapping = (
            self.env["facodi.learning.mapping"]
            .with_user(self.officer)
            .create(
                {"source_slide_id": self.slide.id, "target_slide_id": self.target.id}
            )
        )
        with self.assertRaises(AccessError):
            mapping.with_context(facodi_internal=True).write({"state": "approved"})

    def test_forged_requester_denied(self):
        with self.assertRaises(AccessError):
            self.env["facodi.learning.analysis.job"].with_user(self.officer).create(
                {"slide_id": self.slide.id, "requested_by_id": self.env.user.id}
            )

    def test_result_immutable(self):
        job = self.slide.action_facodi_request_analysis()
        job.action_process()
        with self.assertRaises(AccessError):
            job.result_id.write({"summary": "Forged"})
        with self.assertRaises(AccessError):
            job.result_id.unlink()

    def test_portal_and_public_denied(self):
        for user in (
            self.env.ref("base.public_user"),
            self.env["res.users"].create(
                {
                    "name": "Portal",
                    "login": "pipeline-portal",
                    "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
                }
            ),
        ):
            with self.assertRaises(AccessError):
                self.env["facodi.learning.analysis.job"].with_user(user).create(
                    {"slide_id": self.slide.id}
                )

    def test_course_candidate_public_and_portal_denied(self):
        Candidate = self.env["facodi.learning.course.candidate"]
        portal = self.env["res.users"].create(
            {
                "name": "Course Candidate Portal",
                "login": "course-candidate-portal",
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        for user in (self.env.ref("base.public_user"), portal):
            with self.assertRaises(AccessError):
                Candidate.with_user(user).create(
                    {
                        "provider": "manual",
                        "external_id": f"denied-{user.id}",
                        "name": "Denied",
                    }
                )

    def test_officer_cannot_terminally_resolve_course_candidate(self):
        candidate = (
            self.env["facodi.learning.course.candidate"]
            .with_user(self.officer)
            .create(
                {
                    "provider": "manual",
                    "external_id": "officer-candidate",
                    "name": "Officer Candidate",
                    "description": "Safe description",
                    "language": "pt",
                }
            )
        )
        candidate.with_user(self.officer).action_evaluate()
        with self.assertRaises(AccessError):
            candidate.with_user(self.officer).action_resolve_new()

    def test_officer_cannot_edit_another_officers_course_candidate(self):
        candidate = (
            self.env["facodi.learning.course.candidate"]
            .with_user(self.officer)
            .create(
                {
                    "provider": "manual",
                    "external_id": "officer-owned-candidate",
                    "name": "Officer Owned Candidate",
                    "description": "Original description",
                    "language": "pt",
                }
            )
        )
        self.assertEqual(candidate.requested_by_id, self.officer)
        with self.assertRaises(AccessError):
            candidate.with_user(self.other_officer).write(
                {"description": "Cross-owner mutation"}
            )

    def test_ingest_idempotent(self):
        Source = self.env["facodi.learning.source"]
        values = {
            "external_id": "article-1",
            "channel_id": self.channel.id,
            "name": "Imported",
        }
        source = Source.ingest_manual(values)
        source.slide_id.write({"name": "Editorial title"})
        replay = Source.ingest_manual(values)
        self.assertEqual(source, replay)
        self.assertEqual(replay.slide_id.name, "Editorial title")
        self.assertFalse(replay.slide_id.website_published)

    def test_retry_preserves_failure(self):
        job = self.env["facodi.learning.analysis.job"].create(
            {"slide_id": self.slide.id, "provider": "missing"}
        )
        job.action_process()
        error = job.last_error
        job.action_retry()
        self.assertEqual(job.last_error, error)
        self.assertEqual(len(job.attempt_ids), 1)

    def test_cross_owner_and_reviewed_mapping_mutation_denied(self):
        mapping = self.env["facodi.learning.mapping"].create(
            {"source_slide_id": self.slide.id, "target_slide_id": self.target.id}
        )
        other_channel = self.env["slide.channel"].create({"name": "Other owner"})
        other_slide = self.slide.copy({"channel_id": other_channel.id})
        with self.assertRaises(AccessError):
            mapping.with_user(self.officer).write({"source_slide_id": other_slide.id})
        mapping.action_approve()
        with self.assertRaises(AccessError):
            mapping.write({"target_slide_id": other_slide.id})
        with self.assertRaises(AccessError):
            mapping.unlink()

    def test_provider_normalization_and_failure_isolation(self):
        from unittest.mock import patch

        Job = type(self.env["facodi.learning.analysis.job"])

        def adapter(slide):
            return {
                "summary": "Summary",
                "transcript": "Transcript",
                "suggested_tags": ["new tag"],
                "proposed_mappings": [
                    {"target_slide_id": self.target.id, "confidence": 0.8}
                ],
            }

        first = self.slide.action_facodi_request_analysis()
        second = self.env["facodi.learning.analysis.job"].create(
            {"slide_id": self.slide.id, "provider": "missing"}
        )
        with patch.object(
            Job, "_get_provider_registry", return_value={"local_metadata": adapter}
        ):
            (second | first).action_process()
        self.assertEqual(first.state, "completed")
        self.assertEqual(second.state, "failed")
        self.assertEqual(first.result_id.transcript, "Transcript")
        self.assertFalse(self.slide.tag_ids.filtered(lambda tag: tag.name == "new tag"))
        mapping = self.env["facodi.learning.mapping"].search(
            [("analysis_result_id", "=", first.result_id.id)]
        )
        self.assertEqual(mapping.state, "proposed")
        first.result_id.action_apply_suggested_tags()
        self.assertTrue(self.slide.tag_ids.filtered(lambda tag: tag.name == "new tag"))
        self.assertTrue(first.result_id.tags_applied_at)

    def test_source_failure_rolls_back_content(self):
        source = self.env["facodi.learning.source"].create(
            {
                "name": "Unsupported",
                "external_id": "bad",
                "provider": "unavailable",
                "channel_id": self.channel.id,
            }
        )
        before = self.env["slide.slide"].search_count([])
        source.action_ingest()
        self.assertEqual(source.state, "failed")
        self.assertTrue(source.last_error)
        self.assertFalse(source.slide_id)
        self.assertEqual(self.env["slide.slide"].search_count([]), before)
        with self.assertRaises(AccessError):
            source.with_user(self.officer).action_ingest()

    def test_student_technical_fields_denied(self):
        with self.assertRaises(AccessError):
            self.slide.with_user(self.env.ref("base.public_user")).read(
                ["facodi_transcript"]
            )

    def test_empty_provider_exception_is_failure(self):
        from unittest.mock import patch

        def fail(slide):
            raise RuntimeError()

        job = self.slide.action_facodi_request_analysis()
        with patch.object(
            type(job), "_get_provider_registry", return_value={"local_metadata": fail}
        ):
            job.action_process()
        self.assertEqual(job.state, "failed")
        self.assertTrue(job.last_error)
        self.assertFalse(job.result_id)

    def test_learner_relations_only_approved_visible_targets(self):
        website = self.env["website"].search([], limit=1)
        self.channel.write(
            {
                "website_published": True,
                "website_id": website.id,
                "visibility": "public",
            }
        )
        (self.slide | self.target).write(
            {"website_published": True, "is_preview": True}
        )
        mapping = self.env["facodi.learning.mapping"].create(
            {"source_slide_id": self.slide.id, "target_slide_id": self.target.id}
        )
        public_slide = self.slide.with_user(self.env.ref("base.public_user"))
        self.assertFalse(public_slide._facodi_related_slides(website))
        mapping.action_approve()
        self.assertEqual(
            public_slide._facodi_related_slides(website).ids, self.target.ids
        )
        self.target.website_published = False
        self.assertFalse(public_slide._facodi_related_slides(website))

    def test_reject_tags_records_review_without_editorial_change(self):
        job = self.slide.action_facodi_request_analysis()
        job.action_process()
        result = job.result_id
        result.action_reject_suggested_tags()
        self.assertEqual(result.tags_review_state, "rejected")
        self.assertEqual(result.tags_reviewed_by_id, self.env.user)
        with self.assertRaises(ValidationError):
            result.action_apply_suggested_tags()

    def test_ingestion_adapter_preserves_unpublished_canonical_content(self):
        from unittest.mock import patch

        Source = self.env["facodi.learning.source"]
        values = {
            "provider": "oer",
            "external_id": "resource-1",
            "channel_id": self.channel.id,
            "name": "OER",
        }
        adapter = lambda source: {
            "name": source.name,
            "slide_category": "article",
            "html_content": "<p>Open educational resource</p>",
            "website_published": True,
        }
        with patch.object(
            type(Source), "_get_ingestion_registry", return_value={"oer": adapter}
        ):
            first = Source.ingest(values)
            replay = Source.ingest(values)
        self.assertEqual(first, replay)
        self.assertEqual(first.slide_id.channel_id, self.channel)
        self.assertFalse(first.slide_id.is_published)
        self.assertFalse(first.slide_id.website_published)
        self.assertIn("Open educational", first.slide_id.html_content)

    def test_cron_batch_and_completed_job_are_bounded(self):
        first = self.slide.action_facodi_request_analysis()
        second = self.slide.action_facodi_request_analysis()
        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_learning.analysis_batch_size", "1"
        )
        self.env["facodi.learning.analysis.job"]._cron_process_pending_jobs()
        self.assertEqual(first.state, "completed")
        self.assertEqual(second.state, "pending")
        first.action_process()
        self.assertEqual(first.attempt_count, 1)
        self.assertEqual(len(first.attempt_ids), 1)

    def test_mapping_constraints_and_provenance(self):
        Mapping = self.env["facodi.learning.mapping"]
        values = {"source_slide_id": self.slide.id, "target_slide_id": self.target.id}
        for extra in ({"confidence": 1.1}, {"confidence": -0.1}):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                Mapping.create(dict(values, **extra))
        with self.assertRaises(AccessError):
            Mapping.create(dict(values, state="approved"))

    def test_hidden_course_and_other_website_not_recommended(self):
        website = self.env["website"].search([], limit=1)
        other = self.env["website"].create({"name": "Another website"})
        self.channel.write(
            {"is_published": True, "website_id": website.id, "visibility": "public"}
        )
        (self.slide | self.target).write({"is_published": True, "is_preview": True})
        self.env["facodi.learning.mapping"].create(
            {"source_slide_id": self.slide.id, "target_slide_id": self.target.id}
        ).action_approve()
        public = self.slide.with_user(self.env.ref("base.public_user"))
        self.assertFalse(public._facodi_related_slides(other))
        hidden = self.env["slide.channel"].create(
            {
                "name": "Unlisted",
                "website_id": website.id,
                "visibility": "link",
                "is_published": True,
            }
        )
        self.target.channel_id = hidden
        self.assertFalse(public._facodi_related_slides(website))

    def test_context_cannot_forge_result_review(self):
        job = self.slide.action_facodi_request_analysis()
        job.with_context(
            default_tags_review_state="applied", default_tags_applied_by_id=self.env.uid
        ).action_process()
        self.assertEqual(job.result_id.tags_review_state, "pending")
        self.assertFalse(job.result_id.tags_applied_by_id)
