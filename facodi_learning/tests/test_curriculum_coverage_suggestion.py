from odoo import Command
from odoo.exceptions import AccessError, ValidationError
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

    def test_selected_batch_generates_only_proposed_reviewable_rows(self):
        machine_learning = self.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": self.reference.id,
                "external_unit_code": "19411042",
                "name": "Aprendizagem Automática",
                "credits": 6.0,
                "curricular_year": 2,
            }
        )
        excluded = self.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": self.reference.id,
                "external_unit_code": "19411043",
                "name": "História da Arte Medieval",
                "curricular_year": 2,
            }
        )
        self.env["slide.channel"].create(
            {"name": "Aprendizagem Automática", "is_published": True}
        )

        selected = (self.unit | machine_learning).with_user(self.manager)
        action = selected.action_generate_selected_coverage_proposals()

        Coverage = self.env["facodi.learning.curriculum.coverage"]
        created = Coverage.search(
            [("curriculum_unit_id", "in", selected.ids)]
        )
        self.assertTrue(created)
        self.assertTrue(all(row.state == "proposed" for row in created))
        self.assertTrue(all(row.origin == "analysis" for row in created))
        self.assertFalse(Coverage.search_count(
            [("curriculum_unit_id", "=", excluded.id)]
        ))
        self.assertEqual(action["res_model"], "facodi.learning.curriculum.coverage")
        self.assertEqual(action["domain"][0][:2], ("id", "in"))
        self.assertEqual(set(action["domain"][0][2]), set(created.ids))

        # Replaying the same selection must not duplicate proposals nor
        # reopen prior decisions; the action shows the existing review queue.
        count = Coverage.search_count(
            [("curriculum_unit_id", "in", selected.ids)]
        )
        repeated = selected.action_generate_selected_coverage_proposals()
        self.assertEqual(
            count,
            Coverage.search_count([("curriculum_unit_id", "in", selected.ids)]),
        )
        self.assertEqual(
            repeated["domain"],
            [("curriculum_unit_id", "in", selected.ids), ("state", "=", "proposed")],
        )

    def test_selected_batch_is_manager_only_even_via_direct_orm_call(self):
        with self.assertRaises(AccessError):
            self.unit.with_user(self.officer).action_generate_selected_coverage_proposals()
        with self.assertRaises(AccessError):
            self.unit.with_user(self.officer).browse(
                []
            ).action_generate_selected_coverage_proposals()

    def test_selected_batch_rejects_empty_or_more_than_ten_units(self):
        Unit = self.env["facodi.learning.curriculum.unit"].with_user(self.manager)
        with self.assertRaises(ValidationError):
            Unit.browse().action_generate_selected_coverage_proposals()

        additional = Unit.create([
            {
                "reference_id": self.reference.id,
                "external_unit_code": f"bulk-guard-{index}",
                "name": f"Unit {index}",
            }
            for index in range(10)
        ])
        with self.assertRaises(ValidationError):
            (self.unit.with_user(self.manager) | additional).action_generate_selected_coverage_proposals()

        self.assertFalse(self.env["facodi.learning.curriculum.coverage"].search_count(
            [("curriculum_unit_id", "in", (self.unit | additional).ids)]
        ))

    def test_selected_batch_action_is_list_only_and_manager_bound(self):
        action = self.env.ref(
            "facodi_learning.action_facodi_curriculum_selected_suggestions"
        )
        self.assertEqual(action.model_id.model, "facodi.learning.curriculum.unit")
        self.assertEqual(action.binding_view_types, "list")
        self.assertEqual(action.state, "code")
        self.assertIn(
            self.env.ref("website_slides.group_website_slides_manager"),
            action.groups_id,
        )
