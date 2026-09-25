import json
import os
import urllib.error
import urllib.request
from unittest.mock import patch

from odoo.tests import TransactionCase


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


class TestSupabaseEdgeAnalysis(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["slide.channel"].create(
            {"name": "Supabase Analysis Course"}
        )

    def _ingest_youtube(self):
        return self.env["facodi.learning.source"].ingest(
            {
                "provider": "youtube",
                "external_id": "SNma-fAeMzA",
                "name": "FACODI Supabase video",
                "url": "https://www.youtube.com/watch?v=SNma-fAeMzA",
                "channel_id": self.channel.id,
                "metadata": {"description": "Open learning video"},
            }
        )

    def test_imported_source_queues_one_supabase_job_when_runtime_is_configured(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ):
            source = self._ingest_youtube()
            jobs = self.env["facodi.learning.analysis.job"].search(
                [
                    ("slide_id", "=", source.slide_id.id),
                    ("provider", "=", "supabase_edge"),
                ]
            )
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs.state, "pending")

            replay = self._ingest_youtube()
            self.assertEqual(replay, source)
            self.assertEqual(
                self.env["facodi.learning.analysis.job"].search_count(
                    [
                        ("slide_id", "=", source.slide_id.id),
                        ("provider", "=", "supabase_edge"),
                    ]
                ),
                1,
            )

    def test_supabase_provider_records_normalized_result(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
                "GEMINI_API_KEY": "gemini-test-secret",
            },
            clear=False,
        ):
            source = self._ingest_youtube()
            job = self.env["facodi.learning.analysis.job"].search(
                [
                    ("slide_id", "=", source.slide_id.id),
                    ("provider", "=", "supabase_edge"),
                ],
                limit=1,
            )
            self.assertTrue(job)

            response_payload = {
                "success": True,
                "job_id": "11111111-1111-1111-1111-111111111111",
                "status": "needs_review",
                "odoo_payload": {
                    "summary": "Introdução ao pré-cálculo.",
                    "transcript": "",
                    "detected_language": "pt",
                    "suggested_tag_ids": [],
                    "suggested_tags": ["Pré-cálculo", "Matemática"],
                    "proposed_mappings": [],
                    "model_name": "gemini-test-model",
                    "raw_payload": {
                        "source": "supabase_edge",
                        "processing_job_id": "11111111-1111-1111-1111-111111111111",
                        "idempotency_key": f"odoo-analysis-job-{job.id}",
                        "prompt_version": "facodi-learning-resource-v1",
                    },
                },
            }

            captured = {}

            def fake_urlopen(request, timeout=0):
                captured["request"] = request
                captured["timeout"] = timeout
                return _FakeResponse(response_payload)

            with patch(
                "facodi_learning.services.supabase_edge._open_endpoint",
                side_effect=fake_urlopen,
            ):
                job.action_process()

            self.assertEqual(job.state, "completed")
            self.assertEqual(job.result_id.provider, "supabase_edge")
            self.assertEqual(job.result_id.model_name, "gemini-test-model")
            self.assertEqual(job.result_id.detected_language, "pt")
            self.assertEqual(
                job.result_id.suggested_tags,
                ["Pré-cálculo", "Matemática"],
            )
            self.assertEqual(
                job.result_id.raw_payload["source"],
                "supabase_edge",
            )

            request = captured["request"]
            sent = json.loads(request.data.decode("utf-8"))
            self.assertEqual(
                sent["idempotency_key"],
                f"odoo-analysis-job-{job.id}",
            )
            self.assertEqual(sent["odoo"]["slide_id"], source.slide_id.id)
            self.assertEqual(captured["timeout"], 60)
            self.assertEqual(request.get_header("Apikey"), "sb_secret_test")
            self.assertEqual(
                request.get_header("X-facodi-gemini-key"),
                "gemini-test-secret",
            )


    def test_metadata_discovery_uses_dedicated_supabase_function(self):
        from facodi_learning.services.supabase_edge import discover_resource_metadata

        response_payload = {
            "success": True,
            "metadata": {
                "provider": "youtube",
                "external_id": "w9gb71ZUJDs",
                "canonical_url": "https://www.youtube.com/watch?v=w9gb71ZUJDs",
                "title": "Introdução à Pré-Cálculo",
                "author_name": "Canal Exemplo",
                "author_url": "https://www.youtube.com/@exemplo",
                "thumbnail_url": "https://i.ytimg.com/vi/w9gb71ZUJDs/hqdefault.jpg",
                "duration_seconds": 754,
                "published_at": "2026-01-12",
                "language": "pt-BR",
                "metadata_source": "youtube_public",
            },
        }
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse(response_payload)

        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SECRET_KEY": "sb_secret_test",
                },
                clear=False,
            ),
            patch(
                "facodi_learning.services.supabase_edge._open_endpoint",
                side_effect=fake_urlopen,
            ),
        ):
            metadata = discover_resource_metadata(
                "https://www.youtube.com/watch?v=w9gb71ZUJDs&list=playlist"
            )

        self.assertEqual(metadata["provider"], "youtube")
        self.assertEqual(metadata["external_id"], "w9gb71ZUJDs")
        self.assertEqual(metadata["language"], "pt-BR")
        self.assertEqual(metadata["duration_seconds"], 754)
        self.assertEqual(
            metadata["canonical_url"],
            "https://www.youtube.com/watch?v=w9gb71ZUJDs",
        )

        request = captured["request"]
        self.assertTrue(
            request.full_url.endswith(
                "/functions/v1/v3_discover_resource_metadata"
            )
        )
        self.assertEqual(request.get_header("Apikey"), "sb_secret_test")
        self.assertIsNone(request.get_header("X-facodi-gemini-key"))
        self.assertEqual(captured["timeout"], 15)
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "source_url": (
                    "https://www.youtube.com/watch?v=w9gb71ZUJDs&list=playlist"
                )
            },
        )

    def test_metadata_discovery_rejects_unbounded_duration(self):
        from facodi_learning.services.supabase_edge import discover_resource_metadata

        response_payload = {
            "success": True,
            "metadata": {
                "provider": "youtube",
                "canonical_url": "https://www.youtube.com/watch?v=w9gb71ZUJDs",
                "duration_seconds": 999999999,
            },
        }

        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SECRET_KEY": "sb_secret_test",
                },
                clear=False,
            ),
            patch(
                "facodi_learning.services.supabase_edge._open_endpoint",
                return_value=_FakeResponse(response_payload),
            ),
        ):
            metadata = discover_resource_metadata(
                "https://www.youtube.com/watch?v=w9gb71ZUJDs"
            )

        self.assertFalse(metadata["duration_seconds"])

    def test_url_less_manual_article_is_not_queued_for_supabase(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ):
            source = self.env["facodi.learning.source"].ingest_manual(
                {
                    "provider": "manual",
                    "external_id": "manual-no-url",
                    "name": "Editorial article without external source",
                    "channel_id": self.channel.id,
                }
            )
            self.assertTrue(source.slide_id)
            self.assertFalse(source.slide_id.url)
            self.assertFalse(source.url)
            self.assertFalse(
                self.env["facodi.learning.analysis.job"].search(
                    [
                        ("slide_id", "=", source.slide_id.id),
                        ("provider", "=", "supabase_edge"),
                    ],
                    limit=1,
                )
            )

    def test_manual_source_url_is_used_when_article_has_no_slide_url(self):
        from facodi_learning.services.supabase_edge import _source_url_for_slide

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ):
            source = self.env["facodi.learning.source"].ingest_manual(
                {
                    "provider": "manual",
                    "external_id": "manual-with-url",
                    "name": "Editorial article with provenance",
                    "url": "https://example.org/open-resource",
                    "channel_id": self.channel.id,
                }
            )
            self.assertFalse(source.slide_id.url)
            self.assertEqual(
                _source_url_for_slide(source.slide_id),
                "https://example.org/open-resource",
            )
            job = self.env["facodi.learning.analysis.job"].search(
                [
                    ("slide_id", "=", source.slide_id.id),
                    ("provider", "=", "supabase_edge"),
                ],
                limit=1,
            )
            self.assertTrue(job)

    def test_supabase_endpoint_rejects_non_https_origin(self):
        from facodi_learning.services.supabase_edge import _analysis_endpoint

        with patch.dict(
            os.environ,
            {"SUPABASE_URL": "http://example.supabase.co"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "HTTPS origin"):
                _analysis_endpoint()

    def test_supabase_redirect_handler_never_forwards_credentials(self):
        from facodi_learning.services.supabase_edge import _RejectRedirects

        handler = _RejectRedirects()
        request = urllib.request.Request(
            "https://example.supabase.co/functions/v1/test",
            headers={
                "apikey": "sb_secret_test",
                "x-facodi-gemini-key": "gemini-test-secret",
            },
        )
        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://attacker.invalid/collect",
            )

    def test_supabase_response_must_match_requested_idempotency_key(self):
        from facodi_learning.services.supabase_edge import _validate_response_correlation

        payload = {
            "success": True,
            "job_id": "11111111-1111-1111-1111-111111111111",
            "status": "needs_review",
            "odoo_payload": {
                "raw_payload": {
                    "source": "supabase_edge",
                    "processing_job_id": "11111111-1111-1111-1111-111111111111",
                    "idempotency_key": "odoo-analysis-job-other",
                }
            },
        }
        with self.assertRaisesRegex(ValueError, "idempotency correlation"):
            _validate_response_correlation(
                payload,
                "odoo-analysis-job-123",
            )
