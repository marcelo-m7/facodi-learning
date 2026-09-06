from odoo import Command
from odoo.tests import TransactionCase


class TestCurriculumUI(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Curriculum UI Manager",
                "login": "curriculum-ui-manager",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id,
                        ]
                    )
                ],
            }
        )
        cls.course = cls.env["slide.channel"].create(
            {"name": "Curriculum Workspace Course", "user_id": cls.manager.id}
        )

    def test_curriculum_backend_actions_and_views_are_loaded(self):
        for xml_id in (
            "facodi_learning.action_facodi_curriculum_references",
            "facodi_learning.action_facodi_curriculum_units",
            "facodi_learning.action_facodi_curriculum_coverage",
            "facodi_learning.view_facodi_curriculum_reference_list",
            "facodi_learning.view_facodi_curriculum_reference_form",
            "facodi_learning.view_facodi_curriculum_unit_list",
            "facodi_learning.view_facodi_curriculum_unit_form",
            "facodi_learning.view_facodi_curriculum_coverage_list",
            "facodi_learning.view_facodi_curriculum_coverage_form",
        ):
            self.assertTrue(self.env.ref(xml_id, raise_if_not_found=False), xml_id)

    def test_curriculum_menu_hierarchy_is_distinct_from_course_mapping(self):
        root = self.env.ref("facodi_learning.menu_facodi_learning_root")
        curriculum = self.env.ref(
            "facodi_learning.menu_facodi_learning_curriculum_coverage"
        )
        course_mapping = self.env.ref(
            "facodi_learning.menu_facodi_learning_course_mapping"
        )
        self.assertEqual(curriculum.parent_id, root)
        self.assertEqual(course_mapping.parent_id, root)
        self.assertNotEqual(curriculum, course_mapping)
        for xml_id in (
            "facodi_learning.menu_facodi_curriculum_references",
            "facodi_learning.menu_facodi_curriculum_units",
            "facodi_learning.menu_facodi_curriculum_coverage",
        ):
            self.assertEqual(self.env.ref(xml_id).parent_id, curriculum)

    def test_reference_form_exposes_units_without_parallel_course_editor(self):
        view = self.env.ref("facodi_learning.view_facodi_curriculum_reference_form")
        arch = view.arch_db
        self.assertIn('name="unit_ids"', arch)
        self.assertNotIn('name="channel_ids"', arch)
        self.assertNotIn('name="slide_ids"', arch)
        self.assertNotIn('model="slide.channel"', arch)

    def test_coverage_form_has_manager_review_buttons(self):
        view = self.env.ref("facodi_learning.view_facodi_curriculum_coverage_form")
        arch = view.arch_db
        self.assertIn('name="action_approve"', arch)
        self.assertIn('name="action_reject"', arch)
        self.assertIn("website_slides.group_website_slides_manager", arch)
        self.assertIn("does not grant", arch.lower())

    def test_course_can_open_curriculum_coverage_workspace(self):
        course = self.course.with_user(self.manager)
        self.assertTrue(hasattr(course, "action_facodi_view_curriculum_coverage"))
        action = course.action_facodi_view_curriculum_coverage()
        self.assertEqual(
            action["res_model"], "facodi.learning.curriculum.coverage"
        )
        self.assertEqual(action["domain"], [("channel_id", "=", self.course.id)])
        self.assertEqual(
            action["context"]["default_channel_id"], self.course.id
        )

    def test_no_public_curriculum_qweb_route_is_added(self):
        qweb_views = self.env["ir.ui.view"].search(
            [
                ("type", "=", "qweb"),
                "|",
                ("key", "ilike", "facodi_learning%curriculum%"),
                ("name", "ilike", "FACODI%Curriculum%"),
            ]
        )
        self.assertFalse(qweb_views)
