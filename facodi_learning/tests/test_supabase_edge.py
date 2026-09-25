import json
import os
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
                "facodi_learning.services.supabase_edge.urllib.request.urlopen",
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
