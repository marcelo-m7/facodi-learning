from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCurriculumReference(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Curriculum Manager",
                "login": "curriculum-manager",
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
                "name": "Curriculum Officer",
                "login": "curriculum-officer",
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
                "name": "Curriculum Portal",
                "login": "curriculum-portal",
                "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
            }
        )

    def _reference_vals(self, **extra):
        values = {
            "institution": "Universidade do Algarve",
            "programme_name": "Engenharia de Sistemas e Tecnologias Informáticas",
            "external_programme_code": "1941",
            "academic_year": "2026/27",
            "source_url": "https://www.ualg.pt/curso/1941/plano",
            "provider": "manual",
            "external_id": "ualg-1941-2026-27",
        }
        values.update(extra)
        return values

    def _unit_vals(self, reference, **extra):
        values = {
            "reference_id": reference.id,
            "external_unit_code": "19411017",
            "name": "Base de Dados II",
            "credits": 5.0,
            "curricular_year": 2,
            "period": "semester_2",
            "classification": "mandatory",
            "sequence": 20,
        }
        values.update(extra)
        return values

    def test_curriculum_reference_identity_is_unique(self):
        Reference = self.env["facodi.learning.curriculum.reference"]
        Reference.create(self._reference_vals())
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            Reference.create(self._reference_vals())

    def test_curriculum_unit_code_is_unique_within_reference(self):
        reference = self.env["facodi.learning.curriculum.reference"].create(
            self._reference_vals()
        )
        Unit = self.env["facodi.learning.curriculum.unit"]
        Unit.create(self._unit_vals(reference))
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            Unit.create(self._unit_vals(reference))

    def test_same_unit_code_can_exist_in_different_reference_versions(self):
        Reference = self.env["facodi.learning.curriculum.reference"]
        first = Reference.create(self._reference_vals())
        second = Reference.create(
            self._reference_vals(
                academic_year="2025/26",
                external_id="ualg-1941-2025-26",
            )
        )
        Unit = self.env["facodi.learning.curriculum.unit"]
        Unit.create(self._unit_vals(first))
        older = Unit.create(self._unit_vals(second))
        self.assertEqual(older.external_unit_code, "19411017")

    def test_reference_preserves_academic_year_and_source_facts(self):
        reference = self.env["facodi.learning.curriculum.reference"].create(
            self._reference_vals(
                metadata={"source_kind": "official_study_plan"},
            )
        )
        self.assertEqual(reference.institution, "Universidade do Algarve")
        self.assertEqual(reference.external_programme_code, "1941")
        self.assertEqual(reference.academic_year, "2026/27")
        self.assertEqual(reference.provider, "manual")
        self.assertEqual(reference.external_id, "ualg-1941-2026-27")
        self.assertEqual(
            reference.source_url,
            "https://www.ualg.pt/curso/1941/plano",
        )
        self.assertEqual(reference.metadata, {"source_kind": "official_study_plan"})
        self.assertTrue(reference.imported_at)
        self.assertIn("2026/27", reference.name)

    def test_unit_preserves_year_period_credits_and_option_group(self):
        reference = self.env["facodi.learning.curriculum.reference"].create(
            self._reference_vals()
        )
        unit = self.env["facodi.learning.curriculum.unit"].create(
            self._unit_vals(
                reference,
                external_unit_code="19411035",
                name="Estágio",
                credits=30.0,
                curricular_year=3,
                period="annual",
                classification="optional",
                option_group="Final Project / Internship",
            )
        )
        self.assertEqual(unit.credits, 30.0)
        self.assertEqual(unit.curricular_year, 3)
        self.assertEqual(unit.period, "annual")
        self.assertEqual(unit.classification, "optional")
        self.assertEqual(unit.option_group, "Final Project / Internship")

    def test_invalid_credits_and_curricular_year_are_rejected(self):
        reference = self.env["facodi.learning.curriculum.reference"].create(
            self._reference_vals()
        )
        Unit = self.env["facodi.learning.curriculum.unit"]
        for values in (
            {"credits": -1.0},
            {"curricular_year": -1},
        ):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                Unit.create(self._unit_vals(reference, **values))

    def test_officer_can_read_reference_and_unit(self):
        reference = self.env["facodi.learning.curriculum.reference"].create(
            self._reference_vals()
        )
        unit = self.env["facodi.learning.curriculum.unit"].create(
            self._unit_vals(reference)
        )
        self.assertEqual(
            reference.with_user(self.officer).read(["programme_name"])[0][
                "programme_name"
            ],
            "Engenharia de Sistemas e Tecnologias Informáticas",
        )
        self.assertEqual(
            unit.with_user(self.officer).read(["name"])[0]["name"],
            "Base de Dados II",
        )

    def test_officer_cannot_create_or_edit_reference_or_unit(self):
        Reference = self.env["facodi.learning.curriculum.reference"]
        Unit = self.env["facodi.learning.curriculum.unit"]
        reference = Reference.create(self._reference_vals())
        unit = Unit.create(self._unit_vals(reference))

        with self.assertRaises(AccessError):
            Reference.with_user(self.officer).create(
                self._reference_vals(external_id="officer-forged-reference")
            )
        with self.assertRaises(AccessError):
            reference.with_user(self.officer).write({"academic_year": "2099/00"})
        with self.assertRaises(AccessError):
            Unit.with_user(self.officer).create(
                self._unit_vals(reference, external_unit_code="forged-unit")
            )
        with self.assertRaises(AccessError):
            unit.with_user(self.officer).write({"credits": 99.0})

    def test_public_and_portal_cannot_read_curriculum_reference_or_unit(self):
        reference = self.env["facodi.learning.curriculum.reference"].create(
            self._reference_vals()
        )
        unit = self.env["facodi.learning.curriculum.unit"].create(
            self._unit_vals(reference)
        )
        public = self.env.ref("base.public_user")
        for user in (public, self.portal):
            with self.assertRaises(AccessError):
                reference.with_user(user).read(["programme_name"])
            with self.assertRaises(AccessError):
                unit.with_user(user).read(["name"])
