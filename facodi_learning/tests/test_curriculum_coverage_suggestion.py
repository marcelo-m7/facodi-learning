from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase

from ..services.curriculum_coverage_suggestion import (
    CURRICULUM_COVERAGE_RANKING_VERSION,
    curriculum_coverage_candidates,
    propose_curriculum_coverage,
)


class TestCurriculumCoverageSuggestions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Coverage Suggestion Manager",
                "login": "coverage-suggestion-manager",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id,
                        ]
                    )
                ],
            }
        )
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Coverage Suggestion Officer",
                "login": "coverage-suggestion-officer",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id,
                        ]
                    )
                ],
            }
        )
        cls.reference = cls.env["facodi.learning.curriculum.reference"].create(
            {
                "institution": "Universidade do Algarve",
                "programme_name": "Engenharia de Sistemas e Tecnologias Informáticas",
                "external_programme_code": "1941",
                "academic_year": "2026/27",
                "source_url": "https://www.ualg.pt/curso/1941/plano",
                "provider": "manual",
                "external_id": "coverage-suggestion-ualg-1941-2026-27",
            }
        )
        cls.unit = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411003",
                "name": "Programação",
                "credits": 6.0,
                "curricular_year": 1,
                "period": "semester_1",
                "classification": "mandatory",
            }
        )
        cls.programming = cls.env["slide.channel"].create(
            {
                "name": "Programação em Python",
                "description_short": "Fundamentos de programação, funções e estruturas de dados.",
                "is_published": True,
            }
        )
        cls.unrelated = cls.env["slide.channel"].create(
            {
                "name": "História da Arte Medieval",
                "description_short": "Arquitetura, pintura e cultura visual medieval.",
                "is_published": True,
            }
        )

    def test_ranking_is_versioned_and_never_claims_full_coverage(self):
        candidates = curriculum_coverage_candidates(self.unit)
        programming = next(
            row for row in candidates if row["channel_id"] == self.programming.id
        )
        self.assertEqual(
            programming["evaluation_version"],
            CURRICULUM_COVERAGE_RANKING_VERSION,
        )
        self.assertIn(programming["coverage_type"], {"supports", "partial"})
        self.assertNotIn(programming["coverage_type"], {"covers", "equivalent"})
        self.assertEqual(
            programming["evidence"]["course_profile_version"],
            "course-profile-v1",
        )
        self.assertIn("signals", programming["evidence"])
        self.assertIn("boundary", programming["evidence"])

    def test_ranking_applies_limit_after_scoring_all_published_courses(self):
        fillers = self.env["slide.channel"]
        for index in range(25):
            fillers |= self.env["slide.channel"].create(
                {
                    "name": f"Unrelated filler course {index:02d}",
                    "description_short": "Generic unrelated material.",
                    "sequence": index,
                    "is_published": True,
                }
            )
        self.programming.sequence = 999

        candidates = curriculum_coverage_candidates(self.unit, limit=5)

        self.assertEqual(len(candidates), 5)
        self.assertIn(self.programming.id, [row["channel_id"] for row in candidates])
        self.assertNotEqual(
            [row["channel_id"] for row in candidates],
            fillers.sorted(key=lambda channel: (channel.sequence, channel.id))[:5].ids,
        )

    def test_generation_creates_review_only_analysis_proposals(self):
        created = propose_curriculum_coverage(
            self.unit.with_user(self.manager),
            limit=20,
        )
        proposal = created.filtered(
            lambda item: item.channel_id == self.programming
        )
        self.assertEqual(len(proposal), 1)
        self.assertEqual(proposal.origin, "analysis")
        self.assertEqual(proposal.state, "proposed")
        self.assertEqual(
            proposal.evaluation_version,
            CURRICULUM_COVERAGE_RANKING_VERSION,
        )
        self.assertIn(proposal.coverage_type, {"supports", "partial"})
        self.assertFalse(proposal.reviewed_by_id)
        self.assertFalse(proposal.reviewed_at)

    def test_replay_does_not_duplicate_existing_proposal(self):
        first = propose_curriculum_coverage(
            self.unit.with_user(self.manager),
            limit=20,
        )
        before = self.env["facodi.learning.curriculum.coverage"].search_count(
            [("curriculum_unit_id", "=", self.unit.id)]
        )
        second = propose_curriculum_coverage(
            self.unit.with_user(self.manager),
            limit=20,
        )
        after = self.env["facodi.learning.curriculum.coverage"].search_count(
            [("curriculum_unit_id", "=", self.unit.id)]
        )
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(before, after)

    def test_replay_never_reopens_terminal_decision(self):
        existing = self.env["facodi.learning.curriculum.coverage"].create(
            {
                "channel_id": self.programming.id,
                "curriculum_unit_id": self.unit.id,
                "coverage_type": "supports",
                "confidence": 0.8,
                "evidence": {"reason": "Manual editorial decision"},
            }
        )
        existing.with_user(self.manager).action_reject()
        created = propose_curriculum_coverage(
            self.unit.with_user(self.manager),
            limit=20,
        )
        existing.invalidate_recordset()
        same_pair = self.env["facodi.learning.curriculum.coverage"].search(
            [
                ("channel_id", "=", self.programming.id),
                ("curriculum_unit_id", "=", self.unit.id),
            ]
        )
        self.assertEqual(existing.state, "rejected")
        self.assertEqual(same_pair, existing)
        self.assertNotIn(self.programming, created.mapped("channel_id"))

    def test_low_similarity_course_is_not_proposed(self):
        propose_curriculum_coverage(
            self.unit.with_user(self.manager),
            limit=20,
        )
        unrelated = self.env["facodi.learning.curriculum.coverage"].search(
            [
                ("channel_id", "=", self.unrelated.id),
                ("curriculum_unit_id", "=", self.unit.id),
            ]
        )
        self.assertFalse(unrelated)

    def test_only_manager_can_generate_suggestions(self):
        with self.assertRaises(AccessError):
            propose_curriculum_coverage(
                self.unit.with_user(self.officer),
                limit=20,
            )
