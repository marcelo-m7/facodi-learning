import os
from unittest.mock import patch

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

    def test_candidate_ingestion_links_submission_and_analysis_trace(self):
        submission = self._submission(
            name="Pré-Cálculo",
            source_url="https://www.youtube.com/watch?v=w9gb71ZUJDs",
            language="pt",
        )
        submission.action_accept()
        submission.action_handoff_candidate()
        candidate = submission.candidate_id

        channel = self.env["slide.channel"].create(
            {"name": "Submission processing target"}
        )
        candidate.action_evaluate()
        candidate.write({"matched_channel_id": channel.id})
        candidate.action_resolve_existing()

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ):
            source = candidate.action_ingest_source()
            replay = candidate.action_ingest_source()

        submission.invalidate_recordset()
        self.assertEqual(replay, source)
        self.assertEqual(submission.source_id, source)
        self.assertEqual(submission.slide_id, source.slide_id)
        self.assertEqual(submission.source_state, "imported")
        self.assertTrue(submission.analysis_job_id)
        self.assertEqual(submission.analysis_job_id.provider, "supabase_edge")
        self.assertEqual(submission.processing_state, "pending")
        self.assertFalse(submission.analysis_result_id)
        self.assertEqual(
            self.env["facodi.learning.analysis.job"].search_count(
                [
                    ("slide_id", "=", source.slide_id.id),
                    ("provider", "=", "supabase_edge"),
                ]
            ),
            1,
        )

    def test_submission_trace_uses_latest_job_and_is_officer_readable(self):
        submission = self._submission(
            name="Analysis trace resource",
            source_url="https://www.youtube.com/watch?v=w9gb71ZUJDs",
            language="pt",
        )
        submission.action_accept()
        submission.action_handoff_candidate()
        candidate = submission.candidate_id

        channel = self.env["slide.channel"].create(
            {"name": "Analysis trace target"}
        )
        candidate.action_evaluate()
        candidate.write({"matched_channel_id": channel.id})
        candidate.action_resolve_existing()

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ):
            source = candidate.action_ingest_source()

        supabase_job = self.env["facodi.learning.analysis.job"].search(
            [
                ("slide_id", "=", source.slide_id.id),
                ("provider", "=", "supabase_edge"),
            ],
            limit=1,
        )
        local_job = self.env["facodi.learning.analysis.job"].create(
            {
                "slide_id": source.slide_id.id,
                "provider": "local_metadata",
            }
        )

        submission.invalidate_recordset()
        self.assertEqual(submission.analysis_job_id, local_job)
        self.assertNotEqual(submission.analysis_job_id, supabase_job)

        officer = self.env["res.users"].create(
            {
                "name": "Processing Trace Officer",
                "login": "processing-trace-officer",
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
        values = submission.with_user(officer).read(
            [
                "slide_id",
                "source_state",
                "processing_state",
                "analysis_job_id",
            ]
        )[0]
        self.assertEqual(values["source_state"], "imported")
        self.assertEqual(values["processing_state"], "pending")
        self.assertEqual(values["analysis_job_id"][0], local_job.id)
        self.assertEqual(values["slide_id"][0], source.slide_id.id)

    def test_same_canonical_youtube_source_can_link_multiple_submission_candidates(self):
        first = self._submission(
            name="Shared video A",
            source_url=(
                "https://www.youtube.com/watch?v=w9gb71ZUJDs"
                "&list=PLa_2246N48_rlbheR_al4oqeFCP8dHoQR"
            ),
            language="pt",
        )
        second = self._submission(
            name="Shared video B",
            source_url=(
                "https://www.youtube.com/watch?v=w9gb71ZUJDs"
                "&list=PLdifferent123456789"
            ),
            language="pt",
        )
        for submission in (first, second):
            submission.action_accept()
            submission.action_handoff_candidate()

        self.assertNotEqual(first.candidate_id, second.candidate_id)
        channel = self.env["slide.channel"].create(
            {"name": "Shared canonical source target"}
        )
        for candidate in (first.candidate_id, second.candidate_id):
            candidate.action_evaluate()
            candidate.write({"matched_channel_id": channel.id})
            candidate.action_resolve_existing()

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ):
            first_source = first.candidate_id.action_ingest_source()
            second_source = second.candidate_id.action_ingest_source()

        first.invalidate_recordset()
        second.invalidate_recordset()
        self.assertEqual(first_source, second_source)
        self.assertEqual(first.source_id, first_source)
        self.assertEqual(second.source_id, first_source)
        self.assertEqual(first_source.candidate_id, first.candidate_id)
        self.assertNotEqual(first_source.candidate_id, second.candidate_id)
        self.assertEqual(
            self.env["facodi.learning.analysis.job"].search_count(
                [
                    ("slide_id", "=", first_source.slide_id.id),
                    ("provider", "=", "supabase_edge"),
                ]
            ),
            1,
        )

    def test_source_link_rejects_mismatched_canonical_identity(self):
        submission = self._submission(
            name="Identity protected",
            source_url="https://www.youtube.com/watch?v=w9gb71ZUJDs",
            language="pt",
        )
        submission.action_accept()
        submission.action_handoff_candidate()
        candidate = submission.candidate_id
        channel = self.env["slide.channel"].create(
            {"name": "Identity protected target"}
        )
        candidate.action_evaluate()
        candidate.write({"matched_channel_id": channel.id})
        candidate.action_resolve_existing()

        mismatched = self.env["facodi.learning.source"].create(
            {
                "name": "Wrong source",
                "provider": "youtube",
                "external_id": "SNma-fAeMzA",
                "url": "https://www.youtube.com/watch?v=SNma-fAeMzA",
                "channel_id": channel.id,
            }
        )
        with self.assertRaisesRegex(
            ValidationError,
            "Canonical source identity",
        ):
            submission._link_canonical_source(
                mismatched,
                candidate=candidate,
            )

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


    def test_contributor_can_edit_only_own_pending_submission_and_withdraw(self):
        owned = self._submission(
            name="Owned draft",
            source_url="https://example.org/owned",
            submitted_by_id=self.portal.id,
        )
        other = self._submission(
            name="Other draft",
            source_url="https://example.org/other",
            submitted_by_id=self.manager.id,
        )

        owned.action_update_by_contributor(
            self.portal,
            {
                "name": "Updated by contributor",
                "source_url": "https://example.org/owned-updated",
                "context": "Updated context",
                "language": "pt",
            },
        )
        self.assertEqual(owned.name, "Updated by contributor")
        self.assertEqual(owned.language, "pt")

        with self.assertRaises(AccessError):
            other.action_update_by_contributor(
                self.portal,
                {"name": "Forbidden"},
            )

        owned.action_withdraw_by_contributor(self.portal)
        self.assertEqual(owned.state, "withdrawn")
        with self.assertRaises(ValidationError):
            owned.action_update_by_contributor(
                self.portal,
                {"name": "Too late"},
            )

    def test_contributor_cannot_edit_after_review_starts_but_can_withdraw(self):
        submission = self._submission(
            name="Reviewing own submission",
            source_url="https://example.org/reviewing-own",
            submitted_by_id=self.portal.id,
        )
        submission.action_start_review()
        with self.assertRaises(ValidationError):
            submission.action_update_by_contributor(
                self.portal,
                {"name": "Locked"},
            )
        submission.action_withdraw_by_contributor(self.portal)
        self.assertEqual(submission.state, "withdrawn")

@tagged("-at_install", "post_install")
class TestResourceSubmissionWebsite(HttpCase):
    def _csrf_token(self):
        response = self.url_open("/contribuir/recurso")
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        tokens = tree.xpath('//input[@name="csrf_token"]/@value')
        self.assertEqual(len(tokens), 1)
        return tokens[0]

    def _portal_user(self, login):
        return self.env["res.users"].sudo().create(
            {
                "name": login,
                "login": login,
                "password": "facodi-test-pass",
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )

    def test_authenticated_contributor_can_manage_only_own_submissions(self):
        owner = self._portal_user("facodi-contributor-owner")
        stranger = self._portal_user("facodi-contributor-stranger")
        Submission = self.env["facodi.learning.submission"].sudo()
        owned = Submission.create(
            {
                "name": "Owner managed video",
                "source_url": "https://www.youtube.com/watch?v=w9gb71ZUJDs",
                "context": "Owner private context",
                "language": "pt",
                "submitted_by_id": owner.id,
            }
        )
        other = Submission.create(
            {
                "name": "Stranger submission",
                "source_url": "https://www.youtube.com/watch?v=SNma-fAeMzA",
                "submitted_by_id": stranger.id,
            }
        )

        self.authenticate(owner.login, "facodi-test-pass")
        listing = self.url_open("/minhas-contribuicoes")
        self.assertEqual(listing.status_code, 200)
        self.assertIn("Owner managed video", listing.text)
        self.assertNotIn("Stranger submission", listing.text)

        detail = self.url_open(f"/minhas-contribuicoes/{owned.id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Owner private context", detail.text)

        forbidden = self.url_open(f"/minhas-contribuicoes/{other.id}")
        self.assertEqual(forbidden.status_code, 404)

    def test_contributor_can_edit_and_withdraw_pending_submission(self):
        owner = self._portal_user("facodi-contributor-actions")
        submission = (
            self.env["facodi.learning.submission"]
            .sudo()
            .create(
                {
                    "name": "Editable contribution",
                    "source_url": "https://www.youtube.com/watch?v=w9gb71ZUJDs",
                    "context": "Initial context",
                    "language": "pt",
                    "submitted_by_id": owner.id,
                }
            )
        )

        self.authenticate(owner.login, "facodi-test-pass")
        detail = self.url_open(f"/minhas-contribuicoes/{submission.id}")
        token = html.fromstring(detail.text).xpath(
            '//input[@name="csrf_token"]/@value'
        )[0]

        edit = self.url_open(
            f"/minhas-contribuicoes/{submission.id}/editar",
            data={
                "csrf_token": token,
                "name": "Edited contribution",
                "source_url": "https://www.youtube.com/watch?v=w9gb71ZUJDs",
                "context": "Edited private context",
                "language": "en",
            },
        )
        self.assertEqual(edit.status_code, 200)
        submission.invalidate_recordset()
        self.assertEqual(submission.name, "Edited contribution")
        self.assertEqual(submission.language, "en")
        self.assertEqual(submission.context, "Edited private context")

        detail = self.url_open(f"/minhas-contribuicoes/{submission.id}")
        withdraw_tokens = html.fromstring(detail.text).xpath(
            '//form[contains(@action, "/retirar")]//input[@name="csrf_token"]/@value'
        )
        self.assertEqual(len(withdraw_tokens), 1)
        withdrawn = self.url_open(
            f"/minhas-contribuicoes/{submission.id}/retirar",
            data={"csrf_token": withdraw_tokens[0]},
        )
        self.assertEqual(withdrawn.status_code, 200)
        submission.invalidate_recordset()
        self.assertEqual(submission.state, "withdrawn")

        community = self.url_open("/explorar/videos")
        self.assertNotIn("Edited contribution", community.text)

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

    def test_no_javascript_youtube_submission_is_enriched_server_side(self):
        context_marker = "CI no-JavaScript URL-first discovery"
        discovered = {
            "supported": True,
            "provider": "youtube",
            "external_id": "w9gb71ZUJDs",
            "canonical_url": "https://www.youtube.com/watch?v=w9gb71ZUJDs",
            "title": "Pré-Cálculo",
            "language": "pt-BR",
            "author_name": "FACODI Test Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/w9gb71ZUJDs/hqdefault.jpg",
            "duration_seconds": 372,
            "published_at": "2026-01-01",
        }

        with patch(
            "odoo.addons.facodi_learning.controllers.submission."
            "_discover_public_youtube_metadata",
            return_value=discovered,
        ):
            response = self.url_open(
                "/contribuir/recurso",
                data={
                    "csrf_token": self._csrf_token(),
                    "name": "",
                    "source_url": (
                        "https://www.youtube.com/watch?v=w9gb71ZUJDs"
                        "&list=PLa_2246N48_rlbheR_al4oqeFCP8dHoQR"
                    ),
                    "context": context_marker,
                    "language": "",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Submission received", response.text)

        submission = (
            self.env["facodi.learning.submission"]
            .sudo()
            .search([("context", "=", context_marker)], limit=1)
        )
        self.assertTrue(submission)
        self.assertEqual(submission.name, "Pré-Cálculo")
        self.assertEqual(
            submission.source_url,
            "https://www.youtube.com/watch?v=w9gb71ZUJDs",
        )
        self.assertEqual(submission.language, "pt")

    def test_community_video_wall_is_public_before_review_without_private_fields(self):
        Submission = self.env["facodi.learning.submission"].sudo()
        pending = Submission.create(
            {
                "name": "Community pending video",
                "source_url": "https://youtu.be/w9gb71ZUJDs",
                "context": "PRIVATE CONTEXT MUST NOT LEAK",
                "language": "pt",
            }
        )
        rejected = Submission.create(
            {
                "name": "Rejected community video",
                "source_url": "https://www.youtube.com/watch?v=SNma-fAeMzA",
                "language": "en",
            }
        )
        generic = Submission.create(
            {
                "name": "Generic submitted link",
                "source_url": "https://example.org/not-a-video",
                "language": "en",
            }
        )

        manager = self.env.ref("base.user_admin")
        manager_group = self.env.ref("website_slides.group_website_slides_manager")
        if manager_group not in manager.group_ids:
            manager.write({"group_ids": [(4, manager_group.id)]})
        rejected.with_user(manager).action_reject()

        response = self.url_open("/explorar/videos")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Community pending video", response.text)
        self.assertIn("Awaiting review", response.text)
        self.assertIn(
            "https://www.youtube.com/watch?v=w9gb71ZUJDs",
            response.text,
        )
        self.assertNotIn("Rejected community video", response.text)
        self.assertNotIn("Generic submitted link", response.text)
        self.assertNotIn(pending.access_token, response.text)
        self.assertNotIn("PRIVATE CONTEXT MUST NOT LEAK", response.text)

        filtered = self.url_open("/explorar/videos?language=pt&q=Community")
        self.assertEqual(filtered.status_code, 200)
        self.assertIn("Community pending video", filtered.text)
        self.assertNotIn("Rejected community video", filtered.text)

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
        from odoo.addons.facodi_learning.controllers import submission as submission_controller

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
        from odoo.addons.facodi_learning.controllers import submission as submission_controller

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
