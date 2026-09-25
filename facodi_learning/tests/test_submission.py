from lxml import html

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


class TestResourceSubmissionModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Submission Manager",
                "login": "submission-manager",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id
                        ],
                    )
                ],
            }
        )
        cls.portal = cls.env["res.users"].create(
            {
                "name": "Submission Portal",
                "login": "submission-portal",
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )
        cls.Submission = cls.env["facodi.learning.submission"]

    def _submission(self, **extra):
        values = {
            "name": "Open learning resource",
            "source_url": "https://example.org/resource",
            "context": "Useful for database foundations.",
            "language": "en",
        }
        values.update(extra)
        return self.Submission.with_user(self.manager).create(values)

    def test_public_and_portal_have_no_direct_model_access(self):
        for user in (self.env.ref("base.public_user"), self.portal):
            with self.assertRaises(AccessError):
                self.Submission.with_user(user).search([]).read(["name"])
            with self.assertRaises(AccessError):
                self.Submission.with_user(user).create(
                    {
                        "name": "Denied",
                        "source_url": "https://example.org/denied",
                    }
                )

    def test_submission_defaults_to_submitted_with_private_tracking_token(self):
        submission = self._submission()
        self.assertEqual(submission.state, "submitted")
        self.assertTrue(submission.access_token)
        self.assertGreaterEqual(len(submission.access_token), 32)
        self.assertFalse(submission.candidate_id)
        self.assertFalse(submission.source_id)

    def test_source_url_must_be_public_http_or_https(self):
        for source_url in (
            "javascript:alert(1)",
            "ftp://example.org/resource",
            "file:///tmp/resource",
            "https:///missing-host",
        ):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self._submission(source_url=source_url)

    def test_direct_audit_state_forgery_is_denied(self):
        submission = self._submission()
        with self.assertRaises(AccessError):
            submission.write({"state": "accepted"})
        with self.assertRaises(AccessError):
            submission.write({"access_token": "forged"})
        with self.assertRaises(AccessError):
            submission.write({"reviewed_by_id": self.manager.id})

    def test_manager_review_transitions_are_explicit(self):
        submission = self._submission()
        submission.action_start_review()
        self.assertEqual(submission.state, "reviewing")

        slide_count = self.env["slide.slide"].search_count([])
        submission.action_accept()
        self.assertEqual(submission.state, "accepted")
        self.assertEqual(submission.reviewed_by_id, self.manager)
        self.assertTrue(submission.reviewed_at)
        self.assertEqual(self.env["slide.slide"].search_count([]), slide_count)

        with self.assertRaises(ValidationError):
            submission.action_resolve()

        channel = self.env["slide.channel"].create({"name": "Submission target"})
        source = self.env["facodi.learning.source"].create(
            {
                "name": "Submission source",
                "provider": "manual",
                "external_id": "submission-source-1",
                "url": submission.source_url,
                "channel_id": channel.id,
            }
        )
        submission.write({"source_id": source.id})
        submission.action_resolve()
        self.assertEqual(submission.state, "resolved")
        self.assertEqual(submission.source_id, source)

    def test_youtube_submission_handoff_preserves_submission_provenance(self):
        submission = self._submission(
            name="Pré-Cálculo",
            source_url=(
                "https://www.youtube.com/watch?v=w9gb71ZUJDs"
                "&list=PLa_2246N48_rlbheR_al4oqeFCP8dHoQR"
            ),
            language="pt",
        )
        submission.action_accept()
        action = submission.action_handoff_candidate()
        candidate = submission.candidate_id

        self.assertEqual(action["res_id"], candidate.id)
        self.assertEqual(candidate.provider, "facodi-submission")
        self.assertEqual(candidate.external_id, f"submission-{submission.id}")
        self.assertIn("youtube.com/watch?v=w9gb71ZUJDs", candidate.source_url)
        self.assertEqual(candidate.language, "pt")
        self.assertEqual(candidate.metadata["submission_id"], submission.id)

    def test_only_manager_can_take_terminal_review_actions(self):
        submission = self._submission()
        officer = self.env["res.users"].create(
            {
                "name": "Submission Officer",
                "login": "submission-officer",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id
                        ],
                    )
                ],
            }
        )
        with self.assertRaises(AccessError):
            submission.with_user(officer).action_accept()
        with self.assertRaises(AccessError):
            submission.with_user(officer).action_reject()


