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

    def test_portal_home_projects_public_academic_map_without_claiming_completion(self):
        owner = self._portal_user("facodi-portal-roadmap")
        reference = self.env["facodi.learning.curriculum.reference"].sudo().create(
            {
                "institution": "Open University",
                "programme_name": "Open Computing",
                "academic_year": "2026/27",
                "provider": "portal-test",
                "external_id": "portal-roadmap-2026",
                "website_published": True,
                "validated_at": "2026-09-26 12:00:00",
                "selection_enabled": True,
            }
        )
        unit = self.env["facodi.learning.curriculum.unit"].sudo().create(
            {
                "reference_id": reference.id,
                "external_unit_code": "OC101",
                "name": "Open Algorithms",
                "curricular_year": 1,
                "period": "semester_1",
                "sequence": 10,
            }
        )

        self.authenticate(owner.login, "facodi-test-pass")
        response = self.url_open("/my/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-facodi-academic-map="1"', response.text)
        self.assertIn(reference.programme_name, response.text)
        self.assertIn(unit.name, response.text)
        self.assertIn("open gaps", response.text)
        self.assertNotIn("completed UC", response.text)

    def test_portal_home_keeps_campus_pulse_available_without_forum_dependency(self):
        owner = self._portal_user("facodi-portal-pulse")
        self.authenticate(owner.login, "facodi-test-pass")

        response = self.url_open("/my/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-facodi-campus-pulse="1"', response.text)
        self.assertIn("Campus pulse", response.text)

    def test_legacy_minha_facodi_alias_redirects_to_standard_portal_home(self):
        owner = self._portal_user("facodi-portal-alias")
        self.authenticate(owner.login, "facodi-test-pass")

        response = self.url_open("/minha-facodi", allow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.headers["Location"].endswith("/my/home"))

        canonical = self.url_open("/my/home")
        self.assertEqual(canonical.status_code, 200)
        self.assertIn('data-facodi-portal-home="1"', canonical.text)

    def test_public_portal_home_requires_authentication(self):
        response = self.url_open("/my/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/web/login", response.url)
