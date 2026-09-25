from odoo.tests import TransactionCase

from ..services.curriculum_bootstrap import ensure_lesti_2026_27


class TestCurriculumPublicUnits(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reference = ensure_lesti_2026_27(cls.env)
        cls.database_unit = cls.reference.unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19411017"
        )
        cls.programming_unit = cls.reference.unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19411000"
        )

    def _course(self, name, *, published=True):
        return self.env["slide.channel"].create(
            {
                "name": name,
                "is_published": published,
            }
        )

    def _approved_coverage(self, course, unit, coverage_type):
        coverage = self.env["facodi.learning.curriculum.coverage"].create(
            {
                "channel_id": course.id,
                "curriculum_unit_id": unit.id,
                "coverage_type": coverage_type,
                "confidence": 1.0,
            }
        )
        coverage.action_approve()
        return coverage

    def test_public_unit_path_requires_public_validated_reference(self):
        path = self.database_unit._facodi_public_path()
        self.assertEqual(
            path,
            f"/roadmaps/{self.reference.id}/units/19411017",
        )

        self.reference.action_archive()
        self.assertFalse(self.database_unit._facodi_public_path())

    def test_public_unit_coverage_exposes_only_approved_published_courses(self):
        published = self._course("Published Database Course")
        unpublished = self._course("Draft Database Course", published=False)
        proposed = self._course("Proposed Database Course")

        self._approved_coverage(published, self.database_unit, "covers")
        self._approved_coverage(unpublished, self.database_unit, "covers")
        self.env["facodi.learning.curriculum.coverage"].create(
            {
                "channel_id": proposed.id,
                "curriculum_unit_id": self.database_unit.id,
                "coverage_type": "covers",
                "confidence": 0.9,
            }
        )

        rows = self.database_unit._facodi_public_coverage_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["channel"], published)
        self.assertEqual(rows[0]["coverage_type"], "covers")
        self.assertEqual(rows[0]["coverage_status"], "covered")

    def test_public_reference_matrix_uses_strongest_published_coverage(self):
        supporting = self._course("Programming Support")
        covering = self._course("Programming Complete")
        self._approved_coverage(supporting, self.programming_unit, "supports")
        self._approved_coverage(covering, self.programming_unit, "covers")

        matrix = self.reference._facodi_public_unit_matrix()
        row = next(
            entry
            for entry in matrix
            if entry["unit"].external_unit_code == "19411000"
        )
        self.assertEqual(row["coverage_status"], "covered")
        self.assertEqual(row["published_course_count"], 2)
        self.assertEqual(
            row["unit_url"],
            f"/roadmaps/{self.reference.id}/units/19411000",
        )

        gap = next(
            entry
            for entry in matrix
            if entry["unit"].external_unit_code == "19411017"
        )
        self.assertEqual(gap["coverage_status"], "gap")
        self.assertEqual(gap["published_course_count"], 0)

    def test_supports_only_is_publicly_partial_not_covered(self):
        course = self._course("Database Foundations")
        self._approved_coverage(course, self.database_unit, "supports")

        row = next(
            entry
            for entry in self.reference._facodi_public_unit_matrix()
            if entry["unit"].external_unit_code == "19411017"
        )
        self.assertEqual(row["coverage_status"], "partial")
        self.assertEqual(row["published_course_count"], 1)

    def test_public_catalog_filters_only_validated_published_units(self):
        course = self._course("Programming Foundations")
        self._approved_coverage(course, self.programming_unit, "covers")
        hidden_reference = self.env["facodi.learning.curriculum.reference"].create(
            {
                "institution": "Private Institution",
                "programme_name": "Private Programme",
                "academic_year": "2026/27",
                "provider": "manual",
                "external_id": "private-catalog-reference",
            }
        )
        self.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": hidden_reference.id,
                "external_unit_code": "PRIVATE-001",
                "name": "Private Unit",
                "credits": 5.0,
                "curricular_year": 1,
                "period": "semester_1",
                "classification": "mandatory",
            }
        )

        all_entries = self.env[
            "facodi.learning.curriculum.unit"
        ]._facodi_public_catalog_entries()
        self.assertEqual(len(all_entries), len(self.reference.unit_ids))

        entries = self.env["facodi.learning.curriculum.unit"]._facodi_public_catalog_entries(
            reference_id=self.reference.id,
            curricular_year=1,
            period="semester_1",
            credits=5.0,
        )
        programming = next(
            entry
            for entry in entries
            if entry["unit"].external_unit_code == "19411000"
        )
        self.assertEqual(programming["coverage_status"], "covered")
        self.assertEqual(programming["published_course_count"], 1)
        self.assertEqual(
            programming["unit_url"],
            f"/unidades-curriculares/{self.reference.id}/19411000-programacao",
        )
        self.assertNotIn(
            "PRIVATE-001",
            {entry["unit"].external_unit_code for entry in entries},
        )

    def test_public_curriculum_map_exposes_only_published_references(self):
        course = self._course("Public Curriculum Map Course")
        self._approved_coverage(course, self.programming_unit, "covers")
        hidden_reference = self.env["facodi.learning.curriculum.reference"].create(
            {
                "institution": "Private Institution",
                "programme_name": "Hidden Programme",
                "academic_year": "2026/27",
                "provider": "manual",
                "external_id": "hidden-map-reference",
            }
        )

        entries = self.env[
            "facodi.learning.curriculum.reference"
        ]._facodi_public_curriculum_map()

        self.assertEqual([entry["reference"] for entry in entries], self.reference)
        self.assertNotIn(hidden_reference, [entry["reference"] for entry in entries])
        self.assertEqual(entries[0]["reference_url"], f"/roadmaps/{self.reference.id}")
        programming = next(
            entry
            for entry in entries[0]["unit_matrix"]
            if entry["unit"] == self.programming_unit
        )
        self.assertEqual(programming["coverage_status"], "covered")
        self.assertEqual(programming["coverage_rows"][0]["coverage_type"], "covers")


    def test_unit_detail_omits_missing_optional_metadata(self):
        view = self.env.ref("facodi_learning.curriculum_public_unit")
        self.assertIn('t-if="unit.credits"', view.arch_db)
        self.assertIn('t-if="unit.option_group"', view.arch_db)
        self.assertIn('t-if="unit.classification"', view.arch_db)
        self.assertNotIn("My Notebook", view.arch_db)
        self.assertNotIn("Class Questions", view.arch_db)
        self.assertNotIn("Open Bibliography", view.arch_db)

    def test_gap_state_offers_contextual_resource_submission(self):
        view = self.env.ref("facodi_learning.curriculum_public_unit")
        self.assertIn("curriculum_unit_id", view.arch_db)
        self.assertIn("Suggest a resource", view.arch_db)
        self.assertIn("There is no published course with reviewed coverage", view.arch_db)

    def test_unit_qweb_view_is_loaded_and_links_back_to_official_source(self):
        view = self.env.ref("facodi_learning.curriculum_public_unit")
        self.assertEqual(view.type, "qweb")
        self.assertIn("website.layout", view.arch_db)
        self.assertIn("source_url", view.arch_db)
        self.assertIn("coverage_rows", view.arch_db)
        self.assertIn("learning['modules']", view.arch_db)
        self.assertIn("learning['next_item']", view.arch_db)
        self.assertIn("/roadmaps", view.arch_db)
        self.assertNotIn("facodi.learning.curriculum.coverage", view.arch_db)
