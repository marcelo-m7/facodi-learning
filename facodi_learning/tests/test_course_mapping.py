from odoo.tests import TransactionCase


class TestCourseMapping(TransactionCase):
    def test_course_mapping_model_exists(self):
        self.assertIn("facodi.learning.course.mapping", self.env.registry.models)
