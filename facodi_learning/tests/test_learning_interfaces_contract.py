from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = MODULE_ROOT / "views" / "website_curriculum.xml"
SLIDES = MODULE_ROOT / "views" / "website_slides.xml"
WEBSITE_MENU = MODULE_ROOT / "data" / "website_menu.xml"
PORTAL_HOME = MODULE_ROOT / "views" / "portal_home.xml"
MANIFEST = MODULE_ROOT / "__manifest__.py"
SLIDE_CHANNEL_MODEL = MODULE_ROOT / "models" / "slide_channel.py"
CURRICULUM_CONTROLLER = MODULE_ROOT / "controllers" / "curriculum.py"


class TestLearningInterfacesContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.curriculum = CURRICULUM.read_text(encoding="utf-8")
        cls.slides = SLIDES.read_text(encoding="utf-8")

    def test_d1_release_version(self):
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn('"version": "19.0.1.40.0"', manifest)

    def test_portal_progress_avoids_old_style_percent_formatting(self):
        portal_home = PORTAL_HOME.read_text(encoding="utf-8")
        self.assertNotIn("width: %.0f%%", portal_home)
        self.assertNotIn("t-att-aria-valuenow=\"'%.0f' %", portal_home)
        self.assertIn('t-attf-style="width: #{row[\'completion\']}%"', portal_home)
        self.assertIn('t-att-aria-valuenow="round(row[\'completion\'])"', portal_home)

    def test_explore_menu_groups_discovery_routes_under_one_parent(self):
        menu = WEBSITE_MENU.read_text(encoding="utf-8")
        for menu_id, route in (
            ("menu_public_explore_courses", "/slides"),
            ("menu_public_explore_areas", "/explorar/areas"),
            ("menu_public_explore_contents", "/explorar/conteudos"),
            ("menu_public_explore_videos", "/explorar/videos"),
            ("menu_public_curriculum_map", "/roadmaps"),
            ("menu_public_curricular_units", "/unidades-curriculares"),
        ):
            self.assertIn(f'id="{menu_id}"', menu)
            self.assertIn(f"<field name=\"url\">{route}</field>", menu)

        self.assertGreaterEqual(
            menu.count('<field name="parent_id" ref="facodi_learning.menu_public_explore"/>'),
            6,
        )

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

    def test_detail_views_expose_d1_semantic_structure(self):
        for hook in (
            "facodi-roadmap-study-path",
            "facodi-unit-layout",
            "facodi-unit-main",
            "facodi-reference-rail",
            "facodi-module-stack",
            "facodi-module-detail",
            "facodi-open-callout",
        ):
            self.assertIn(hook, self.curriculum)

        self.assertIn("unit_matrix_groups", self.curriculum)
        self.assertIn("learning['modules']", self.curriculum)
        self.assertIn("learning['next_item']", self.curriculum)

    def test_course_alignment_and_contribution_expose_d1_hooks(self):
        self.assertIn("facodi-course-alignment-sheet", self.curriculum)
        self.assertIn("facodi-open-callout", self.slides)
        self.assertIn("/contribuir/recurso", self.slides)

        model_source = SLIDE_CHANNEL_MODEL.read_text(encoding="utf-8")
        self.assertIn(
            "Content correspondence - not academic equivalence",
            model_source,
        )

    def test_curriculum_forum_link_uses_odoo19_slug_route(self):
        controller = CURRICULUM_CONTROLLER.read_text(encoding="utf-8")
        self.assertIn('request.env["ir.http"]._slug(forum)', controller)
        self.assertNotIn("forum.website_url", controller)

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
