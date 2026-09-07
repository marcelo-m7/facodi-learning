from odoo.tests import TransactionCase


class TestCurriculumGap(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Curriculum Gap Manager",
                "login": "curriculum-gap-manager",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("website_slides.group_website_slides_manager").id,
                        ],
                    )
                ],
            }
        )
        cls.reference = cls.env["facodi.learning.curriculum.reference"].with_user(
            cls.manager
        ).create(
            {
                "institution": "Universidade do Algarve",
                "programme_name": "Engenharia de Sistemas e Tecnologias Informáticas",
                "external_programme_code": "1941",
                "academic_year": "2026/27",
                "source_url": "https://www.ualg.pt/curso/1941/plano",
                "provider": "ualg-public-plan",
                "selection_enabled": True,
            }
        )
        Unit = cls.env["facodi.learning.curriculum.unit"].with_user(cls.manager)
        cls.database_ii = Unit.create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411017",
                "name": "Base de Dados II",
                "credits": 5.0,
                "curricular_year": 2,
                "period": "semester_2",
                "sequence": 10,
            }
        )
        cls.software_engineering = Unit.create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411016",
                "name": "Engenharia de Software",
                "credits": 5.0,
                "curricular_year": 2,
                "sequence": 20,
            }
        )
        cls.artificial_intelligence = Unit.create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411022",
                "name": "Inteligência Artificial",
                "credits": 5.0,
                "curricular_year": 3,
                "sequence": 30,
            }
        )
        cls.channel = cls.env["slide.channel"].create(
            {"name": "FACODI Database Coverage"}
        )

    def _approved_coverage(self, unit, coverage_type="covers", confidence=1.0):
        coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.manager
        ).create(
            {
                "channel_id": self.channel.id,
                "curriculum_unit_id": unit.id,
                "coverage_type": coverage_type,
                "confidence": confidence,
            }
        )
        coverage.action_approve()
        return coverage

    def _service(self):
        from ..services import curriculum_coverage

        return curriculum_coverage

    def test_uncovered_matching_lesti_unit_has_high_need(self):
        service = self._service()
        context = service.build_curriculum_selection_context(self.env)
        result = service.score_candidate_curriculum_gap("Base de Dados II", context)
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["evidence"]["best_unit_code"], "19411017")
        self.assertEqual(result["evidence"]["best_academic_year"], "2026/27")

    def test_approved_full_coverage_removes_gap_priority(self):
        service = self._service()
        self._approved_coverage(self.database_ii, "covers", 1.0)
        context = service.build_curriculum_selection_context(self.env)
        result = service.score_candidate_curriculum_gap("Base de Dados II", context)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["evidence"]["approved_coverage_strength"], 1.0)

    def test_proposed_or_rejected_coverage_does_not_reduce_gap(self):
        service = self._service()
        Coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.manager
        )
        proposed = Coverage.create(
            {
                "channel_id": self.channel.id,
                "curriculum_unit_id": self.database_ii.id,
                "coverage_type": "covers",
                "confidence": 1.0,
            }
        )
        context = service.build_curriculum_selection_context(self.env)
        self.assertEqual(
            service.score_candidate_curriculum_gap("Base de Dados II", context)["score"],
            1.0,
        )
        proposed.action_reject()
        context = service.build_curriculum_selection_context(self.env)
        self.assertEqual(
            service.score_candidate_curriculum_gap("Base de Dados II", context)["score"],
            1.0,
        )

    def test_partial_and_support_coverage_use_weighted_strength(self):
        service = self._service()
        self._approved_coverage(self.database_ii, "partial", 0.8)
        strength = service.coverage_strength_for_unit(self.database_ii)
        self.assertEqual(strength, 0.4)
        context = service.build_curriculum_selection_context(self.env)
        result = service.score_candidate_curriculum_gap("Base de Dados II", context)
        self.assertEqual(result["score"], 0.6)

    def test_no_enabled_reference_preserves_m31_baseline(self):
        service = self._service()
        self.reference.selection_enabled = False
        context = service.build_curriculum_selection_context(self.env)
        result = service.score_candidate_curriculum_gap("Anything", context)
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["evidence"]["mode"], "baseline")

    def test_gap_evidence_contains_no_prerequisite_or_learner_data(self):
        service = self._service()
        result = service.score_candidate_curriculum_gap(
            "Base de Dados II", service.build_curriculum_selection_context(self.env)
        )
        forbidden = {
            "prerequisite_channel_ids",
            "partner_id",
            "email",
            "progress",
            "credits_recognized",
        }
        self.assertFalse(forbidden & set(result["evidence"]))
