from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = MODULE_ROOT / "views" / "website_curriculum.xml"
SLIDES = MODULE_ROOT / "views" / "website_slides.xml"
MANIFEST = MODULE_ROOT / "__manifest__.py"


class TestLearningInterfacesContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.curriculum = CURRICULUM.read_text(encoding="utf-8")
        cls.slides = SLIDES.read_text(encoding="utf-8")

    def test_roadmap_catalogue_exposes_d1_structure(self):
        self.assertIn('id="curriculum_public_index"', self.curriculum)
        self.assertIn("facodi-learning-hero", self.curriculum)
        self.assertIn("facodi-index-tabs", self.curriculum)
        self.assertIn("facodi-record-card--roadmap", self.curriculum)
        self.assertIn("/roadmaps", self.curriculum)
        self.assertIn("/unidades-curriculares", self.curriculum)

    def test_unit_catalogue_preserves_real_filters_and_d1_structure(self):
        self.assertIn('id="curriculum_public_unit_index"', self.curriculum)
        self.assertIn("facodi-filter-sheet", self.curriculum)
        self.assertIn("facodi-record-card--unit", self.curriculum)
        for field in ("reference_id", "year", "period", "credits"):
            self.assertIn(f'name="{field}"', self.curriculum)
        for value in ("published_course_count", "coverage_status", "unit_url"):
            self.assertIn(value, self.curriculum)

    def test_stitch_only_features_are_not_rendered(self):
        for source in (self.curriculum, self.slides):
            for forbidden in (
                "My Notebook",
                "Class Questions",
                "Open Bibliography",
                "verified answer",
            ):
                self.assertNotIn(forbidden, source)

    def test_no_fabricated_static_learning_statistics(self):
        for source in (self.curriculum, self.slides):
            self.assertNotRegex(source, r">\s*[0-9]{2,}\s+students\s*<")
            self.assertNotRegex(source, r">\s*[0-9]{2,}%\s+complete\s*<")


if __name__ == "__main__":
    unittest.main()
