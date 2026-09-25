import io
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

    def read(self, size=-1):
        return self._payload if size is None or size < 0 else self._payload[:size]


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


    def test_resource_metadata_discovery_uses_dedicated_edge_function(self):
        from facodi_learning.services.supabase_edge import (
            discover_supabase_resource_metadata,
        )

        response_payload = {
            "success": True,
            "metadata": {
                "provider": "youtube",
                "external_id": "w9gb71ZUJDs",
                "canonical_url": "https://www.youtube.com/watch?v=w9gb71ZUJDs",
                "title": "Pré-Cálculo",
                "author_name": "Canal FACODI",
                "thumbnail_url": "https://i.ytimg.com/vi/w9gb71ZUJDs/hqdefault.jpg",
                "duration_seconds": 372,
                "published_at": "2026-01-01",
                "language": "pt-BR",
                "metadata_source": "youtube_public",
            },
        }
        captured = {}

        def fake_open(request, timeout=0):
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeResponse(response_payload)

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ), patch(
            "facodi_learning.services.supabase_edge._open_endpoint",
            side_effect=fake_open,
        ):
            metadata = discover_supabase_resource_metadata(
                "https://www.youtube.com/watch?v=w9gb71ZUJDs&list=playlist"
            )

        self.assertTrue(metadata["supported"])
        self.assertEqual(metadata["provider"], "youtube")
        self.assertEqual(metadata["title"], "Pré-Cálculo")
        self.assertEqual(metadata["language"], "pt-BR")
        self.assertEqual(
            metadata["canonical_url"],
            "https://www.youtube.com/watch?v=w9gb71ZUJDs",
        )
        self.assertEqual(captured["timeout"], 15)
        request = captured["request"]
        self.assertEqual(request.get_header("Apikey"), "sb_secret_test")
        self.assertTrue(
            request.full_url.endswith(
                "/functions/v1/v3_discover_resource_metadata"
            )
        )
        self.assertEqual(
            json.loads(request.data.decode("utf-8"))["source_url"],
            "https://www.youtube.com/watch?v=w9gb71ZUJDs&list=playlist",
        )

    def test_resource_metadata_discovery_does_not_promote_generic_provider(self):
        from facodi_learning.services.supabase_edge import (
            discover_supabase_resource_metadata,
        )

        response_payload = {
            "success": True,
            "metadata": {
                "provider": "generic",
                "external_id": None,
                "canonical_url": "https://example.org/resource",
                "title": None,
                "author_name": None,
                "thumbnail_url": None,
                "duration_seconds": None,
                "published_at": None,
                "language": None,
                "metadata_source": "odoo_submission",
            },
        }

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
            },
            clear=False,
        ), patch(
            "facodi_learning.services.supabase_edge._open_endpoint",
            return_value=_FakeResponse(response_payload),
        ):
            metadata = discover_supabase_resource_metadata(
                "https://example.org/resource"
            )

        self.assertFalse(metadata["supported"])
        self.assertEqual(metadata["provider"], "generic")


    def test_metadata_response_read_is_bounded(self):
        from facodi_learning.services.supabase_edge import (
            MAX_METADATA_RESPONSE_BYTES,
            _read_bounded_response,
        )

        oversized = _FakeResponse(
            {"padding": "x" * (MAX_METADATA_RESPONSE_BYTES + 1024)}
        )
        with self.assertRaisesRegex(ValueError, "size limit"):
            _read_bounded_response(oversized, MAX_METADATA_RESPONSE_BYTES)


    def test_supabase_failure_records_only_safe_processing_correlation(self):
        correlation_id = "11111111-1111-1111-1111-111111111111"
        edge_body = {
            "success": False,
            "error": "gemini_failed",
            "message": "Learning-resource analysis failed.",
            "details": {
                "processing_job_id": correlation_id,
                "provider_secret": "must-not-enter-odoo",
            },
        }

        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_test",
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
            http_error = urllib.error.HTTPError(
                "https://example.supabase.co/functions/v1/v3_analyze_learning_resource",
                424,
                "Failed Dependency",
                {},
                io.BytesIO(json.dumps(edge_body).encode("utf-8")),
            )

            with patch(
                "facodi_learning.services.supabase_edge._open_endpoint",
                side_effect=http_error,
            ):
                job.action_process()

            self.assertEqual(job.state, "failed")
            self.assertIn(f"Correlation: {correlation_id}.", job.last_error)
            self.assertNotIn("gemini_failed", job.last_error)
            self.assertNotIn("must-not-enter-odoo", job.last_error)
            self.assertNotIn("Learning-resource analysis failed", job.last_error)
            self.assertEqual(len(job.attempt_ids), 1)
            self.assertIn(correlation_id, job.attempt_ids.error)
            self.assertNotIn("must-not-enter-odoo", job.attempt_ids.error)

    def test_invalid_supabase_failure_correlation_is_ignored(self):
        from facodi_learning.services.supabase_edge import (
            _safe_processing_correlation,
        )

        body = {
            "details": {
                "processing_job_id": "not-a-uuid",
            },
        }
        error = urllib.error.HTTPError(
            "https://example.supabase.co/functions/v1/v3_analyze_learning_resource",
            500,
            "Server Error",
            {},
            io.BytesIO(json.dumps(body).encode("utf-8")),
        )
        self.assertFalse(_safe_processing_correlation(error))

    def test_supabase_failure_correlation_body_is_bounded(self):
        from facodi_learning.services.supabase_edge import (
            MAX_ERROR_RESPONSE_BYTES,
            _safe_processing_correlation,
        )

        error = urllib.error.HTTPError(
            "https://example.supabase.co/functions/v1/v3_analyze_learning_resource",
            500,
            "Server Error",
            {},
            io.BytesIO(b"x" * (MAX_ERROR_RESPONSE_BYTES + 1)),
        )
        self.assertFalse(_safe_processing_correlation(error))


    def test_analysis_audit_revalidates_extension_correlation(self):
        from facodi_learning.models.analysis_job import _validated_correlation_id

        class ProviderFailure(ValueError):
            correlation_id = "secret-shaped-provider-detail"

        self.assertFalse(_validated_correlation_id(ProviderFailure("boom")))

        class ValidProviderFailure(ValueError):
            correlation_id = "11111111-1111-1111-1111-111111111111"

        self.assertEqual(
            _validated_correlation_id(ValidProviderFailure("boom")),
            "11111111-1111-1111-1111-111111111111",
        )