@tagged("-at_install", "post_install")
class TestResourceSubmissionWebsite(HttpCase):
    def _csrf_token(self):
        response = self.url_open("/contribuir/recurso")
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        tokens = tree.xpath('//input[@name="csrf_token"]/@value')
        self.assertEqual(len(tokens), 1)
        return tokens[0]

    def test_public_form_creates_submission_and_redirects_to_safe_status(self):
        before = self.env["facodi.learning.submission"].sudo().search_count([])
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(),
                "name": "Public resource suggestion",
                "source_url": "https://example.org/open-course",
                "context": "Could support an introductory module.",
                "language": "en",
                "state": "accepted",
                "reviewed_by_id": str(self.env.user.id),
            },
        )
        self.assertEqual(response.status_code, 200)

        submissions = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "Public resource suggestion")]
        )
        self.assertEqual(len(submissions), 1)
        submission = submissions
        self.assertEqual(
            self.env["facodi.learning.submission"].sudo().search_count([]),
            before + 1,
        )
        self.assertEqual(submission.state, "submitted")
        self.assertFalse(submission.reviewed_by_id)
        self.assertIn("Submission received", response.text)
        self.assertIn(submission.name, response.text)
        self.assertNotIn("decision_note", response.text)

    def test_invalid_url_is_rejected_without_creating_submission(self):
        before = self.env["facodi.learning.submission"].sudo().search_count([])
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(),
                "name": "Bad resource",
                "source_url": "javascript:alert(1)",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Enter a valid public HTTP or HTTPS URL.", response.text)
        self.assertEqual(
            self.env["facodi.learning.submission"].sudo().search_count([]),
            before,
        )

    def test_metadata_discovery_budget_is_bounded_per_client(self):
        from facodi_learning.controllers import submission as submission_controller

        with submission_controller._metadata_lock:
            submission_controller._metadata_rate.clear()

        for offset in range(submission_controller._METADATA_RATE_PER_CLIENT):
            self.assertTrue(
                submission_controller._consume_metadata_budget(
                    "203.0.113.10",
                    now=1000.0 + offset * 0.01,
                )
            )
        self.assertFalse(
            submission_controller._consume_metadata_budget(
                "203.0.113.10",
                now=1001.0,
            )
        )
        self.assertTrue(
            submission_controller._consume_metadata_budget(
                "203.0.113.11",
                now=1001.0,
            )
        )

    def test_metadata_cache_reuses_discovered_payload(self):
        from facodi_learning.controllers import submission as submission_controller

        with submission_controller._metadata_lock:
            submission_controller._metadata_cache.clear()

        key = "https://www.youtube.com/watch?v=w9gb71ZUJDs"
        payload = {
            "supported": True,
            "provider": "youtube",
            "title": "Pré-Cálculo",
        }
        submission_controller._metadata_cache_set(key, payload, now=1000.0)
        cached = submission_controller._metadata_cache_get(key, now=1001.0)
        self.assertEqual(cached["title"], "Pré-Cálculo")
        cached["title"] = "Changed"
        self.assertEqual(
            submission_controller._metadata_cache_get(key, now=1002.0)["title"],
            "Pré-Cálculo",
        )
        self.assertFalse(
            submission_controller._metadata_cache_get(
                key,
                now=1000.0 + submission_controller._METADATA_CACHE_TTL + 1,
            )
        )

    def test_status_page_requires_exact_private_token(self):
        submission = (
            self.env["facodi.learning.submission"]
            .sudo()
            .create(
                {
                    "name": "Token protected",
                    "source_url": "https://example.org/token-protected",
                }
            )
        )
        ok = self.url_open(
            f"/contribuir/recurso/status/{submission.access_token}"
        )
        self.assertEqual(ok.status_code, 200)
        self.assertIn("Token protected", ok.text)

        missing = self.url_open("/contribuir/recurso/status/not-the-token")
        self.assertEqual(missing.status_code, 404)
