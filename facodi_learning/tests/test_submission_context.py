from lxml import html

from odoo.tests import HttpCase, TransactionCase, tagged

from ..services.curriculum_bootstrap import ensure_lesti_2026_27


class TestSubmissionContextModel(TransactionCase):
    def test_source_url_normalization_is_stable_for_duplicate_checks(self):
        Submission = self.env["facodi.learning.submission"]
        self.assertEqual(
            Submission._normalize_source_url(
                "HTTPS://Example.org:443/resource/#section"
            ),
            "https://example.org/resource",
        )
        self.assertEqual(
            Submission._normalize_source_url(
                "https://example.org/resource?b=2&a=1"
            ),
            "https://example.org/resource?b=2&a=1",
        )


@tagged("-at_install", "post_install")
class TestSubmissionContextWebsite(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reference = ensure_lesti_2026_27(cls.env)
        cls.database_unit = cls.reference.unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19411017"
        )
        cls.programming_unit = cls.reference.unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19411000"
        )
        cls.private_reference = cls.env[
            "facodi.learning.curriculum.reference"
        ].create(
            {
                "institution": "Private",
                "programme_name": "Private",
                "academic_year": "2026/27",
                "provider": "manual",
                "external_id": "private-submission-context",
            }
        )
        cls.private_unit = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.private_reference.id,
                "external_unit_code": "PRIVATE-SUBMISSION",
                "name": "Private Submission Unit",
            }
        )

    def _csrf_token(self, route="/contribuir/recurso"):
        response = self.url_open(route)
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        tokens = tree.xpath('//input[@name="csrf_token"]/@value')
        self.assertEqual(len(tokens), 1)
        return tokens[0]

    def test_contextual_form_persists_only_public_curricular_unit(self):
        route = (
            "/contribuir/recurso?curriculum_unit_id=%s"
            % self.database_unit.id
        )
        response = self.url_open(route)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.database_unit.name, response.text)
        tree = html.fromstring(response.text)
        self.assertEqual(
            tree.xpath('//input[@name="curriculum_unit_id"]/@value'),
            [str(self.database_unit.id)],
        )

        before_coverage = self.env[
            "facodi.learning.curriculum.coverage"
        ].sudo().search_count([])
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(route),
                "name": "Contextual database resource",
                "source_url": "https://example.org/contextual-database",
                "curriculum_unit_id": str(self.database_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        submission = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "Contextual database resource")],
            limit=1,
        )
        self.assertEqual(submission.curriculum_unit_id, self.database_unit)
        self.assertIn(self.database_unit.name, response.text)
        self.assertEqual(
            self.env[
                "facodi.learning.curriculum.coverage"
            ].sudo().search_count([]),
            before_coverage,
        )

    def test_private_or_forged_curricular_context_is_not_persisted(self):
        before = self.env["facodi.learning.submission"].sudo().search_count([])
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(),
                "name": "Forged context",
                "source_url": "https://example.org/forged-context",
                "curriculum_unit_id": str(self.private_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "The curricular unit context is no longer publicly available.",
            response.text,
        )
        self.assertEqual(
            self.env["facodi.learning.submission"].sudo().search_count([]),
            before,
        )

    def test_active_duplicate_is_suppressed_without_leaking_tracking_token(self):
        first = self.env["facodi.learning.submission"].sudo().create(
            {
                "name": "Existing contextual suggestion",
                "source_url": "https://EXAMPLE.org:443/duplicate/#section",
                "curriculum_unit_id": self.database_unit.id,
            }
        )
        before = self.env["facodi.learning.submission"].sudo().search_count([])
        route = (
            "/contribuir/recurso?curriculum_unit_id=%s"
            % self.database_unit.id
        )
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(route),
                "name": "Duplicate contextual suggestion",
                "source_url": "https://example.org/duplicate",
                "curriculum_unit_id": str(self.database_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "already under editorial review for this context",
            response.text,
        )
        self.assertNotIn(first.access_token, response.text)
        self.assertEqual(
            self.env["facodi.learning.submission"].sudo().search_count([]),
            before,
        )

        other_route = (
            "/contribuir/recurso?curriculum_unit_id=%s"
            % self.programming_unit.id
        )
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(other_route),
                "name": "Same resource, different curricular unit",
                "source_url": "https://example.org/duplicate",
                "curriculum_unit_id": str(self.programming_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        second = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "Same resource, different curricular unit")],
            limit=1,
        )
        self.assertEqual(second.curriculum_unit_id, self.programming_unit)

    def test_rejected_history_does_not_block_resubmission(self):
        previous = self.env["facodi.learning.submission"].sudo().create(
            {
                "name": "Historical suggestion",
                "source_url": "https://example.org/history",
                "curriculum_unit_id": self.database_unit.id,
            }
        )
        previous.sudo().action_reject()

        route = (
            "/contribuir/recurso?curriculum_unit_id=%s"
            % self.database_unit.id
        )
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(route),
                "name": "New suggestion after rejection",
                "source_url": "https://example.org/history",
                "curriculum_unit_id": str(self.database_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        current = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "New suggestion after rejection")],
            limit=1,
        )
        self.assertTrue(current)
        self.assertEqual(current.state, "submitted")
