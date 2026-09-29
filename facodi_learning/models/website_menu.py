from odoo import api, models


class WebsiteMenu(models.Model):
    _inherit = "website.menu"

    @api.model
    def facodi_reconcile_navigation(self):
        """Reconcile the FACODI public navigation around an English-first IA."""
        Website = self.env["website"].sudo()
        Menu = self.sudo()

        context_website_id = self.env.context.get("website_id")
        facodi = (
            Website.browse(context_website_id).exists()
            if context_website_id
            else Website.search([("domain", "ilike", "facodi.com")], limit=1)
        )
        if not facodi or len(facodi) != 1:
            return False

        root = facodi.menu_id.sudo().exists()
        if not root:
            return False

        # English is the canonical/source language of the public FACODI website.
        # Keep other enabled languages available through Odoo's standard selector.
        Language = self.env["res.lang"].sudo().with_context(active_test=False)
        english = Language.search([("code", "=", "en_GB")], limit=1)
        if english:
            if not english.active:
                Language._activate_lang("en_GB")
                english = Language.search([("code", "=", "en_GB")], limit=1)
            write_values = {"default_lang_id": english.id}
            if english not in facodi.language_ids:
                write_values["language_ids"] = [(4, english.id)]
            facodi.write(write_values)

        active_language_codes = set(
            facodi.language_ids.filtered("active").mapped("code")
        )
        menu_translations = {
            "Home": {
                "pt_PT": "Início",
                "es_ES": "Inicio",
                "fr_FR": "Accueil",
            },
            "Explore": {
                "pt_PT": "Explorar",
                "es_ES": "Explorar",
                "fr_FR": "Explorer",
            },
            "Community": {
                "pt_PT": "Comunidade",
                "es_ES": "Comunidad",
                "fr_FR": "Communauté",
            },
            "About": {
                "pt_PT": "Sobre",
                "es_ES": "Acerca de",
                "fr_FR": "À propos",
            },
            "Contact": {
                "pt_PT": "Contacto",
                "es_ES": "Contacto",
                "fr_FR": "Contact",
            },
            "Courses": {
                "pt_PT": "Cursos",
                "es_ES": "Cursos",
                "fr_FR": "Cours",
            },
            "Roadmaps": {
                "pt_PT": "Roadmaps",
                "es_ES": "Rutas",
                "fr_FR": "Parcours",
            },
            "Curricular units": {
                "pt_PT": "Unidades curriculares",
                "es_ES": "Unidades curriculares",
                "fr_FR": "Unités d’enseignement",
            },
            "Areas": {
                "pt_PT": "Áreas",
                "es_ES": "Áreas",
                "fr_FR": "Domaines",
            },
            "Learning resources": {
                "pt_PT": "Recursos de aprendizagem",
                "es_ES": "Recursos de aprendizaje",
                "fr_FR": "Ressources d’apprentissage",
            },
            "Community videos": {
                "pt_PT": "Vídeos da comunidade",
                "es_ES": "Vídeos de la comunidad",
                "fr_FR": "Vidéos de la communauté",
            },
            "News": {
                "pt_PT": "Notícias",
                "es_ES": "Noticias",
                "fr_FR": "Actualités",
            },
            "Forum": {
                "pt_PT": "Fórum",
                "es_ES": "Foro",
                "fr_FR": "Forum",
            },
            "Contribute": {
                "pt_PT": "Contribuir",
                "es_ES": "Contribuir",
                "fr_FR": "Contribuer",
            },
        }

        source_language = english.code if english else (facodi.default_lang_id.code or self.env.lang)
        english_us = Language.search([("code", "=", "en_US")], limit=1)

        def write_menu_name(menu, source_name):
            # Odoo's stock website records may already carry an en_US translation
            # (for example \"Contact us\"). FACODI's canonical language is en_GB,
            # but keep both English variants aligned so callers running with the
            # base en_US context do not see stale stock labels during install/update.
            if english_us and english_us.active:
                menu.with_context(lang="en_US").write({"name": source_name})
            menu.with_context(lang=source_language).write({"name": source_name})
            for language_code, translated_name in menu_translations.get(
                source_name, {}
            ).items():
                if language_code in active_language_codes:
                    menu.with_context(lang=language_code).write(
                        {"name": translated_name}
                    )

        def ensure_menu(name, url, sequence, parent, aliases=()):
            candidates = Menu.search(
                [
                    ("website_id", "=", facodi.id),
                    ("id", "!=", parent.id),
                    ("url", "in", list({url, *aliases})),
                ],
                order="id",
            )
            # A navigable parent can intentionally share the canonical URL of
            # its first child (for example Explore -> /courses). The search
            # domain excludes that parent, so it can never be reused or deleted
            # while reconciling the child that points to the same destination.
            menu = candidates.filtered(lambda item: item.parent_id == parent)[:1]
            if not menu:
                menu = candidates[:1]
            values = {
                "url": url,
                "parent_id": parent.id,
                "website_id": facodi.id,
                "sequence": sequence,
            }
            if menu:
                # A legacy Website page menu can be reused through an alias
                # (notably /contactus -> /contact).  Once its URL points to a
                # controller route, keeping the old page/controller ownership
                # makes Odoo's menu editor call ir.http._match() while handling
                # its POST RPC. GET-only FACODI routes then raise 405 and the
                # whole menu editor cannot be saved.
                if menu.page_id and menu.page_id.url != url:
                    values["page_id"] = False
                if menu.controller_page_id and menu.url != url:
                    values["controller_page_id"] = False
                menu.write(values)
            else:
                menu = Menu.create({"name": name, **values})
            write_menu_name(menu, name)

            duplicates = candidates - menu
            if duplicates:
                # Preserve custom descendants before deduplicating a legacy shell.
                # Never reparent the canonical menu to itself if a malformed or
                # legacy tree happens to expose it through a duplicate's children.
                descendants = duplicates.mapped("child_id") - menu
                if descendants:
                    descendants.write({"parent_id": menu.id})
                duplicates.unlink()
            return menu

        home = ensure_menu("Home", "/", 5, root)

        explore_candidates = Menu.search(
            [
                ("website_id", "=", facodi.id),
                ("parent_id", "=", root.id),
                "|",
                ("url", "in", ["/explore", "/courses"]),
                "&",
                ("url", "=", "#"),
                ("name", "in", ["Explore", "Learn", "Learning"]),
            ],
            order="id",
        )
        explore = explore_candidates[:1]
        if not explore:
            explore = Menu.create(
                {
                    "name": "Explore",
                    "url": "#",
                    "parent_id": root.id,
                    "website_id": facodi.id,
                    "sequence": 10,
                }
            )
        else:
            explore.write(
                {
                    "url": "#",
                    "parent_id": root.id,
                    "website_id": facodi.id,
                    "sequence": 10,
                }
            )
        write_menu_name(explore, "Explore")

        duplicate_explore = explore_candidates - explore
        if duplicate_explore:
            descendants = duplicate_explore.mapped("child_id") - explore
            if descendants:
                descendants.write({"parent_id": explore.id})
            duplicate_explore.unlink()

        learning_entries = (
            ("Courses", "/courses", 10, ("/slides", "/explore/courses")),
            ("Roadmaps", "/roadmaps", 20, ()),
            (
                "Curricular units",
                "/curricular-units",
                30,
                ("/unidades-curriculares",),
            ),
            ("Areas", "/explore/areas", 40, ("/explorar/areas",)),
            (
                "Learning resources",
                "/explore/content",
                50,
                ("/explorar/conteudos",),
            ),
            (
                "Community videos",
                "/explore/videos",
                60,
                ("/explorar/videos",),
            ),
        )
        for name, url, sequence, aliases in learning_entries:
            ensure_menu(name, url, sequence, explore, aliases=aliases)

        # Group community actions so the primary navbar stays compact on desktop
        # while the standard Odoo mobile menu keeps the same hierarchy.
        community_candidates = Menu.search(
            [
                ("website_id", "=", facodi.id),
                ("parent_id", "=", root.id),
                ("url", "in", ["#", "/forum"]),
                ("name", "in", ["Community", "Comunidade", "Comunidad", "Communauté"]),
            ],
            order="id",
        )
        community = community_candidates[:1]
        if not community:
            community = Menu.create(
                {
                    "name": "Community",
                    "url": "#",
                    "parent_id": root.id,
                    "website_id": facodi.id,
                    "sequence": 20,
                }
            )
        else:
            community.write(
                {
                    "url": "#",
                    "parent_id": root.id,
                    "website_id": facodi.id,
                    "sequence": 20,
                }
            )
        write_menu_name(community, "Community")
        duplicate_community = community_candidates - community
        if duplicate_community:
            descendants = duplicate_community.mapped("child_id") - community
            if descendants:
                descendants.write({"parent_id": community.id})
            duplicate_community.unlink()

        # Do not expose an empty News destination. website_blog is optional
        # for facodi_learning, so discover it through installed modules before
        # touching blog.post. When public posts appear, reconciliation restores
        # the standard /blog entry automatically.
        blog_installed = bool(
            self.env["ir.module.module"].sudo().search_count(
                [("name", "=", "website_blog"), ("state", "=", "installed")]
            )
        )
        published_news = bool(
            blog_installed
            and self.env["blog.post"].sudo().search_count(
                [("website_published", "=", True)]
            )
        )
        existing_news = Menu.search(
            [("website_id", "=", facodi.id), ("url", "=", "/blog")]
        )
        if published_news:
            ensure_menu("News", "/blog", 10, community)
        elif existing_news:
            existing_news.unlink()

        forum_installed = bool(
            self.env["ir.module.module"].sudo().search_count(
                [("name", "=", "website_forum"), ("state", "=", "installed")]
            )
        )
        existing_forum = Menu.search(
            [("website_id", "=", facodi.id), ("url", "=", "/forum")], limit=1
        )
        if forum_installed or existing_forum:
            ensure_menu("Forum", "/forum", 20, community)

        ensure_menu(
            "Contribute",
            "/submissions/new?type=resource&source=main_nav_contribute&section=header",
            30,
            community,
            aliases=("/contribuir/recurso", "/contribuir"),
        )

        # Keep the editor-owned About page and any manually curated children.
        about_candidates = Menu.search(
            [
                ("website_id", "=", facodi.id),
                ("url", "in", ["/sobre", "/about"]),
            ],
            order="id",
        )
        about = about_candidates.filtered(lambda item: item.parent_id == root)[:1]
        if not about:
            about = about_candidates[:1]
        if not about:
            about = Menu.create(
                {
                    "name": "About",
                    "url": "/sobre",
                    "parent_id": root.id,
                    "website_id": facodi.id,
                    "sequence": 30,
                }
            )
        else:
            about.write(
                {
                    "parent_id": root.id,
                    "website_id": facodi.id,
                    "sequence": 30,
                }
            )
        write_menu_name(about, "About")
        duplicate_about = about_candidates - about
        if duplicate_about:
            descendants = duplicate_about.mapped("child_id") - about
            if descendants:
                descendants.write({"parent_id": about.id})
            duplicate_about.unlink()

        ensure_menu("Contact", "/contact", 40, root, aliases=("/contactus",))

        # Remove stale top-level shells left by previous iterations now that their
        # destinations are owned by Explore/Community.
        stale_top_level = Menu.search(
            [
                ("website_id", "=", facodi.id),
                ("parent_id", "=", root.id),
                ("id", "not in", [home.id, explore.id, community.id, about.id]),
                (
                    "url",
                    "in",
                    [
                        "/slides",
                        "/courses",
                        "/roadmaps",
                        "/curricular-units",
                        "/unidades-curriculares",
                        "/explore/areas",
                        "/explore/content",
                        "/explore/videos",
                        "/blog",
                        "/forum",
                        "/contribuir/recurso",
                        "/contribuir",
                        "/submissions/new?type=resource",
                        "/submissions/new?type=resource&source=main_nav_contribute&section=header",
                    ],
                ),
            ]
        )
        if stale_top_level:
            stale_top_level.unlink()

        # Remove only website-less legacy Explore trees from this module's old
        # generic data. Other websites remain untouched.
        generic_explore = Menu.search(
            [("website_id", "=", False), ("url", "=", "/explore")]
        )
        generic_explore.unlink()
        return True
