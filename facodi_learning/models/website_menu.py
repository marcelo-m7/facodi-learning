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

        explore = Menu.search(
            [
                ("website_id", "=", facodi.id),
                ("parent_id", "=", root.id),
                ("url", "=", "/explorar"),
            ],
            order="id",
            limit=1,
        )
        if not explore:
            explore = Menu.create(
                {
                    "name": "Explore",
                    "url": "/explorar",
                    "parent_id": root.id,
                    "website_id": facodi.id,
                    "sequence": 40,
                }
            )
        else:
            explore.write({"name": "Explore", "sequence": 40})

        entries = (
            ("Courses", "/slides", 10),
            ("Areas", "/explorar/areas", 20),
            ("Learning resources", "/explorar/conteudos", 30),
            ("Community videos", "/explorar/videos", 40),
            ("Roadmaps", "/roadmaps", 50),
            ("Curricular units", "/unidades-curriculares", 60),
        )
        target_urls = {url for _name, url, _sequence in entries}

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

        # Remove only website-less legacy Explore trees from this module's
        # previous generic data. Other websites remain untouched.
        generic_explore = Menu.search(
            [("website_id", "=", False), ("url", "=", "/explorar")]
        )
        generic_explore.unlink()
        return True
