import json
from unittest.mock import patch

from lxml import html

from odoo.tests import HttpCase, tagged

from facodi_learning.controllers import submission as submission_controller


@tagged("-at_install", "post_install")
class TestResourceSubmissionMetadataHttp(HttpCase):
    route = "/contribuir/recurso/metadata"

    def setUp(self):
        super().setUp()
        with submission_controller._METADATA_CACHE_LOCK:
            submission_controller._METADATA_CACHE.clear()

    def _csrf_token(self):
        response = self.url_open("/contribuir/recurso")
        self.assertEqual(response.status_code, 200)
        tokens = html.fromstring(response.content).xpath(
            '//input[@name="csrf_token"]/@value'
        )
        self.assertTrue(tokens)
        return tokens[0]

    def _post(self, source_url, *, csrf=True):
        data = {"source_url": source_url}
        if csrf:
            data["csrf_token"] = self._csrf_token()
        return self.url_open(
            self.route,
            data=data,
            allow_redirects=False,
        )

    def test_metadata_endpoint_rejects_invalid_url(self):
        with patch.object(
            submission_controller,
            "_METADATA_MIN_INTERVAL_SECONDS",
            0,
        ):
            response = self._post("javascript:alert(1)")

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])

    def test_metadata_endpoint_requires_csrf(self):
        # Establish a public session, then deliberately omit the token.
        self.url_open("/contribuir/recurso")
        response = self.url_open(
            self.route,
            data={"source_url": "https://example.org/resource"},
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("CSRF", response.text.upper())

    def test_metadata_endpoint_returns_sanitized_success_and_caches(self):
        metadata = {
            "provider": "youtube",
            "external_id": "w9gb71ZUJDs",
            "canonical_url": "https://www.youtube.com/watch?v=w9gb71ZUJDs",
            "title": "Pré-Cálculo",
            "author_name": "Canal Exemplo",
            "thumbnail_url": "https://i.ytimg.com/vi/w9gb71ZUJDs/hqdefault.jpg",
            "duration_seconds": 754,
            "published_at": "2026-01-12",
            "language": "pt-BR",
        }
        source_url = (
            "https://www.youtube.com/watch?v=w9gb71ZUJDs&list=playlist"
        )

        with (
            patch.object(
                submission_controller,
                "_METADATA_MIN_INTERVAL_SECONDS",
                60,
            ),
            patch.object(
                submission_controller,
                "discover_resource_metadata",
                return_value=metadata,
            ) as discover,
        ):
            first = self._post(source_url)
            second = self._post(source_url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        payload = first.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["metadata"]["language"], "pt")
        self.assertEqual(
            payload["metadata"]["canonical_url"],
            "https://www.youtube.com/watch?v=w9gb71ZUJDs",
        )
        self.assertEqual(payload["metadata"]["title"], "Pré-Cálculo")
        self.assertEqual(discover.call_count, 1)

    def test_canonical_url_alone_counts_as_available(self):
        with (
            patch.object(
                submission_controller,
                "_METADATA_MIN_INTERVAL_SECONDS",
                0,
            ),
            patch.object(
                submission_controller,
                "discover_resource_metadata",
                return_value={
                    "provider": "youtube",
                    "canonical_url": (
                        "https://www.youtube.com/watch?v=w9gb71ZUJDs"
                    ),
                },
            ),
        ):
            response = self._post(
                "https://www.youtube.com/watch?v=w9gb71ZUJDs&list=playlist"
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["available"])

    def test_metadata_endpoint_falls_back_without_blocking_submission(self):
        with (
            patch.object(
                submission_controller,
                "_METADATA_MIN_INTERVAL_SECONDS",
                0,
            ),
            patch.object(
                submission_controller,
                "discover_resource_metadata",
                side_effect=ValueError("provider unavailable"),
            ),
        ):
            response = self._post("https://example.org/open-resource")

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertNotIn("provider unavailable", json.dumps(payload))

    def test_metadata_endpoint_throttles_distinct_cache_misses(self):
        with (
            patch.object(
                submission_controller,
                "_METADATA_MIN_INTERVAL_SECONDS",
                60,
            ),
            patch.object(
                submission_controller,
                "discover_resource_metadata",
                return_value={
                    "provider": "generic",
                    "canonical_url": "https://example.org/one",
                },
            ) as discover,
        ):
            token = self._csrf_token()
            first = self.url_open(
                self.route,
                data={
                    "csrf_token": token,
                    "source_url": "https://example.org/one",
                },
                allow_redirects=False,
            )
            second = self.url_open(
                self.route,
                data={
                    "csrf_token": token,
                    "source_url": "https://example.org/two",
                },
                allow_redirects=False,
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.headers.get("Retry-After"), "2")
        self.assertEqual(discover.call_count, 1)
