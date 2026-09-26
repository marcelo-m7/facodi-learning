from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestFacodiPortalHome(HttpCase):
    def _portal_user(self, login):
        return self.env["res.users"].sudo().create(
            {
                "name": login,
                "login": login,
                "password": "facodi-test-pass",
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )

    def test_portal_home_exposes_only_owned_learning_and_contributions(self):
        owner = self._portal_user("facodi-portal-owner")
        stranger = self._portal_user("facodi-portal-stranger")

        course = self.env["slide.channel"].sudo().create(
            {
                "name": "FACODI Portal Course",
                "is_published": True,
                "partner_ids": [(4, owner.partner_id.id)],
            }
        )
        self.env["facodi.learning.submission"].sudo().create(
            {
                "name": "Owner portal contribution",
                "source_url": "https://example.org/owner-portal",
                "submitted_by_id": owner.id,
            }
        )
        self.env["facodi.learning.submission"].sudo().create(
            {
                "name": "Stranger portal contribution",
                "source_url": "https://example.org/stranger-portal",
                "submitted_by_id": stranger.id,
            }
        )

        self.authenticate(owner.login, "facodi-test-pass")
        response = self.url_open("/my/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-facodi-portal-home="1"', response.text)
        self.assertIn("Your campus", response.text)
        self.assertIn(course.name, response.text)
        self.assertIn("Owner portal contribution", response.text)
        self.assertNotIn("Stranger portal contribution", response.text)
        self.assertIn("Your FACODI toolbox", response.text)

    def test_legacy_minha_facodi_alias_redirects_to_standard_portal_home(self):
        owner = self._portal_user("facodi-portal-alias")
        self.authenticate(owner.login, "facodi-test-pass")

        response = self.url_open("/minha-facodi")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.url.endswith("/my/home"))
        self.assertIn('data-facodi-portal-home="1"', response.text)

    def test_public_portal_home_requires_authentication(self):
        response = self.url_open("/my/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/web/login", response.url)
