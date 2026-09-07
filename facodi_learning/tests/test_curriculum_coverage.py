from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCurriculumCoverage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref("base.group_user").id
        group_manager = cls.env.ref("website_slides.group_website_slides_manager").id
        group_officer = cls.env.ref("website_slides.group_website_slides_officer").id
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Coverage Manager",
                "login": "coverage-manager",
                "group_ids": [(6, 0, [group_user, group_manager])],
            }
        )
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Coverage Officer",
                "login": "coverage-officer",
                "group_ids": [(6, 0, [group_user, group_officer])],
            }
        )
        cls.other_officer = cls.env["res.users"].create(
            {
                "name": "Other Coverage Officer",
                "login": "other-coverage-officer",
                "group_ids": [(6, 0, [group_user, group_officer])],
            }
        )
        cls.portal = cls.env["res.users"].create(
            {
                "name": "Coverage Portal",
                "login": "coverage-portal",
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
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
            }
        )
        cls.unit = cls.env["facodi.learning.curriculum.unit"].with_user(
            cls.manager
        ).create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411017",
                "name": "Base de Dados II",
                "credits": 5.0,
            }
        )
        cls.owned_channel = cls.env["slide.channel"].create(
            {"name": "FACODI Database Course", "user_id": cls.officer.id}
        )
        cls.other_channel = cls.env["slide.channel"].create(
            {"name": "Other FACODI Course", "user_id": cls.other_officer.id}
        )

    def _values(self, **extra):
        values = {
            "channel_id": self.owned_channel.id,
            "curriculum_unit_id": self.unit.id,
            "coverage_type": "partial",
            "confidence": 0.7,
            "evidence": {"reason": "Covers normalization and transactions"},
        }
        values.update(extra)
        return values

    def test_curriculum_coverage_model_and_schema_exist(self):
        self.assertIn("facodi.learning.curriculum.coverage", self.env.registry.models)
        Coverage = self.env["facodi.learning.curriculum.coverage"]
        expected = {
            "channel_id",
            "curriculum_unit_id",
            "coverage_type",
            "confidence",
            "origin",
            "state",
            "evidence",
            "reviewed_by_id",
            "reviewed_at",
            "policy_version",
            "decision_snapshot",
        }
        self.assertTrue(expected <= set(Coverage._fields))

    def test_officer_can_create_manual_proposal_for_owned_course(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.officer
        ).create(self._values())
        self.assertEqual(coverage.state, "proposed")
        self.assertEqual(coverage.origin, "manual")
        self.assertEqual(coverage.coverage_type, "partial")

    def test_officer_cannot_create_coverage_for_another_course(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.officer
        )
        with self.assertRaises(AccessError):
            Coverage.create(self._values(channel_id=self.other_channel.id))

    def test_manager_reviews_and_officer_cannot_review(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.officer
        ).create(self._values())
        with self.assertRaises(AccessError):
            coverage.with_user(self.officer).action_approve()
        coverage.with_user(self.manager).action_approve()
        coverage.invalidate_recordset()
        self.assertEqual(coverage.state, "approved")
        self.assertEqual(coverage.reviewed_by_id, self.manager)
        self.assertTrue(coverage.reviewed_at)

    def test_reviewed_coverage_is_immutable(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.officer
        ).create(self._values())
        coverage.with_user(self.manager).action_approve()
        for values in ({"confidence": 0.9}, {"evidence": {"reason": "rewritten"}}):
            with self.assertRaises(AccessError):
                coverage.with_user(self.manager).write(values)
        with self.assertRaises(AccessError):
            coverage.with_user(self.manager).unlink()

    def test_duplicate_identity_and_invalid_confidence_are_rejected(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.manager
        )
        Coverage.create(self._values())
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            Coverage.create(self._values())
        for confidence in (-0.01, 1.01):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                Coverage.create(
                    self._values(coverage_type="covers", confidence=confidence)
                )

    def test_terminal_and_generated_provenance_cannot_be_forged(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"].with_user(
            self.officer
        )
        for forged in (
            {"state": "approved"},
            {"reviewed_by_id": self.manager.id},
            {"policy_version": "forged"},
            {"origin": "analysis"},
        ):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                Coverage.create(self._values(**forged))

    def test_public_and_portal_cannot_read_coverage(self):
        Coverage = self.env["facodi.learning.curriculum.coverage"]
        for user in (self.env.ref("base.public_user"), self.portal):
            with self.assertRaises(AccessError):
                Coverage.with_user(user).search([])
