from odoo.tests import TransactionCase


class TestCurriculumCandidateSelection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Curriculum Selection Manager",
                "login": "curriculum-selection-manager",
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
        cls.database_ii = cls.env["facodi.learning.curriculum.unit"].with_user(
            cls.manager
        ).create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411017",
                "name": "Base de Dados II",
                "credits": 5.0,
                "curricular_year": 2,
                "period": "semester_2",
            }
        )
        cls.coverage_channel = cls.env["slide.channel"].create(
            {"name": "FACODI Existing Database Coverage"}
        )

    def _candidate(self, name="Base de Dados II", external_id=None):
        external_id = external_id or f"curriculum-candidate-{name.lower().replace(' ', '-')}"
        return self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
            {
                "provider": "manual",
                "external_id": external_id,
                "name": name,
                "description": f"Complete learning resource for {name}.",
                "institution": "FACODI",
                "language": "pt",
                "level": "undergraduate",
                "duration_minutes": 120,
            }
        )

    def _approved_full_coverage(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.manager
        ).create(
            {
                "channel_id": self.coverage_channel.id,
                "curriculum_unit_id": self.database_ii.id,
                "coverage_type": "covers",
                "confidence": 1.0,
            }
        )
        coverage.action_approve()
        return coverage

    def test_candidate_uses_enabled_curriculum_gap(self):
        candidate = self._candidate(external_id="curriculum-gap-uncovered")
        candidate.action_evaluate()
        self.assertEqual(candidate.coverage_score, 1.0)
        self.assertEqual(candidate.coverage_evidence["mode"], "curriculum-gap")
        self.assertEqual(candidate.coverage_evidence["best_unit_code"], "19411017")
        self.assertEqual(candidate.coverage_evidence["best_academic_year"], "2026/27")

    def test_existing_approved_coverage_lowers_candidate_coverage_score(self):
        self._approved_full_coverage()
        candidate = self._candidate(external_id="curriculum-gap-covered")
        candidate.action_evaluate()
        self.assertEqual(candidate.coverage_score, 0.0)
        self.assertEqual(candidate.coverage_evidence["approved_coverage_strength"], 1.0)

    def test_no_enabled_curriculum_preserves_m31_baseline(self):
        self.reference.with_user(self.manager).write({"selection_enabled": False})
        candidate = self._candidate("Anything", "curriculum-baseline")
        candidate.action_evaluate()
        self.assertEqual(candidate.coverage_score, 1.0)
        self.assertEqual(candidate.coverage_evidence["mode"], "baseline")

    def test_terminal_snapshot_preserves_curriculum_evidence(self):
        candidate = self._candidate(external_id="curriculum-snapshot")
        candidate.action_evaluate()
        evidence = dict(candidate.coverage_evidence)
        candidate.action_resolve_new()
        self.assertEqual(candidate.decision_snapshot["coverage_evidence"], evidence)

    def test_auto_approve_fails_closed_when_curriculum_gap_score_is_below_threshold(self):
        self._approved_full_coverage()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("facodi_learning.course_selection_mode", "auto")
        params.set_param("facodi_learning.auto_approve_trusted_providers", "manual")
        params.set_param("facodi_learning.auto_approve_min_coverage", "0.65")
        candidate = self._candidate(external_id="curriculum-auto-blocked")
        candidate.action_evaluate()
        self.assertEqual(candidate.coverage_score, 0.0)
        self.assertNotEqual(candidate.state, "resolved")
        self.assertFalse(candidate.resolved_channel_id)
