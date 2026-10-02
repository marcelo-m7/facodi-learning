import ast
from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = MODULE_ROOT / "views" / "website_curriculum.xml"
SLIDES = MODULE_ROOT / "views" / "website_slides.xml"
WEBSITE_MENU = MODULE_ROOT / "data" / "website_menu.xml"
WEBSITE_MENU_MODEL = MODULE_ROOT / "models" / "website_menu.py"
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
        manifest = ast.literal_eval(MANIFEST.read_text(encoding="utf-8"))
        version = tuple(int(part) for part in manifest["version"].split("."))
        self.assertGreaterEqual(version, (19, 0, 1, 131, 0))

    def test_contextual_forum_uses_native_odoo_forum_flow(self):
        manifest = MANIFEST.read_text(encoding="utf-8")
        controller = (MODULE_ROOT / "controllers" / "community.py").read_text(encoding="utf-8")
        prefill = (MODULE_ROOT / "static" / "src" / "js" / "forum_prefill.js").read_text(encoding="utf-8")

        self.assertIn('"website_forum"', manifest)
        self.assertIn('"/community/new"', controller)
        self.assertIn('/ask?', controller)
        self.assertIn('"question", "share"', controller)
        self.assertIn("unit_id", controller)
        self.assertIn("course_id", controller)
        self.assertIn("slide_id", controller)
        self.assertIn("facodi-forum-question-cta", self.curriculum)
        self.assertIn("facodi-forum-share-cta", self.curriculum)
        self.assertIn("facodi-forum-question-cta", self.slides)
        self.assertIn("facodi-forum-share-cta", self.slides)
        self.assertIn("Never overwrite", prefill)

    def test_portal_progress_avoids_old_style_percent_formatting(self):
        portal_home = PORTAL_HOME.read_text(encoding="utf-8")
        self.assertNotIn("width: %.0f%%", portal_home)
        self.assertNotIn("t-att-aria-valuenow=\"'%.0f' %", portal_home)
        self.assertIn('t-attf-style="width: #{row[\'completion\']}%"', portal_home)
        self.assertIn('t-att-aria-valuenow="round(row[\'completion\'])"', portal_home)

    def test_explore_menu_reconciles_only_facodi_website_root(self):
        menu_data = WEBSITE_MENU.read_text(encoding="utf-8")
        menu_model = WEBSITE_MENU_MODEL.read_text(encoding="utf-8")

        self.assertIn('name="facodi_reconcile_navigation"', menu_data)
        self.assertNotIn('id="menu_public_explore"', menu_data)
        self.assertIn('("domain", "ilike", "facodi.com")', menu_model)
        self.assertIn('("website_id", "=", facodi.id)', menu_model)
        self.assertIn('("parent_id", "=", root.id)', menu_model)

        for route in (
            "/courses",
            "/explore/areas",
            "/explore/content",
            "/explore/videos",
            "/roadmaps",
            "/curricular-units",
        ):
            self.assertIn(f'"{route}"', menu_model)

        self.assertNotIn('<record ', menu_data)
        self.assertNotIn('ref="website.default_website"', menu_data)
        self.assertNotIn('ref="website.website_2"', menu_data)
        self.assertIn('("website_id", "=", False)', menu_model)
        self.assertIn('("id", "!=", parent.id)', menu_model)
        self.assertIn('descendants = duplicates.mapped("child_id") - menu', menu_model)
        self.assertIn('descendants = duplicate_explore.mapped("child_id") - explore', menu_model)
        self.assertIn("stale_top_level.unlink()", menu_model)
        self.assertIn('("Learning paths", "/roadmaps", 20, ())', menu_model)
        self.assertIn('ensure_menu("Project & team", "/about#project"', menu_model)
        self.assertIn('ensure_menu("Partnerships", "/partners"', menu_model)
        self.assertIn('ensure_menu("Discussions", "/forum", 20, community)', menu_model)
        self.assertIn('"url": "/about"', menu_model)
        self.assertNotIn('"url": "/sobre"', menu_model)

    def test_explore_filter_chips_have_individual_remove_urls(self):
        explore_controller = (MODULE_ROOT / "controllers" / "explore.py").read_text(encoding="utf-8")
        explore_view = (MODULE_ROOT / "views" / "website_explore.xml").read_text(encoding="utf-8")
        self.assertIn('filter_row["remove_url"] = "/explore/content"', explore_controller)
        self.assertIn('remove_params[filter_row["key"]] = False', explore_controller)
        self.assertIn("facodi-filter-chip__remove", explore_view)
        self.assertIn("t-att-href=\"filter_row['remove_url']\"", explore_view)

    def test_explore_uses_orm_filtering_and_bounded_pagination(self):
        explore_controller = (MODULE_ROOT / "controllers" / "explore.py").read_text(encoding="utf-8")
        self.assertIn("Slide.search_count(slide_domain)", explore_controller)
        self.assertIn("offset=offset", explore_controller)
        self.assertIn("limit=self.PAGE_SIZE", explore_controller)
        self.assertIn('("name", "ilike", query)', explore_controller)
        self.assertIn('("description", "ilike", query)', explore_controller)
        self.assertIn('("channel_id.tag_ids", "in", [area_id])', explore_controller)
        self.assertIn('("tag_ids.name", "=", f"{self.LANGUAGE_PREFIX}{language}")', explore_controller)
        self.assertNotIn("filtered = all_slides", explore_controller)

    def test_explore_map_exposes_dynamic_learning_destinations(self):
        explore = (MODULE_ROOT / "views" / "website_explore.xml").read_text(encoding="utf-8")
        controller = (MODULE_ROOT / "controllers" / "explore.py").read_text(encoding="utf-8")
        for marker in (
            'data-facodi-explore-map="1"',
            'data-facodi-spotlight="1"',
            'data-facodi-scramble="1"',
            'href="/courses"',
            'href="/roadmaps"',
            'href="/curricular-units"',
            'href="/explore/content"',
            '/submissions/new?type=resource&amp;source=explore_map_resource_cta',
        ):
            self.assertIn(marker, explore)
        for key in ('"courses"', '"resources"', '"roadmaps"', '"units"', '"community"', '"areas"'):
            self.assertIn(key, controller)

    def test_roadmap_catalogue_exposes_d1_structure(self):
        self.assertIn('id="curriculum_public_index"', self.curriculum)
        self.assertIn("facodi-learning-hero", self.curriculum)
        self.assertIn("facodi-index-tabs", self.curriculum)
        self.assertIn("facodi-record-card--roadmap", self.curriculum)
        self.assertIn("/roadmaps", self.curriculum)
        self.assertIn("/curricular-units", self.curriculum)

    def test_unit_catalogue_gap_cta_uses_entry_unit_context(self):
        unit_index = self.curriculum.split(
            '<template id="curriculum_public_unit_index"',
            1,
        )[1].split(
            '<template id="curriculum_public_unit"',
            1,
        )[0]
        self.assertNotIn(
            "'/contribuir/recurso?curriculum_unit_id=%s' % unit.id",
            unit_index,
        )
        self.assertIn(
            "'/submissions/new?type=resource&amp;unit_id=%s&amp;source=unit_resource_cta&amp;section=resources' % entry['unit'].id",
            unit_index,
        )

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

    def test_learning_addon_does_not_duplicate_theme_catalogue_navigation(self):
        self.assertNotIn("curriculum_catalog_navigation", self.slides)
        self.assertNotIn('aria-label="Aprendizagem FACODI"', self.slides)

    def test_course_alignment_and_contribution_expose_d1_hooks(self):
        self.assertIn("facodi-course-alignment-sheet", self.curriculum)
        self.assertIn("facodi-open-callout", self.slides)
        self.assertIn("/submissions/new?type=resource", self.slides)
        self.assertIn("source=course_resource_cta", self.slides)

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
