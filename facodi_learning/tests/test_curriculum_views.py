from odoo.tests import TransactionCase


class TestCurriculumViews(TransactionCase):
    def test_curriculum_workspace_views_actions_and_menus_are_loaded(self):
        expected = {
            "facodi_learning.view_facodi_curriculum_reference_search": "ir.ui.view",
            "facodi_learning.view_facodi_curriculum_reference_list": "ir.ui.view",
            "facodi_learning.view_facodi_curriculum_reference_form": "ir.ui.view",
            "facodi_learning.action_facodi_curriculum_references": "ir.actions.act_window",
            "facodi_learning.view_facodi_curriculum_unit_search": "ir.ui.view",
            "facodi_learning.view_facodi_curriculum_unit_list": "ir.ui.view",
            "facodi_learning.view_facodi_curriculum_unit_form": "ir.ui.view",
            "facodi_learning.action_facodi_curriculum_units": "ir.actions.act_window",
            "facodi_learning.view_facodi_curriculum_coverage_search": "ir.ui.view",
            "facodi_learning.view_facodi_curriculum_coverage_list": "ir.ui.view",
            "facodi_learning.view_facodi_curriculum_coverage_form": "ir.ui.view",
            "facodi_learning.action_facodi_curriculum_coverage": "ir.actions.act_window",
            "facodi_learning.menu_facodi_learning_curriculum": "ir.ui.menu",
            "facodi_learning.menu_facodi_curriculum_references": "ir.ui.menu",
            "facodi_learning.menu_facodi_curriculum_units": "ir.ui.menu",
            "facodi_learning.menu_facodi_curriculum_coverage": "ir.ui.menu",
        }
        for xmlid, model_name in expected.items():
            record = self.env.ref(xmlid, raise_if_not_found=False)
            self.assertTrue(record, xmlid)
            self.assertEqual(record._name, model_name, xmlid)

    def test_curriculum_actions_target_the_expected_models(self):
        self.assertEqual(
            self.env.ref("facodi_learning.action_facodi_curriculum_references").res_model,
            "facodi.learning.curriculum.reference",
        )
        self.assertEqual(
            self.env.ref("facodi_learning.action_facodi_curriculum_units").res_model,
            "facodi.learning.curriculum.unit",
        )
        self.assertEqual(
            self.env.ref("facodi_learning.action_facodi_curriculum_coverage").res_model,
            "facodi.learning.curriculum.coverage",
        )

    def test_candidate_form_exposes_readonly_curriculum_evidence(self):
        arch = self.env.ref("facodi_learning.view_facodi_course_candidate_form").arch_db
        self.assertIn('name="coverage_evidence"', arch)
        self.assertIn('readonly="1"', arch)
