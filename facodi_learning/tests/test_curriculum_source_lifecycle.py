from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCurriculumSourceLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Curriculum Lifecycle Manager",
                "login": "curriculum-lifecycle-manager",
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
                "institution": "External Institution",
                "programme_name": "External Programme",
                "academic_year": "2026/27",
                "provider": "manual",
                "external_id": "curriculum-lifecycle-reference",
            }
        )

    def test_lifecycle_context_cannot_bypass_review_actions(self):
        manager_reference = self.reference.with_user(self.manager)

        with self.assertRaises(AccessError):
            manager_reference.with_context(facodi_curriculum_review=True).write(
                {"state": "validated", "validated_at": False}
            )

        manager_reference.action_validate()
        self.assertEqual(manager_reference.state, "validated")
        manager_reference.action_publish()
        self.assertTrue(manager_reference.website_published)
        manager_reference.action_archive()
        self.assertEqual(manager_reference.state, "archived")
        self.assertFalse(manager_reference.website_published)

    def test_unexpected_import_error_is_not_persisted_or_exposed(self):
        source = self.env["facodi.learning.curriculum.source"].create(
            {
                "external_id": "curriculum-import-error",
                "institution": "External Institution",
                "programme_name": "External Programme",
                "external_programme_code": "EXTERNAL",
                "academic_year": "2026/27",
                "source_url": "https://www.ualg.pt/curso/external/plano",
                "website_id": self.env["website"].get_current_website().id,
            }
        )

        with patch(
            "odoo.addons.facodi_learning.models.curriculum_source.parse_ualg_course_plan",
            side_effect=RuntimeError("internal connection detail"),
        ), self.assertRaisesRegex(ValidationError, "failed unexpectedly"):
            source._import_raw(b"<html/>")

        capture = source.capture_ids
        self.assertEqual(capture.status, "failed")
        self.assertNotIn("internal connection detail", capture.error)