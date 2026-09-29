from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from ..services.curriculum_bootstrap import ensure_design_curricula_2026_27, ensure_lesti_2026_27


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


    def test_design_curricula_bootstrap_is_idempotent_and_public(self):
        first = ensure_design_curricula_2026_27(self.env)
        second = ensure_design_curricula_2026_27(self.env)

        self.assertEqual(first["1930"], second["1930"])
        self.assertEqual(first["1454"], second["1454"])
        self.assertTrue(first["1930"].website_published)
        self.assertTrue(first["1454"].website_published)
        self.assertEqual(len(first["1930"].unit_ids), 19)
        self.assertEqual(len(first["1454"].unit_ids), 41)

        typography = first["1930"].unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19301007"
        )
        web_design = first["1930"].unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19301009"
        )
        self.assertEqual(typography.credits, 5.0)
        self.assertEqual(web_design.credits, 4.0)

        design_foundations_channel = self.env.ref(
            "__import__.facodi_dtm_19301001_design_foundations"
        )
        interaction_channel = self.env.ref(
            "__import__.facodi_dtm_19301006_interaction_design"
        )
        motion_channel = self.env.ref(
            "__import__.facodi_dtm_19301008_motion_design"
        )
        web_channel = self.env.ref(
            "__import__.facodi_dtm_19301009_web_design"
        )
        self.assertTrue(design_foundations_channel.is_published)
        self.assertTrue(interaction_channel.is_published)
        self.assertTrue(motion_channel.is_published)
        self.assertTrue(web_channel.is_published)
        self.assertEqual(len(interaction_channel.slide_ids), 2)
        self.assertIn("User Experience", interaction_channel.slide_ids.tag_ids.mapped("name"))
        self.assertIn("Figma", interaction_channel.slide_ids.tag_ids.mapped("name"))
        self.assertIn("Motion Design", motion_channel.slide_ids.tag_ids.mapped("name"))
        self.assertIn("Web Design", web_channel.slide_ids.tag_ids.mapped("name"))
        self.assertIn(
            "Design Principles",
            design_foundations_channel.slide_ids.tag_ids.mapped("name"),
        )

        typography_channel = self.env.ref(
            "__import__.facodi_ldcom_14541153"
        )
        art_history_channel = self.env.ref(
            "__import__.facodi_ldcom_14541196"
        )
        self.assertTrue(typography_channel.is_published)
        self.assertTrue(art_history_channel.is_published)
        self.assertEqual(len(typography_channel.slide_ids), 20)
        self.assertEqual(len(art_history_channel.slide_ids), 22)
        self.assertFalse(
            typography_channel.slide_ids.filtered(
                lambda slide: "2AnSbALxoD8" in (slide.url or "")
            )
        )
        self.assertFalse(
            art_history_channel.slide_ids.filtered(
                lambda slide: any(
                    youtube_id in (slide.url or "")
                    for youtube_id in ("lAAfjtnc7bI", "m62ZGavdj-8")
                )
            )
        )

        typography_dtm = first["1930"].unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19301007"
        )
        typography_ldcom = first["1454"].unit_ids.filtered(
            lambda unit: unit.external_unit_code == "14541153"
        )
        art_history_ldcom = first["1454"].unit_ids.filtered(
            lambda unit: unit.external_unit_code == "14541196"
        )
        for channel, unit in (
            (typography_channel, typography_dtm),
            (typography_channel, typography_ldcom),
            (art_history_channel, art_history_ldcom),
        ):
            self.assertTrue(
                self.env["facodi.learning.curriculum.coverage"].search(
                    [
                        ("channel_id", "=", channel.id),
                        ("curriculum_unit_id", "=", unit.id),
                        ("coverage_type", "=", "supports"),
                        ("state", "=", "approved"),
                    ],
                    limit=1,
                )
            )

        editor_tag = self.env["slide.tag"].create({"name": "Editor-curated DTM tag"})
        interaction_channel.slide_ids[:1].write({"tag_ids": [(4, editor_tag.id)]})
        ensure_design_curricula_2026_27(self.env)
        self.assertIn(
            "Editor-curated DTM tag",
            interaction_channel.slide_ids[:1].tag_ids.mapped("name"),
        )

        self.assertTrue(
            self.env["facodi.learning.curriculum.coverage"].search(
                [
                    ("channel_id", "=", design_foundations_channel.id),
                    ("curriculum_unit_id", "=", first["1930"].unit_ids.filtered(
                        lambda unit: unit.external_unit_code == "19301001"
                    ).id),
                    ("state", "=", "approved"),
                ],
                limit=1,
            )
        )
        self.assertTrue(
            self.env["facodi.learning.curriculum.coverage"].search(
                [
                    ("channel_id", "=", interaction_channel.id),
                    ("curriculum_unit_id", "=", first["1930"].unit_ids.filtered(
                        lambda unit: unit.external_unit_code == "19301006"
                    ).id),
                    ("state", "=", "approved"),
                ],
                limit=1,
            )
        )
        self.assertTrue(
            self.env["facodi.learning.curriculum.coverage"].search(
                [
                    ("channel_id", "=", motion_channel.id),
                    ("curriculum_unit_id", "=", first["1930"].unit_ids.filtered(
                        lambda unit: unit.external_unit_code == "19301008"
                    ).id),
                    ("state", "=", "approved"),
                ],
                limit=1,
            )
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
