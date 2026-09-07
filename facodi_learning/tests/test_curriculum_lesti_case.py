from odoo import Command
from odoo.tests import TransactionCase


class TestCurriculumLestiCase(TransactionCase):
    """Validate M3.4 with official-plan-shaped LESTI facts only.

    This fixture is not production seed data and does not assert an official
    FACODI/UAlg equivalence, credit award, prerequisite, or learner pathway.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "LESTI Validation Manager",
                "login": "lesti-validation-manager",
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
        cls.reference = cls.env["facodi.learning.curriculum.reference"].create(
            {
                "institution": "Universidade do Algarve",
                "programme_name": "Engenharia de Sistemas e Tecnologias Informáticas",
                "external_programme_code": "1941",
                "academic_year": "2026/27",
                "source_url": "https://www.ualg.pt/curso/1941/plano",
                "provider": "manual",
                "external_id": "ualg-1941-2026-27-lesti-acceptance",
            }
        )
        cls.programming = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411000",
                "name": "Programação",
                "credits": 5.0,
                "curricular_year": 1,
                "period": "semester_1",
                "classification": "mandatory",
                "sequence": 10,
            }
        )
        cls.database_ii = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411017",
                "name": "Base de Dados II",
                "credits": 5.0,
                "curricular_year": 2,
                "period": "semester_2",
                "classification": "mandatory",
                "sequence": 20,
            }
        )
        cls.internship = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411035",
                "name": "Estágio",
                "credits": 30.0,
                "curricular_year": 3,
                "period": "semester_2",
                "classification": "optional",
                "option_group": "OPÇÃO VIII (CI)",
                "sequence": 30,
            }
        )
        cls.project = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411036",
                "name": "Projeto",
                "credits": 30.0,
                "curricular_year": 3,
                "period": "semester_2",
                "classification": "optional",
                "option_group": "OPÇÃO VIII (CI)",
                "sequence": 40,
            }
        )
        cls.course_a = cls.env["slide.channel"].create(
            {"name": "FACODI Programming and Data Foundations"}
        )
        cls.course_b = cls.env["slide.channel"].create(
            {"name": "FACODI Database Practice"}
        )

    def _approve(self, course, unit, coverage_type):
        relation = self.env["facodi.learning.curriculum.coverage"].create(
            {
                "channel_id": course.id,
                "curriculum_unit_id": unit.id,
                "coverage_type": coverage_type,
                "confidence": 0.8,
                "evidence": {"fixture": "LESTI 2026/27 validation"},
            }
        )
        relation.with_user(self.manager).action_approve()
        return relation

    def test_option_group_is_source_fact_not_prerequisite_or_equivalence(self):
        self.assertEqual(self.internship.option_group, "OPÇÃO VIII (CI)")
        self.assertEqual(self.project.option_group, "OPÇÃO VIII (CI)")
        self.assertEqual(self.internship.credits, 30.0)
        self.assertEqual(self.project.credits, 30.0)
        self.assertFalse(self.course_a.prerequisite_channel_ids)
        self.assertFalse(self.course_b.prerequisite_channel_ids)
        self.assertFalse(
            self.env["facodi.learning.curriculum.coverage"].search(
                [
                    ("curriculum_unit_id", "in", [self.internship.id, self.project.id])
                ]
            )
        )

    def test_year_period_sequence_never_infer_native_prerequisites(self):
        before_a = self.course_a.prerequisite_channel_ids.ids
        before_b = self.course_b.prerequisite_channel_ids.ids
        self.reference._facodi_coverage_summary()
        self.programming._facodi_coverage_summary()
        self.database_ii._facodi_coverage_summary()
        self.course_a.invalidate_recordset()
        self.course_b.invalidate_recordset()
        self.assertEqual(self.course_a.prerequisite_channel_ids.ids, before_a)
        self.assertEqual(self.course_b.prerequisite_channel_ids.ids, before_b)

    def test_many_to_many_coverage_and_gap_statuses_use_approved_evidence_only(self):
        self._approve(self.course_a, self.programming, "covers")
        self._approve(self.course_a, self.database_ii, "partial")
        self._approve(self.course_b, self.database_ii, "supports")

        course_a_relations = self.env["facodi.learning.curriculum.coverage"].search(
            [("channel_id", "=", self.course_a.id), ("state", "=", "approved")]
        )
        database_relations = self.env["facodi.learning.curriculum.coverage"].search(
            [
                ("curriculum_unit_id", "=", self.database_ii.id),
                ("state", "=", "approved"),
            ]
        )
        self.assertEqual(len(course_a_relations), 2)
        self.assertEqual(len(database_relations), 2)

        summary = self.reference._facodi_coverage_summary()
        statuses = {item["unit_id"]: item["status"] for item in summary["units"]}
        self.assertEqual(statuses[self.programming.id], "covered")
        self.assertEqual(statuses[self.database_ii.id], "partial")
        self.assertEqual(statuses[self.internship.id], "gap")
        self.assertEqual(statuses[self.project.id], "gap")

    def test_m3_4_exposes_no_official_credit_recognition_contract(self):
        forbidden_fields = {
            "recognized_credits",
            "ects_awarded",
            "credits_awarded",
            "official_equivalence",
            "academic_equivalence",
            "official_prerequisite",
        }
        for model_name in (
            "facodi.learning.curriculum.reference",
            "facodi.learning.curriculum.unit",
            "facodi.learning.curriculum.coverage",
        ):
            model = self.env[model_name]
            self.assertFalse(forbidden_fields.intersection(model._fields))
            for method_name in (
                "action_recognize_ects",
                "action_grant_credits",
                "action_award_ects",
                "action_official_equivalence",
            ):
                self.assertFalse(hasattr(model, method_name))
