from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCanonicalRoutes(HttpCase):
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
