from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
PORTAL_CONTROLLER = MODULE_ROOT / "controllers" / "portal.py"
PORTAL_VIEW = MODULE_ROOT / "views" / "portal_home.xml"
SUBMISSION_VIEW = MODULE_ROOT / "views" / "website_submission.xml"


class TestPortalHomeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.controller = PORTAL_CONTROLLER.read_text(encoding="utf-8")
        cls.portal = PORTAL_VIEW.read_text(encoding="utf-8")
        cls.submission = SUBMISSION_VIEW.read_text(encoding="utf-8")

    def test_counter_rpc_returns_before_facodi_dashboard_queries(self):
        guard = "if counters:\n            return values"
        self.assertIn(guard, self.controller)
        self.assertLess(
            self.controller.index(guard),
            self.controller.index('request.env["facodi.learning.submission"].sudo()'),
        )

    def test_learning_shelf_uses_standard_membership_model(self):
        self.assertIn('request.env["slide.channel.partner"]', self.controller)
        self.assertIn('("member_status", "!=", "invited")', self.controller)
        self.assertNotIn('("partner_ids", "in"', self.controller)

    def test_learning_shelf_is_website_scoped(self):
        self.assertIn('("channel_id.website_id", "=", request.website.id)', self.controller)
        self.assertIn('("channel_id.website_published", "=", True)', self.controller)
        self.assertIn('("channel_id.visibility", "=", "public")', self.controller)

    def test_portal_exposes_native_progress_without_parallel_tracking(self):
        self.assertIn('"completion": min(max(completion, 0.0), 100.0)', self.controller)
        self.assertIn('"is_completed": membership.member_status == "completed"', self.controller)
        self.assertIn("facodi-course-progress", self.portal)
        self.assertIn("facodi_course_rows", self.portal)

    def test_academic_map_uses_standard_membership_course_ids(self):
        self.assertIn(
            'enrolled_course_ids = set(memberships.mapped("channel_id").ids)',
            self.controller,
        )
        self.assertNotIn("set(enrolled_courses.ids)", self.controller)

    def test_recent_learning_uses_native_completion_records(self):
        self.assertIn('request.env["slide.slide.partner"].sudo()', self.controller)
        self.assertIn('("completed", "=", True)', self.controller)
        self.assertIn('"facodi_recent_learning_rows": recent_learning_rows', self.controller)
        self.assertIn('data-facodi-latest-wins="1"', self.portal)

    def test_portal_t_field_expressions_are_smart_record_fields(self):
        import re

        expressions = re.findall(r't-field="([^"]+)"', self.portal)
        self.assertTrue(expressions)
        invalid = [expression for expression in expressions if "." not in expression]
        self.assertEqual(
            invalid,
            [],
            "t-field is only valid for smart-record expressions like record.field",
        )
        self.assertIn(
            't-out="row[\'completed_at\']"',
            self.portal,
            "computed completion timestamps must use t-out, not t-field",
        )

    def test_minha_facodi_has_single_standard_portal_destination(self):
        self.assertIn('return request.redirect("/my/home", code=301)', self.controller)
        self.assertNotIn('id="my_facodi_dashboard"', self.submission)


if __name__ == "__main__":
    unittest.main()
