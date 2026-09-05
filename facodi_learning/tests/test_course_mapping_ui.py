from odoo.tests.common import TransactionCase


class TestCourseMappingUI(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = cls.env["slide.channel"].create({"name": "Source course"})
        cls.target = cls.env["slide.channel"].create({"name": "Related course"})

    def test_course_mapping_backend_views_and_actions_are_loaded(self):
        action = self.env.ref("facodi_learning.action_facodi_course_mappings")
        self.assertEqual(action.res_model, "facodi.learning.course.mapping")
        self.assertEqual(action.name, "Course Mappings")
        self.env.ref("facodi_learning.view_facodi_course_mapping_search")
        self.env.ref("facodi_learning.view_facodi_course_mapping_list")
        self.env.ref("facodi_learning.view_facodi_course_mapping_form")
        self.env.ref("facodi_learning.slide_channel_view_form_facodi_mapping")

    def test_content_and_course_mapping_menus_are_distinct(self):
        content_menu = self.env.ref("facodi_learning.menu_facodi_learning_mappings")
        course_menu = self.env.ref("facodi_learning.menu_facodi_course_mappings")
        self.assertEqual(content_menu.name, "Content Mappings")
        self.assertEqual(course_menu.name, "Course Mappings")
        self.assertNotEqual(content_menu.parent_id, course_menu.parent_id)

    def test_course_can_open_its_mapping_workspace(self):
        action = self.source.action_facodi_view_course_mappings()
        self.assertEqual(action["res_model"], "facodi.learning.course.mapping")
        self.assertEqual(action["context"]["default_source_channel_id"], self.source.id)
        self.assertIn(self.source.id, action["domain"][1])
        self.assertIn(self.source.id, action["domain"][2])

    def test_generate_action_returns_mapping_workspace(self):
        action = self.source.action_facodi_generate_course_mappings_ui()
        self.assertEqual(action["res_model"], "facodi.learning.course.mapping")
        self.assertEqual(action["context"]["default_source_channel_id"], self.source.id)

    def test_related_course_website_template_is_loaded(self):
        view = self.env.ref("facodi_learning.approved_course_relations")
        self.assertEqual(view.type, "qweb")
        self.assertIn("_facodi_related_channels", view.arch_db)
