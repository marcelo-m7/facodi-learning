from odoo import Command
from odoo.tests import TransactionCase


class TestCurriculumReleaseInvariants(TransactionCase):
    def test_release_bootstraps_only_validated_lesti_reference(self):
        Reference = self.env["facodi.learning.curriculum.reference"]
        Unit = self.env["facodi.learning.curriculum.unit"]
        Coverage = self.env["facodi.learning.curriculum.coverage"]

        references = Reference.search([])
        self.assertEqual(len(references), 1)
        reference = references
        self.assertEqual(reference.provider, "ualg")
        self.assertEqual(reference.external_id, "ualg-1941-2026-27")
        self.assertEqual(reference.external_programme_code, "1941")
        self.assertEqual(reference.academic_year, "2026/27")
        self.assertTrue(reference.validated_at)
        self.assertTrue(reference.website_published)

        units = Unit.search([("reference_id", "=", reference.id)])
        self.assertEqual(len(units), 43)
        self.assertEqual(len(set(units.mapped("external_unit_code"))), 43)
        self.assertFalse(Coverage.search([]))

    def test_empty_curriculum_analysis_does_not_mutate_standard_course_graph(self):
        prerequisite = self.env["slide.channel"].create({"name": "Existing Prerequisite"})
        course = self.env["slide.channel"].create(
            {
                "name": "Existing Canonical Course",
                "prerequisite_channel_ids": [Command.link(prerequisite.id)],
            }
        )
        reference = self.env["facodi.learning.curriculum.reference"].create(
            {
                "institution": "External Institution",
                "programme_name": "External Programme",
                "academic_year": "2026/27",
                "provider": "manual",
                "external_id": "release-invariant-reference",
            }
        )
        unit = self.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": reference.id,
                "external_unit_code": "EXT-001",
                "name": "External Unit",
                "credits": 5.0,
                "curricular_year": 1,
                "period": "semester_1",
                "classification": "mandatory",
            }
        )

        before_prerequisites = course.prerequisite_channel_ids.ids
        before_write_date = course.write_date

        summary = reference._facodi_coverage_summary()
        unit_summary = unit._facodi_coverage_summary()
        course.action_facodi_view_curriculum_coverage()

        course.invalidate_recordset()
        self.assertEqual(course.prerequisite_channel_ids.ids, before_prerequisites)
        self.assertEqual(course.write_date, before_write_date)
        self.assertEqual(summary["gap_count"], 1)
        self.assertEqual(unit_summary["status"], "gap")
        self.assertFalse(
            self.env["facodi.learning.curriculum.coverage"].search(
                [("channel_id", "=", course.id)]
            )
        )
