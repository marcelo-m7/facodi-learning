from odoo import api, models


class WebsiteMenu(models.Model):
    _inherit = "website.menu"

    @api.model
    def facodi_reconcile_navigation(self):
        """Keep FACODI discovery navigation isolated from other websites."""
        Website = self.env["website"].sudo()
        Menu = self.sudo()

        facodi = Website.search([("domain", "ilike", "facodi.com")], limit=1)
        if not facodi:
            return False

        root = Menu.search(
            [("website_id", "=", facodi.id), ("parent_id", "=", False)],
            order="id",
            limit=1,
        )
        if not root:
            return False

        explore_candidates = Menu.search(
            [
                ("website_id", "=", facodi.id),
                ("parent_id", "=", root.id),
                "|",
                ("url", "=", "/explore"),
                "&",
                ("url", "=", "#"),
                ("name", "=", "Explore"),
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
            explore.write({"name": "Explore", "url": "#", "sequence": 10})

        duplicate_explore = explore_candidates - explore
        if duplicate_explore:
            duplicate_explore.mapped("child_id").write({"parent_id": explore.id})
            duplicate_explore.unlink()

        entries = (
            ("Courses", "/courses", 10),
            ("Areas", "/explore/areas", 20),
            ("Learning resources", "/explore/content", 30),
            ("Community videos", "/explore/videos", 40),
            ("Roadmaps", "/roadmaps", 50),
            ("Curricular units", "/curricular-units", 60),
        )
        target_urls = {url for _name, url, _sequence in entries}
        legacy_urls = {
            "/slides",
            "/explorar/areas",
            "/explorar/conteudos",
            "/explorar/videos",
            "/unidades-curriculares",
        }

        for name, url, sequence in entries:
            matches = Menu.search(
                [
                    ("website_id", "=", facodi.id),
                    ("url", "=", url),
                ],
                order="id",
            )
            menu = matches.filtered(lambda item: item.parent_id == explore)[:1]
            if not menu:
                menu = Menu.create(
                    {
                        "name": name,
                        "url": url,
                        "parent_id": explore.id,
                        "website_id": facodi.id,
                        "sequence": sequence,
                    }
                )
            else:
                menu.write(
                    {
                        "name": name,
                        "parent_id": explore.id,
                        "website_id": facodi.id,
                        "sequence": sequence,
                    }
                )

            duplicates = matches - menu
            duplicates.filtered(
                lambda item: item.parent_id == explore or item.parent_id == root
            ).unlink()

        learn_groups = Menu.search(
            [
                ("website_id", "=", facodi.id),
                ("parent_id", "=", root.id),
                ("url", "=", "#"),
                ("name", "in", ["Learn", "Learning"]),
            ]
        )
        for learn in learn_groups:
            children = Menu.search([("parent_id", "=", learn.id)])
            if children and set(children.mapped("url")).issubset(target_urls):
                learn.unlink()

        stale_entries = Menu.search(
            [
                ("website_id", "=", facodi.id),
                ("parent_id", "in", [explore.id, root.id]),
                ("url", "in", list(legacy_urls)),
            ]
        )
        if stale_entries:
            stale_entries.unlink()

        # Remove only website-less legacy Explore trees from this module's
        # previous generic data. Other websites remain untouched.
        generic_explore = Menu.search(
            [("website_id", "=", False), ("url", "=", "/explore")]
        )
        generic_explore.unlink()
        return True
