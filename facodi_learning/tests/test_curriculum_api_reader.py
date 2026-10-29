from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase


class TestCurriculumApiReader(TransactionCase):
    """Enforce connector isolation at the ORM boundary, not only in Edge code."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader_group = cls.env.ref(
            "facodi_learning.group_facodi_curriculum_api_reader"
        )
        cls.reader = cls.env["res.users"].create(
            {
                "name": "Curriculum API Reader Fixture",
                "login": "curriculum-api-reader-fixture",
                "group_ids": [
                    Command.set([
                        cls.env.ref("base.group_user").id,
                        cls.reader_group.id,
                    ])
                ],
            }
        )
        cls.reference = cls.env["facodi.learning.curriculum.reference"].create(
            {
                "institution": "Test University",
                "programme_name": "Demo programme",
                "academic_year": "2026/27",
                "provider": "manual",
                "external_id": "api-reader-published-reference",
                "website_published": True,
                "validated_at": fields.Datetime.now(),
            }
        )
        cls.private_reference = cls.env[
            "facodi.learning.curriculum.reference"
        ].create(
            {
                "institution": "Test University",
                "programme_name": "Private programme",
                "academic_year": "2026/27",
                "provider": "manual",
                "external_id": "api-reader-private-reference",
                "website_published": False,
            }
        )
        Unit = cls.env["facodi.learning.curriculum.unit"]
        cls.unit = Unit.create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "reader-unit-1",
                "name": "Data analysis",
            }
        )
        cls.private_unit = Unit.create(
            {
                "reference_id": cls.private_reference.id,
                "external_unit_code": "reader-unit-private",
                "name": "Private project",
            }
        )
        cls.course = cls.env["slide.channel"].create(
            {"name": "Published analysis", "is_published": True,
             "website_published": True}
        )
        cls.private_course = cls.env["slide.channel"].create(
            {"name": "Private content", "is_published": False,
             "website_published": False}
        )
        Coverage = cls.env["facodi.learning.curriculum.coverage"]
        cls.approved = Coverage.create({
            "channel_id": cls.course.id,
            "curriculum_unit_id": cls.unit.id,
            "coverage_type": "supports",
            "confidence": 0.8,
        })
        cls.approved.action_approve()
        cls.proposed = Coverage.create({
            "channel_id": cls.private_course.id,
            "curriculum_unit_id": cls.unit.id,
            "coverage_type": "supports",
            "confidence": 0.6,
        })

    def test_role_has_no_elearning_editor_or_administrator_group(self):
        self.assertTrue(self.reader.has_group(
            "facodi_learning.group_facodi_curriculum_api_reader"
        ))
        for group in (
            "website_slides.group_website_slides_officer",
            "website_slides.group_website_slides_manager",
            "base.group_system",
        ):
            self.assertFalse(self.reader.has_group(group))

    def test_read_only_access_granted_to_four_models(self):
        for model_name in (
            "facodi.learning.curriculum.reference",
            "facodi.learning.curriculum.unit",
            "facodi.learning.curriculum.coverage",
            "slide.channel",
        ):
            model = self.env[model_name].with_user(self.reader)
            model.check_access("read")
            for operation in ("write", "create", "unlink"):
                with self.assertRaises(AccessError, msg=f"{model_name}: {operation}"):
                    model.check_access(operation)

    def test_only_approved_public_curriculum_is_visible(self):
        references = self.env[
            "facodi.learning.curriculum.reference"
        ].with_user(self.reader)
        units = self.env["facodi.learning.curriculum.unit"].with_user(self.reader)
        coverages = self.env[
            "facodi.learning.curriculum.coverage"
        ].with_user(self.reader)
        courses = self.env["slide.channel"].with_user(self.reader)

        self.assertIn(self.reference, references.search([
            ("id", "=", self.reference.id),
        ]))
        self.assertFalse(references.search([("id", "=", self.private_reference.id)]))
        self.assertIn(self.unit, units.search([("id", "=", self.unit.id)]))
        self.assertFalse(units.search([("id", "=", self.private_unit.id)]))
        self.assertIn(self.approved, coverages.search([("id", "=", self.approved.id)]))
        self.assertFalse(coverages.search([("id", "=", self.proposed.id)]))
        self.assertIn(self.course, courses.search([("id", "=", self.course.id)]))
        self.assertFalse(courses.search([("id", "=", self.private_course.id)]))

    def test_connector_cannot_generate_or_approve_proposals(self):
        with self.assertRaises(AccessError):
            self.unit.with_user(
                self.reader
            ).action_generate_coverage_proposals()
        with self.assertRaises(AccessError):
            self.approved.with_user(self.reader).action_approve()
