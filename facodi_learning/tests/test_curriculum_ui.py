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

    def test_public_curriculum_qweb_views_are_explicit_and_standard_first(self):
        index = self.env.ref("facodi_learning.curriculum_public_index")
        detail = self.env.ref("facodi_learning.curriculum_public_detail")
        unit_index = self.env.ref("facodi_learning.curriculum_public_unit_index")
        course_link = self.env.ref(
            "facodi_learning.approved_course_curriculum_links"
        )

        self.assertEqual(index.type, "qweb")
        self.assertEqual(detail.type, "qweb")
        self.assertEqual(unit_index.type, "qweb")
        self.assertEqual(course_link.type, "qweb")
        self.assertIn("website.layout", index.arch_db)
        self.assertIn("website.layout", detail.arch_db)
        self.assertIn("/curricular-units", unit_index.arch_db)
        self.assertIn("facodi-learning-hero", index.arch_db)
        self.assertIn("facodi-index-tabs", index.arch_db)
        self.assertIn("facodi-record-card--roadmap", index.arch_db)
        self.assertIn("facodi-learning-hero", unit_index.arch_db)
        self.assertIn("facodi-index-tabs", unit_index.arch_db)
        self.assertIn("facodi-filter-sheet", unit_index.arch_db)
        self.assertIn("facodi-record-card--unit", unit_index.arch_db)
        self.assertIn("reference_id", unit_index.arch_db)
        self.assertIn("period", unit_index.arch_db)
        self.assertIn("source_url", detail.arch_db)
        self.assertIn("coverage_links", detail.arch_db)
        self.assertIn("facodi-roadmap-study-path", detail.arch_db)
        self.assertIn("entry['learning']['modules']", detail.arch_db)
        self.assertIn("/roadmaps", detail.arch_db)
        self.assertEqual(course_link.inherit_id.key, "website_slides.course_main")
        self.assertNotIn("slide.slide", detail.arch_db)
        self.assertNotIn("facodi.learning.curriculum.coverage", detail.arch_db)

    def test_public_roadmaps_menu_uses_the_canonical_route(self):
        website = self.env["website"].search([], order="id", limit=1)
        self.assertTrue(website)
        website.domain = "https://facodi.com"

        self.assertTrue(self.env["website.menu"].facodi_reconcile_navigation())

        menus = self.env["website.menu"].search(
            [
                ("website_id", "=", website.id),
                ("url", "=", "/roadmaps"),
            ]
        )
        self.assertEqual(len(menus), 1)
        menu = menus[0]
        self.assertEqual(menu.name, "Roadmaps")
        self.assertEqual(menu.url, "/roadmaps")
        self.assertEqual(menu.parent_id.name, "Explore")
        self.assertEqual(menu.parent_id.parent_id, website.menu_id)
        self.assertEqual(menu.parent_id.url, "#")
        self.assertEqual(menu.parent_id.sequence, 10)
        self.assertEqual(website.default_lang_id.code, "en_US")
        self.assertEqual(
            website.menu_id.child_id.sorted("sequence").mapped("name")[:5],
            ["Home", "Explore", "Community", "About", "Contact"],
        )

        for code in ("pt_PT", "es_ES", "fr_FR"):
            self.env["res.lang"]._activate_lang(code)
        website.language_ids = self.env["res.lang"].search(
            [("code", "in", ["en_US", "pt_PT", "es_ES", "fr_FR"])]
        )
        self.assertTrue(self.env["website.menu"].facodi_reconcile_navigation())
        expected_names = {
            "pt_PT": (
                "Explorar",
                "Roadmaps",
                "Unidades curriculares",
                "Comunidade",
                "Sobre",
                "Contacto",
            ),
            "es_ES": (
                "Explorar",
                "Rutas",
                "Unidades curriculares",
                "Comunidad",
                "Acerca de",
                "Contacto",
            ),
            "fr_FR": (
                "Explorer",
                "Parcours",
                "Unités d’enseignement",
                "Communauté",
                "À propos",
                "Contact",
            ),
        }
        units_menu = self.env["website.menu"].search(
            [
                ("website_id", "=", website.id),
                ("url", "=", "/curricular-units"),
            ],
            limit=1,
        )
        community_menu = self.env["website.menu"].search(
            [
                ("website_id", "=", website.id),
                ("parent_id", "=", website.menu_id.id),
                ("url", "=", "#"),
                ("name", "=", "Community"),
            ],
            limit=1,
        )
        about_menu = self.env["website.menu"].search(
            [
                ("website_id", "=", website.id),
                ("parent_id", "=", website.menu_id.id),
                ("url", "in", ["/sobre", "/about"]),
            ],
            limit=1,
        )
        contact_menu = self.env["website.menu"].search(
            [
                ("website_id", "=", website.id),
                ("parent_id", "=", website.menu_id.id),
                ("url", "=", "/contact"),
            ],
            limit=1,
        )
        self.assertTrue(community_menu)
        self.assertTrue(about_menu)
        self.assertTrue(contact_menu)
        self.assertEqual(contact_menu.url, "/contact")

        for code, (
            explore_name,
            roadmap_name,
            units_name,
            community_name,
            about_name,
            contact_name,
        ) in expected_names.items():
            self.assertEqual(menu.parent_id.with_context(lang=code).name, explore_name)
            self.assertEqual(menu.with_context(lang=code).name, roadmap_name)
            self.assertEqual(units_menu.with_context(lang=code).name, units_name)
            self.assertEqual(
                community_menu.with_context(lang=code).name, community_name
            )
            self.assertEqual(about_menu.with_context(lang=code).name, about_name)
            self.assertEqual(contact_menu.with_context(lang=code).name, contact_name)

        course_menus = self.env["website.menu"].search(
            [
                ("website_id", "=", website.id),
                ("url", "=", "/courses"),
            ]
        )
        self.assertEqual(len(course_menus), 1)
        self.assertEqual(course_menus.parent_id, menu.parent_id)

        news_menu = self.env["website.menu"].search(
            [("website_id", "=", website.id), ("url", "=", "/blog")], limit=1
        )
        contribute_menu = self.env["website.menu"].search(
            [
                ("website_id", "=", website.id),
                ("url", "=", "/submissions/new?type=resource"),
            ],
            limit=1,
        )
        self.assertEqual(news_menu.parent_id, community_menu)
        self.assertEqual(contribute_menu.parent_id, community_menu)

        # Reconciliation is idempotent and must not recreate legacy/duplicate
        # Explore or Learn trees on every module update.
        self.assertTrue(self.env["website.menu"].facodi_reconcile_navigation())
        explore_menus = self.env["website.menu"].search(
            [
                ("website_id", "=", website.id),
                ("parent_id", "=", website.menu_id.id),
                ("name", "=", "Explore"),
            ]
        )
        self.assertEqual(len(explore_menus), 1)
        self.assertEqual(explore_menus.url, "#")
        self.assertFalse(
            self.env["website.menu"].search(
                [
                    ("website_id", "=", website.id),
                    ("url", "in", [
                        "/explorar/areas",
                        "/explorar/conteudos",
                        "/explorar/videos",
                        "/unidades-curriculares",
                    ]),
                ]
            )
        )

    def test_navigation_reconcile_accepts_explicit_domainless_website_context(self):
        website = self.env["website"].search([], order="id", limit=1)
        self.assertTrue(website)
        website.domain = False

        Menu = self.env["website.menu"]
        self.assertFalse(Menu.facodi_reconcile_navigation())
        self.assertTrue(
            Menu.with_context(website_id=website.id).facodi_reconcile_navigation()
        )
        explore = Menu.search(
            [
                ("website_id", "=", website.id),
                ("parent_id", "=", website.menu_id.id),
                ("url", "=", "#"),
            ],
            limit=1,
        )
        self.assertTrue(explore)
        self.assertEqual(explore.with_context(lang="en_US").name, "Explore")
