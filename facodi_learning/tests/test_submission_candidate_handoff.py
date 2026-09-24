from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase

from ..services.curriculum_bootstrap import ensure_lesti_2026_27


class TestSubmissionCandidateHandoff(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Submission Handoff Manager",
                "login": "submission-handoff-manager",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Submission Handoff Officer",
                "login": "submission-handoff-officer",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.reference = ensure_lesti_2026_27(cls.env)
        cls.unit = cls.reference.unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19411017"
        )

    def _accepted_submission(self, *, source_url="https://example.org/resource", name="Resource"):
        submission = self.env["facodi.learning.submission"].with_user(
            self.manager
        ).create(
            {
                "name": name,
                "source_url": source_url,
                "language": "pt",
                "context": "Useful for database foundations.",
                "curriculum_unit_id": self.unit.id,
            }
        )
        submission.action_accept()
        return submission

    def test_accepted_submission_routes_to_discovered_candidate_without_content_side_effect(self):
        submission = self._accepted_submission()
        before_candidates = self.env["facodi.learning.course.candidate"].search_count([])
        before_courses = self.env["slide.channel"].search_count([])
        before_slides = self.env["slide.slide"].search_count([])
        before_sources = self.env["facodi.learning.source"].search_count([])

        submission.action_handoff_candidate()
        submission.invalidate_recordset()

        self.assertEqual(submission.state, "resolved")
        self.assertTrue(submission.candidate_id)
        self.assertEqual(submission.candidate_id.state, "discovered")
        self.assertEqual(
            submission.candidate_id.source_url,
            submission.normalized_source_url,
        )
        self.assertEqual(
            submission.candidate_id.metadata["submission_id"],
            submission.id,
        )
        self.assertEqual(
            submission.candidate_id.metadata["curriculum_unit_id"],
            self.unit.id,
        )
        self.assertEqual(
            self.env["facodi.learning.course.candidate"].search_count([]),
            before_candidates + 1,
        )
        self.assertEqual(self.env["slide.channel"].search_count([]), before_courses)
        self.assertEqual(self.env["slide.slide"].search_count([]), before_slides)
        self.assertEqual(
            self.env["facodi.learning.source"].search_count([]),
            before_sources,
        )

    def test_handoff_is_idempotent(self):
        submission = self._accepted_submission(
            source_url="https://example.org/idempotent",
            name="Idempotent resource",
        )
        submission.action_handoff_candidate()
        candidate = submission.candidate_id
        count = self.env["facodi.learning.course.candidate"].search_count([])

        submission.action_handoff_candidate()
        submission.invalidate_recordset()

        self.assertEqual(submission.candidate_id, candidate)
        self.assertEqual(
            self.env["facodi.learning.course.candidate"].search_count([]),
            count,
        )

    def test_existing_active_candidate_for_canonical_url_is_reused(self):
        existing = self.env["facodi.learning.course.candidate"].with_user(
            self.manager
        ).create(
            {
                "provider": "manual",
                "external_id": "existing-submission-resource",
                "source_url": "https://example.org/reused",
                "name": "Existing candidate",
            }
        )
        submission = self._accepted_submission(
            source_url="https://EXAMPLE.org:443/reused/#fragment",
            name="Same resource",
        )
        count = self.env["facodi.learning.course.candidate"].search_count([])

        submission.action_handoff_candidate()
        submission.invalidate_recordset()

        self.assertEqual(submission.candidate_id, existing)
        self.assertEqual(
            self.env["facodi.learning.course.candidate"].search_count([]),
            count,
        )

    def test_rejected_candidate_does_not_block_new_handoff(self):
        rejected = self.env["facodi.learning.course.candidate"].with_user(
            self.manager
        ).create(
            {
                "provider": "manual",
                "external_id": "rejected-submission-resource",
                "source_url": "https://example.org/rejected",
                "name": "Rejected candidate",
            }
        )
        rejected.action_evaluate()
        rejected.action_reject()

        submission = self._accepted_submission(
            source_url="https://example.org/rejected",
            name="Resubmitted resource",
        )
        submission.action_handoff_candidate()
        submission.invalidate_recordset()

        self.assertNotEqual(submission.candidate_id, rejected)
        self.assertEqual(submission.candidate_id.state, "discovered")

    def test_non_accepted_submission_cannot_handoff(self):
        submission = self.env["facodi.learning.submission"].with_user(
            self.manager
        ).create(
            {
                "name": "Not accepted",
                "source_url": "https://example.org/not-accepted",
            }
        )
        with self.assertRaises(ValidationError):
            submission.action_handoff_candidate()

    def test_officer_cannot_handoff_submission(self):
        submission = self._accepted_submission(
            source_url="https://example.org/officer-denied",
            name="Officer denied",
        )
        with self.assertRaises(AccessError):
            submission.with_user(self.officer).action_handoff_candidate()
