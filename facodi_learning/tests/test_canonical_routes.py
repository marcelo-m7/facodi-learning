from lxml import html

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCanonicalRoutes(HttpCase):
    def test_portuguese_learning_routes_render_without_inheritance_errors(self):
        website = self.env["website"].get_current_website()
        lang_pt = self.env["res.lang"]._activate_lang("pt_PT")
        lang_en = self.env["res.lang"]._activate_lang("en_GB")\n        website.language_ids = lang_en + lang_pt

        for route in ("/pt/roadmaps", "/pt/curricular-units", "/pt/courses"):
            response = self.url_open(route, allow_redirects=True)
            self.assertEqual(response.status_code, 200, route)
            self.assertNotIn("Internal Server Error", response.text, route)

    def test_courses_entrypoint_keeps_native_elearning_owner(self):
        response = self.url_open("/courses", allow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/slides"))

    def test_curricular_units_canonical_route_renders(self):
        response = self.url_open("/curricular-units")
        self.assertEqual(response.status_code, 200)

    def test_legacy_curricular_units_redirect_permanently(self):
        response = self.url_open("/unidades-curriculares", allow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.headers["Location"].endswith("/curricular-units"))

    def test_public_learning_indexes_expose_one_description_and_canonical(self):
        for route in (
            "/explore",
            "/explore/areas",
            "/explore/content",
            "/explore/videos",
            "/roadmaps",
            "/curricular-units",
        ):
            response = self.url_open(route)
            self.assertEqual(response.status_code, 200, route)
            tree = html.fromstring(response.text)
            descriptions = tree.xpath('//meta[@name="description"]/@content')
            open_graph = tree.xpath('//meta[@property="og:description"]/@content')
            canonicals = tree.xpath('//link[@rel="canonical"]/@href')
            self.assertEqual(len(descriptions), 1, route)
            self.assertTrue(descriptions[0].strip(), route)
            self.assertEqual(open_graph, descriptions, route)
            self.assertEqual(len(canonicals), 1, route)
            canonical_path = canonicals[0].split("?", 1)[0].rstrip("/")
            self.assertTrue(canonical_path.endswith(route.rstrip("/")), (route, canonicals[0]))

    def test_legacy_explore_aliases_do_not_compete_with_canonical_routes(self):
        for legacy, canonical in (
            ("/explorar", "/explore"),
            ("/explorar/areas", "/explore/areas"),
            ("/explorar/conteudos", "/explore/content"),
            ("/explorar/videos", "/explore/videos"),
        ):
            response = self.url_open(legacy, allow_redirects=False)
            self.assertEqual(response.status_code, 301, legacy)
            self.assertTrue(response.headers["Location"].endswith(canonical), legacy)
