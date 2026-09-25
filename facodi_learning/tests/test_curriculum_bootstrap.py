from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from ..services.curriculum_bootstrap import ensure_lesti_2026_27


class TestCurriculumBootstrap(TransactionCase):
    def test_lesti_bootstrap_is_idempotent_and_public(self):
        reference = ensure_lesti_2026_27(self.env)
        again = ensure_lesti_2026_27(self.env)

        self.assertEqual(reference, again)
        self.assertEqual(reference.provider, "ualg")
        self.assertEqual(reference.external_id, "ualg-1941-2026-27")
        self.assertEqual(reference.external_programme_code, "1941")
        self.assertEqual(reference.academic_year, "2026/27")
        self.assertTrue(reference.validated_at)
        self.assertTrue(reference.website_published)
        self.assertEqual(len(reference.unit_ids), 43)
        self.assertEqual(
            reference.unit_ids.filtered(
                lambda unit: unit.external_unit_code == "19411035"
            ).credits,
            30.0,
        )

    def test_lesti_bootstrap_rejects_identity_mismatch(self):
        reference = ensure_lesti_2026_27(self.env)
        original_institution = reference.institution

        from ..services import curriculum_bootstrap as bootstrap

        payload = bootstrap._load_fixture()
        payload["reference"] = dict(payload["reference"])
        payload["reference"]["institution"] = "Conflicting Institution"

        with patch.object(bootstrap, "_load_fixture", return_value=payload):
            with self.assertRaisesRegex(
                ValidationError,
                "does not match the existing curriculum reference",
            ):
                ensure_lesti_2026_27(self.env)

        reference.invalidate_recordset()
        self.assertEqual(reference.institution, original_institution)
        self.assertTrue(reference.website_published)
        self.assertEqual(len(reference.unit_ids), 43)

    def test_public_curriculum_links_require_reviewed_coverage(self):
        reference = ensure_lesti_2026_27(self.env)
        unit = reference.unit_ids.filtered(
            lambda item: item.external_unit_code == "19411017"
        )
        course = self.env["slide.channel"].create(
            {
                "name": "FACODI — Bases de Dados II",
                "is_published": True,
            }
        )
        coverage = self.env["facodi.learning.curriculum.coverage"].create(
            {
                "channel_id": course.id,
                "curriculum_unit_id": unit.id,
                "coverage_type": "covers",
                "confidence": 1.0,
            }
        )

        self.assertFalse(course._facodi_public_curriculum_links())
        coverage.action_approve()
        links = course._facodi_public_curriculum_links()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["unit_code"], "19411017")
        self.assertEqual(links[0]["reference_id"], reference.id)
        self.assertEqual(links[0]["coverage_label"], "Curriculum coverage")

    def test_unpublished_reference_is_not_exposed_by_course_link(self):
        reference = ensure_lesti_2026_27(self.env)
        reference.action_archive()
        unit = reference.unit_ids.filtered(
            lambda item: item.external_unit_code == "19411017"
        )
        course = self.env["slide.channel"].create(
            {
                "name": "FACODI — Database Practice",
                "is_published": True,
            }
        )
        coverage = self.env["facodi.learning.curriculum.coverage"].create(
            {
                "channel_id": course.id,
                "curriculum_unit_id": unit.id,
                "coverage_type": "supports",
                "confidence": 0.9,
            }
        )
        coverage.action_approve()
        self.assertFalse(course._facodi_public_curriculum_links())
