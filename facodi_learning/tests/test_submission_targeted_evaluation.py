from odoo.tests import TransactionCase

from ..services.curriculum_bootstrap import ensure_lesti_2026_27


class TestSubmissionTargetedCurriculumEvaluation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Targeted Evaluation Manager",
                "login": "targeted-evaluation-manager",
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
        cls.reference = ensure_lesti_2026_27(cls.env)
        cls.reference.write({"selection_enabled": True})
        cls.unit = cls.reference.unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19411017"
        )

    def _candidate_from_submission(self, name="Completely unrelated title"):
        submission = self.env["facodi.learning.submission"].with_user(
            self.manager
        ).create(
            {
                "name": name,
                "source_url": "https://example.org/targeted-%s" % self.id(),
                "language": "pt",
                "curriculum_unit_id": self.unit.id,
            }
        )
        submission.action_accept()
        submission.action_handoff_candidate()
        return submission, submission.candidate_id

    def _approve_full_coverage(self):
        channel = self.env["slide.channel"].create(
            {"name": "Existing full database coverage"}
        )
        coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.manager
        ).create(
            {
                "channel_id": channel.id,
                "curriculum_unit_id": self.unit.id,
                "coverage_type": "covers",
                "confidence": 1.0,
            }
        )
        coverage.action_approve()
        return coverage

    def test_submission_context_targets_explicit_gap_even_when_title_does_not_match(self):
        submission, candidate = self._candidate_from_submission()

        candidate.action_evaluate()

        self.assertEqual(candidate.coverage_score, 1.0)
        self.assertEqual(
            candidate.coverage_evidence["mode"],
            "curriculum-targeted-gap",
        )
        self.assertEqual(
            candidate.coverage_evidence["best_unit_id"],
            self.unit.id,
        )
        self.assertEqual(
            candidate.coverage_evidence["target_origin"],
            "accepted-submission",
        )
        self.assertEqual(
            candidate.coverage_evidence["submission_ids"],
            [submission.id],
        )
        self.assertTrue(
            any(
                "accepted submission context" in reason.lower()
                for reason in candidate.evaluation_reasons
            )
        )

    def test_targeted_gap_respects_existing_approved_coverage(self):
        self._approve_full_coverage()
        _submission, candidate = self._candidate_from_submission(
            "Another unrelated title"
        )

        candidate.action_evaluate()

        self.assertEqual(candidate.coverage_score, 0.0)
        self.assertEqual(
            candidate.coverage_evidence["mode"],
            "curriculum-targeted-gap",
        )
        self.assertEqual(
            candidate.coverage_evidence["approved_coverage_strength"],
            1.0,
        )

    def test_disabled_target_context_falls_back_to_existing_baseline(self):
        _submission, candidate = self._candidate_from_submission(
            "Unrelated while disabled"
        )
        self.reference.write({"selection_enabled": False})

        candidate.action_evaluate()

        self.assertEqual(candidate.coverage_evidence["mode"], "baseline")

    def test_generic_candidate_keeps_existing_curriculum_gap_matching(self):
        candidate = self.env["facodi.learning.course.candidate"].with_user(
            self.manager
        ).create(
            {
                "provider": "manual",
                "external_id": "generic-database-targeted-eval",
                "name": self.unit.name,
                "language": "pt",
            }
        )

        candidate.action_evaluate()

        self.assertEqual(candidate.coverage_evidence["mode"], "curriculum-gap")
        self.assertEqual(
            candidate.coverage_evidence["best_unit_id"],
            self.unit.id,
        )
