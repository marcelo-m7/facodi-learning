from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase

from ..services.curriculum import CurriculumFetchError


HTML_V1 = b"""
<html>
  <body>
    <h1>Engenharia de Sistemas e Tecnologias Informaticas</h1>
    <div data-academic-year="2026/27">2026/27</div>
    <table>
      <tr><th>Codigo</th><th>Unidade Curricular</th><th>ECTS</th></tr>
      <tr><td>19411000</td><td>Programacao</td><td>5</td></tr>
    </table>
  </body>
</html>
"""

HTML_V2 = b"""
<html>
  <body>
    <h1>Engenharia de Sistemas e Tecnologias Informaticas</h1>
    <div data-academic-year="2026/27">2026/27</div>
    <table>
      <tr><th>Codigo</th><th>Unidade Curricular</th><th>ECTS</th></tr>
      <tr><td>19411000</td><td>Programacao</td><td>5</td></tr>
      <tr><td>19411001</td><td>Ambientes de Desenvolvimento Colaborativo</td><td>5</td></tr>
    </table>
  </body>
</html>
"""


class TestCurriculumSourceVerification(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Curriculum Verification Manager",
                "login": "curriculum-verification-manager",
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
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Curriculum Verification Officer",
                "login": "curriculum-verification-officer",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id,
                        ]
                    )
                ],
            }
        )
        cls.website = cls.env["website"].get_current_website()

    def _source(self, suffix="default", **extra):
        values = {
            "external_id": f"ualg-1941-{suffix}",
            "institution": "Universidade do Algarve",
            "programme_name": "Engenharia de Sistemas e Tecnologias Informaticas",
            "external_programme_code": "1941",
            "academic_year": "2026/27",
            "source_url": "https://www.ualg.pt/curso/1941/plano",
            "website_id": self.website.id,
            "responsible_id": self.manager.id,
        }
        values.update(extra)
        return self.env["facodi.learning.curriculum.source"].create(values)

    def _fetch(self, raw):
        return patch(
            "odoo.addons.facodi_learning.models.curriculum_source.fetch_official_curriculum",
            return_value=(raw, "https://www.ualg.pt/curso/1941/plano"),
        )

    def test_verification_is_opt_in_and_manager_only(self):
        source = self._source("permissions")
        self.assertFalse(source.verification_enabled)
        with self.assertRaises(AccessError):
            source.with_user(self.officer).action_verify_now()

    def test_first_check_creates_private_draft_and_replay_updates_checked_at(self):
        source = self._source("draft")
        with self._fetch(HTML_V1):
            status = source.with_user(self.manager)._verify_source_once()
        self.assertEqual(status, "changed")
        source.invalidate_recordset()
        reference = source.current_reference_id
        self.assertTrue(reference)
        self.assertEqual(reference.state, "draft")
        self.assertFalse(reference.website_published)
        self.assertEqual(len(reference.unit_ids), 1)
        self.assertEqual(source.last_check_status, "changed")
        first_checked_at = source.checked_at
        self.assertTrue(first_checked_at)
        self.assertEqual(
            len(source._problem_activity("changed")),
            1,
        )

        with self._fetch(HTML_V1):
            replay = source.with_user(self.manager)._verify_source_once()
        source.invalidate_recordset()
        self.assertEqual(replay, "ok")
        self.assertEqual(source.current_reference_id, reference)
        self.assertEqual(len(source.reference_ids), 1)
        self.assertEqual(source.last_check_status, "ok")
        self.assertTrue(source.checked_at)

    def test_changed_source_creates_new_draft_and_preserves_published_version(self):
        source = self._source("changed")
        with self._fetch(HTML_V1):
            source.with_user(self.manager)._verify_source_once()
        published = source.current_reference_id.with_user(self.manager)
        published.action_validate()
        published.action_publish()
        self.assertTrue(published.website_published)
        self.assertFalse(source._problem_activity("changed"))

        with self._fetch(HTML_V2):
            status = source.with_user(self.manager)._verify_source_once()
        source.invalidate_recordset()
        draft = source.current_reference_id
        self.assertEqual(status, "changed")
        self.assertNotEqual(draft, published)
        self.assertEqual(draft.state, "draft")
        self.assertFalse(draft.website_published)
        self.assertEqual(len(draft.unit_ids), 2)
        published.invalidate_recordset()
        self.assertTrue(published.website_published)
        self.assertEqual(published.state, "validated")
        self.assertEqual(len(source._problem_activity("changed")), 1)

    def test_failure_preserves_published_reference_and_deduplicates_activity(self):
        source = self._source("failure")
        with self._fetch(HTML_V1):
            source.with_user(self.manager)._verify_source_once()
        published = source.current_reference_id.with_user(self.manager)
        published.action_validate()
        published.action_publish()

        failure = CurriculumFetchError("Official curriculum request failed.")
        with patch(
            "odoo.addons.facodi_learning.models.curriculum_source.fetch_official_curriculum",
            side_effect=failure,
        ):
            first = source.with_user(self.manager)._verify_source_once()
            second = source.with_user(self.manager)._verify_source_once()

        source.invalidate_recordset()
        published.invalidate_recordset()
        self.assertEqual(first, "failed")
        self.assertEqual(second, "failed")
        self.assertEqual(source.current_reference_id, published)
        self.assertTrue(published.website_published)
        self.assertEqual(source.last_check_status, "failed")
        self.assertIn("request failed", source.last_check_error)
        self.assertEqual(len(source._problem_activity("failed")), 1)
        self.assertEqual(
            len(source.capture_ids.filtered(lambda capture: capture.status == "failed")),
            2,
        )

    def test_daily_cron_processes_only_opted_in_sources(self):
        disabled = self._source("cron-disabled")
        enabled = self._source("cron-enabled", verification_enabled=True)

        with self._fetch(HTML_V1):
            self.env["facodi.learning.curriculum.source"]._cron_verify_enabled_sources()

        disabled.invalidate_recordset()
        enabled.invalidate_recordset()
        self.assertFalse(disabled.last_attempt_at)
        self.assertTrue(enabled.last_attempt_at)
        self.assertEqual(enabled.last_check_status, "changed")

    def test_http_policy_rejects_non_https_and_non_ualg_hosts_before_network(self):
        from ..services.curriculum import fetch_official_curriculum

        for url in (
            "http://www.ualg.pt/curso/1941/plano",
            "https://example.com/curso/1941/plano",
        ):
            with self.assertRaises(CurriculumFetchError):
                fetch_official_curriculum(url)

    def test_source_form_exposes_manual_verify_and_opt_in_controls(self):
        arch = self.env.ref(
            "facodi_learning.view_facodi_curriculum_source_form"
        ).arch_db
        self.assertIn('name="action_verify_now"', arch)
        self.assertIn('name="verification_enabled"', arch)
        self.assertIn('name="last_check_status"', arch)
        self.assertIn("<chatter", arch)
