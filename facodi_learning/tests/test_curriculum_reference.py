from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCurriculumReference(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create({"name": "Curriculum Manager", "login": "curriculum-manager", "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref("website_slides.group_website_slides_manager").id])]})
        cls.officer = cls.env["res.users"].create({"name": "Curriculum Officer", "login": "curriculum-officer", "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref("website_slides.group_website_slides_officer").id])]})
        cls.portal = cls.env["res.users"].create({"name": "Curriculum Portal", "login": "curriculum-portal", "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])]})
        cls.public = cls.env["res.users"].create({"name": "Curriculum Public", "login": "curriculum-public", "group_ids": [(6, 0, [cls.env.ref("base.group_public").id])]})

    def _reference_values(self, **extra):
        values = {"institution": "Universidade do Algarve", "programme_name": "Engenharia de Sistemas e Tecnologias Informáticas", "external_programme_code": "1941", "academic_year": "2026/27", "source_url": "https://www.ualg.pt/curso/1941/plano", "provider": "ualg-public-plan", "selection_enabled": True}
        values.update(extra)
        return values

    def test_curriculum_models_exist(self):
        self.assertIn("facodi.learning.curriculum.reference", self.env.registry.models)
        self.assertIn("facodi.learning.curriculum.unit", self.env.registry.models)

    def test_manager_can_create_reference_and_unit(self):
        Reference = self.env["facodi.learning.curriculum.reference"].with_user(self.manager)
        Unit = self.env["facodi.learning.curriculum.unit"].with_user(self.manager)
        reference = Reference.create(self._reference_values())
        unit = Unit.create({"reference_id": reference.id, "external_unit_code": "19411017", "name": "Base de Dados II", "credits": 5.0, "curricular_year": 2, "period": "semester_2", "classification": "mandatory", "sequence": 20})
        self.assertEqual(unit.reference_id, reference)
        self.assertEqual(unit.credits, 5.0)
        self.assertTrue(reference.selection_enabled)

    def test_duplicate_reference_version_is_rejected(self):
        Reference = self.env["facodi.learning.curriculum.reference"].with_user(self.manager)
        Reference.create(self._reference_values())
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            Reference.create(self._reference_values())

    def test_invalid_credits_and_year_are_rejected(self):
        Reference = self.env["facodi.learning.curriculum.reference"].with_user(self.manager)
        Unit = self.env["facodi.learning.curriculum.unit"].with_user(self.manager)
        reference = Reference.create(self._reference_values())
        for vals in ({"credits": -1.0, "curricular_year": 1}, {"credits": 5.0, "curricular_year": -1}):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                Unit.create({"reference_id": reference.id, "external_unit_code": "invalid-%s" % vals["credits"], "name": "Invalid Unit", **vals})

    def test_blank_reference_and_unit_names_are_rejected(self):
        Reference = self.env["facodi.learning.curriculum.reference"].with_user(self.manager)
        Unit = self.env["facodi.learning.curriculum.unit"].with_user(self.manager)
        for field_name in ("institution", "programme_name", "academic_year", "provider", "source_url"):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                Reference.create(self._reference_values(**{field_name: "   "}))
        reference = Reference.create(self._reference_values())
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            Unit.create({"reference_id": reference.id, "name": "   ", "credits": 5.0})

    def test_officer_can_read_but_not_manage_reference_facts(self):
        reference = self.env["facodi.learning.curriculum.reference"].with_user(self.manager).create(self._reference_values())
        reference.with_user(self.officer).read(["programme_name"])
        with self.assertRaises(AccessError):
            reference.with_user(self.officer).write({"selection_enabled": False})

    def test_public_and_portal_cannot_read_curriculum_models(self):
        for user in (self.public, self.portal):
            with self.assertRaises(AccessError):
                self.env["facodi.learning.curriculum.reference"].with_user(user).search([])
            with self.assertRaises(AccessError):
                self.env["facodi.learning.curriculum.unit"].with_user(user).search([])
