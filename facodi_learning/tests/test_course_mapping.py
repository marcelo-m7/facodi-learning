from odoo.tests import TransactionCase


class TestCourseMapping(TransactionCase):
    def test_course_mapping_model_exists(self):
        self.assertIn("facodi.learning.course.mapping", self.env.registry.models)

    def test_course_mapping_has_audit_schema(self):
        Mapping = self.env["facodi.learning.course.mapping"]
        expected_fields = {
            "source_channel_id",
            "target_channel_id",
            "mapping_type",
            "confidence",
            "origin",
            "state",
            "evidence",
            "ranking_version",
            "reviewed_by_id",
            "reviewed_at",
            "policy_version",
            "decision_snapshot",
            "native_applied_by_id",
            "native_applied_at",
        }
        self.assertTrue(expected_fields <= set(Mapping._fields))
