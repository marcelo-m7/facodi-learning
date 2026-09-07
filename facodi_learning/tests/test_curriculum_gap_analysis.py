from odoo import Command
from odoo.tests import TransactionCase


class TestCurriculumGapAnalysis(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Gap Analysis Manager",
                "login": "gap-analysis-manager",
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
                "external_id": "gap-ualg-1941-2026-27",
            }
        )
        cls.database_unit = cls.env["facodi.learning.curriculum.unit"].create(
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
        cls.programming_unit = cls.env["facodi.learning.curriculum.unit"].create(
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
        cls.ai_unit = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411022",
                "name": "Inteligência Artificial",
                "credits": 5.0,
                "curricular_year": 3,
                "period": "semester_1",
                "classification": "mandatory",
                "sequence": 30,
            }
        )
        cls.course_a = cls.env["slide.channel"].create({"name": "Databases A"})
        cls.course_b = cls.env["slide.channel"].create({"name": "Databases B"})

    def _coverage(self, unit, coverage_type="covers", course=None, state="approved"):
        coverage = self.env["facodi.learning.curriculum.coverage"].create(
            {
                "channel_id": (course or self.course_a).id,
                "curriculum_unit_id": unit.id,
                "coverage_type": coverage_type,
                "confidence": 0.8,
                "evidence": {"reason": f"{coverage_type} evidence"},
            }
        )
        if state == "approved":
            coverage.with_user(self.manager).action_approve()
        elif state == "rejected":
            coverage.with_user(self.manager).action_reject()
        return coverage

    def _unit_summary(self, unit):
        self.assertTrue(
            hasattr(unit, "_facodi_coverage_summary"),
            "M3.4 requires curriculum unit coverage summaries.",
        )
        return unit._facodi_coverage_summary()

    def _reference_summary(self):
        self.assertTrue(
            hasattr(self.reference, "_facodi_coverage_summary"),
            "M3.4 requires curriculum reference coverage summaries.",
        )
        return self.reference._facodi_coverage_summary()

    def test_unit_without_approved_coverage_is_gap(self):
        summary = self._unit_summary(self.database_unit)
        self.assertEqual(summary["schema_version"], "curriculum-coverage-v1")
        self.assertEqual(summary["status"], "gap")
        self.assertEqual(summary["approved_relations"], [])

    def test_proposed_and_rejected_coverage_do_not_close_gap(self):
        self._coverage(self.database_unit, "partial", state="proposed")
        self._coverage(self.database_unit, "supports", course=self.course_b, state="rejected")
        summary = self._unit_summary(self.database_unit)
        self.assertEqual(summary["status"], "gap")
        self.assertEqual(summary["approved_relations"], [])

    def test_partial_or_supports_only_is_partial(self):
        self._coverage(self.database_unit, "partial")
        self._coverage(self.database_unit, "supports", course=self.course_b)
        summary = self._unit_summary(self.database_unit)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(
            {item["coverage_type"] for item in summary["approved_relations"]},
            {"partial", "supports"},
        )

    def test_covers_marks_unit_covered(self):
        self._coverage(self.database_unit, "covers")
        self.assertEqual(self._unit_summary(self.database_unit)["status"], "covered")

    def test_equivalent_marks_unit_covered_without_credit_claim(self):
        self._coverage(self.database_unit, "equivalent")
        summary = self._unit_summary(self.database_unit)
        self.assertEqual(summary["status"], "covered")
        self.assertNotIn("recognized_credits", summary)
        self.assertNotIn("academic_equivalence", summary)
        self.assertNotIn("ects_awarded", summary)

    def test_multiple_courses_are_returned_in_stable_order(self):
        self._coverage(self.database_unit, "supports", course=self.course_b)
        self._coverage(self.database_unit, "partial", course=self.course_a)
        summary = self._unit_summary(self.database_unit)
        pairs = [
            (item["channel_id"], item["coverage_type"])
            for item in summary["approved_relations"]
        ]
        self.assertEqual(pairs, sorted(pairs))

    def test_reference_summary_counts_gap_partial_and_covered_units(self):
        self._coverage(self.programming_unit, "covers")
        self._coverage(self.database_unit, "partial")
        summary = self._reference_summary()
        self.assertEqual(summary["unit_count"], 3)
        self.assertEqual(summary["covered_count"], 1)
        self.assertEqual(summary["partial_count"], 1)
        self.assertEqual(summary["gap_count"], 1)
        self.assertEqual(
            [item["unit_id"] for item in summary["units"]],
            [self.programming_unit.id, self.database_unit.id, self.ai_unit.id],
        )

    def test_summary_is_deterministic(self):
        self._coverage(self.database_unit, "partial")
        first = self._reference_summary()
        self.reference.invalidate_recordset()
        self.database_unit.invalidate_recordset()
        second = self._reference_summary()
        self.assertEqual(first, second)

    def test_summary_contains_no_learner_membership_or_progress(self):
        self._coverage(self.database_unit, "covers")
        before = self._reference_summary()
        partner = self.env["res.partner"].create({"name": "Curriculum Learner"})
        self.env["slide.channel.partner"].create(
            {"channel_id": self.course_a.id, "partner_id": partner.id}
        )
        self.reference.invalidate_recordset()
        after = self._reference_summary()
        self.assertEqual(before, after)
        serialized = str(after).lower()
        for forbidden in ("partner", "learner", "progress", "completion", "email"):
            self.assertNotIn(forbidden, serialized)
