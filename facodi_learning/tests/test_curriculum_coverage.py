from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCurriculumCoverage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Coverage Manager",
                "login": "coverage-manager",
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
                "name": "Coverage Officer",
                "login": "coverage-officer",
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
        cls.other_officer = cls.env["res.users"].create(
            {
                "name": "Other Coverage Officer",
                "login": "other-coverage-officer",
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
        cls.portal = cls.env["res.users"].create(
            {
                "name": "Coverage Portal",
                "login": "coverage-portal",
                "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
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
                "external_id": "coverage-ualg-1941-2026-27",
            }
        )
        cls.unit = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411017",
                "name": "Base de Dados II",
                "credits": 5.0,
                "curricular_year": 2,
                "period": "semester_2",
                "classification": "mandatory",
            }
        )
        cls.source = cls.env["slide.channel"].create(
            {"name": "FACODI Databases", "user_id": cls.officer.id}
        )
        cls.other_source = cls.env["slide.channel"].create(
            {"name": "FACODI Other", "user_id": cls.other_officer.id}
        )

    def _vals(self, **extra):
        values = {
            "channel_id": self.source.id,
            "curriculum_unit_id": self.unit.id,
            "coverage_type": "covers",
            "confidence": 0.8,
            "evidence": {"reason": "Reviewed syllabus coverage"},
        }
        values.update(extra)
        return values

    def test_curriculum_coverage_unique_course_unit_type(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"]
        Coverage.create(self._vals())
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            Coverage.create(self._vals())

    def test_curriculum_coverage_rejects_confidence_outside_zero_one(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"]
        for confidence in (-0.01, 1.01):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                Coverage.create(
                    self._vals(
                        coverage_type="partial" if confidence < 0 else "supports",
                        confidence=confidence,
                    )
                )

    def test_manual_proposal_starts_proposed(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].create(self._vals())
        self.assertEqual(coverage.origin, "manual")
        self.assertEqual(coverage.state, "proposed")
        self.assertFalse(coverage.evaluation_version)
        self.assertFalse(coverage.reviewed_by_id)
        self.assertFalse(coverage.reviewed_at)

    def test_direct_terminal_state_is_rejected_on_create(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"]
        for state in ("approved", "rejected"):
            with self.assertRaises(AccessError):
                Coverage.create(self._vals(state=state))

    def test_direct_generated_provenance_is_rejected_on_create(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"]
        with self.assertRaises(AccessError):
            Coverage.create(self._vals(origin="analysis"))
        with self.assertRaises(AccessError):
            Coverage.create(self._vals(evaluation_version="forged-v1"))

    def test_officer_can_propose_coverage_for_owned_course(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.officer
        ).create(self._vals())
        self.assertEqual(coverage.channel_id, self.source)
        self.assertEqual(coverage.state, "proposed")

    def test_officer_cannot_propose_coverage_for_another_course(self):
        with self.assertRaises(AccessError):
            self.env["facodi.learning.curriculum.coverage"].with_user(
                self.officer
            ).create(self._vals(channel_id=self.other_source.id))

    def test_officer_cannot_review_coverage(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.officer
        ).create(self._vals())
        with self.assertRaises(AccessError):
            coverage.action_approve()
        with self.assertRaises(AccessError):
            coverage.action_reject()

    def test_manager_can_approve_coverage(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].create(self._vals())
        coverage.with_user(self.manager).action_approve()
        coverage.invalidate_recordset()
        self.assertEqual(coverage.state, "approved")
        self.assertEqual(coverage.reviewed_by_id, self.manager)
        self.assertTrue(coverage.reviewed_at)

    def test_reviewed_coverage_is_immutable(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].create(self._vals())
        coverage.with_user(self.manager).action_reject()
        coverage.invalidate_recordset()
        with self.assertRaises(AccessError):
            coverage.with_user(self.manager).write({"confidence": 0.2})
        with self.assertRaises(AccessError):
            coverage.with_user(self.manager).unlink()

    def test_generated_coverage_evidence_is_immutable(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"]
        coverage = Coverage._create_generated(
            self._vals(
                coverage_type="partial",
                evaluation_version="curriculum-coverage-eval-v1",
            )
        )
        self.assertEqual(coverage.origin, "analysis")
        with self.assertRaises(AccessError):
            coverage.write({"confidence": 0.1})
        with self.assertRaises(AccessError):
            coverage.write({"evidence": {"forged": True}})
        with self.assertRaises(AccessError):
            coverage.unlink()

    def test_public_and_portal_cannot_read_curriculum_coverage(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].create(self._vals())
        public = self.env.ref("base.public_user")
        for user in (public, self.portal):
            with self.assertRaises(AccessError):
                coverage.with_user(user).read(["confidence", "evidence"])

    def test_coverage_review_does_not_write_course_or_curriculum_unit(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].create(
            self._vals(coverage_type="equivalent")
        )
        course_before = self.source.read(
            ["name", "website_published", "prerequisite_channel_ids"]
        )[0]
        unit_before = self.unit.read(
            ["name", "credits", "curricular_year", "period", "classification"]
        )[0]

        coverage.with_user(self.manager).action_approve()

        self.source.invalidate_recordset()
        self.unit.invalidate_recordset()
        course_after = self.source.read(
            ["name", "website_published", "prerequisite_channel_ids"]
        )[0]
        unit_after = self.unit.read(
            ["name", "credits", "curricular_year", "period", "classification"]
        )[0]
        self.assertEqual(course_before, course_after)
        self.assertEqual(unit_before, unit_after)
