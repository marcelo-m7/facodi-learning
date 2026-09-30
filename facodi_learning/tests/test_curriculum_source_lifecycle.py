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
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Curriculum Lifecycle Officer",
                "login": "curriculum-lifecycle-officer",
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
        self.assertEqual(manager_reference.validated_by_id, self.manager)
        self.assertTrue(manager_reference.validated_at)

        manager_reference.action_publish()
        self.assertTrue(manager_reference.website_published)
        self.assertTrue(manager_reference.is_published)
        self.assertEqual(manager_reference.published_by_id, self.manager)
        self.assertTrue(manager_reference.published_at)

        manager_reference.action_archive()
        self.assertEqual(manager_reference.state, "archived")
        self.assertFalse(manager_reference.website_published)
        self.assertFalse(manager_reference.is_published)
        self.assertEqual(manager_reference.archived_by_id, self.manager)
        self.assertTrue(manager_reference.archived_at)

    def test_non_manager_cannot_review_curriculum_reference(self):
        for method_name in ("action_validate", "action_publish", "action_archive"):
            reference = self.env["facodi.learning.curriculum.reference"].create(
                {
                    "institution": "Restricted Institution",
                    "programme_name": f"Restricted {method_name}",
                    "academic_year": "2026/27",
                    "provider": "manual",
                    "external_id": f"restricted-{method_name}",
                }
            )
            if method_name == "action_publish":
                reference.with_user(self.manager).action_validate()
            with self.assertRaises(AccessError):
                getattr(reference.with_user(self.officer), method_name)()

    def test_review_audit_fields_cannot_be_forged_by_direct_write(self):
        reference = self.reference.with_user(self.manager)
        for values in (
            {"validated_by_id": self.manager.id},
            {"published_at": "2026-09-30 19:00:00"},
            {"published_by_id": self.manager.id},
            {"archived_at": "2026-09-30 19:00:00"},
            {"archived_by_id": self.manager.id},
        ):
            with self.assertRaises(AccessError):
                reference.write(values)

    def test_reference_form_exposes_manager_review_actions(self):
        view = self.env.ref(
            "facodi_learning.view_facodi_curriculum_reference_form"
        )
        arch = view.arch_db
        for action in ("action_validate", "action_publish", "action_archive"):
            self.assertIn(f'name="{action}"', arch)
        self.assertIn(
            'groups="website_slides.group_website_slides_manager"',
            arch,
        )
        self.assertIn('name="state"', arch)
        self.assertIn('widget="statusbar"', arch)

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