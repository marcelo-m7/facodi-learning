from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]


class TestEditorialSubmissionDeskContract(unittest.TestCase):
    def test_review_desk_exposes_unified_submission_context(self):
        source = (MODULE_ROOT / "views" / "submission_views.xml").read_text(encoding="utf-8")
        self.assertIn('string="FACODI Submissions"', source)
        self.assertIn('name="Review Desk"', source)
        self.assertIn('name="needs_attention"', source)
        self.assertIn('name="submission_type"', source)
        self.assertIn('name="contact_topic"', source)
        self.assertIn('name="source_cta"', source)
        self.assertIn('name="source_section"', source)
        self.assertIn('name="curriculum_unit_id"', source)
        self.assertIn('name="module_id"', source)
        self.assertIn('name="course_id"', source)
        self.assertIn('name="suggested_slide_id"', source)

    def test_review_desk_no_longer_presents_unified_queue_as_resource_only(self):
        source = (MODULE_ROOT / "views" / "submission_views.xml").read_text(encoding="utf-8")
        self.assertNotIn('string="Resource Submissions"', source)
        self.assertNotIn('<field name="name">Resource Submissions</field>', source)


if __name__ == "__main__":
    unittest.main()
