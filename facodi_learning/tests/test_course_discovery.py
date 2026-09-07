import importlib
import importlib.util
from unittest.mock import patch

from odoo.tests import TransactionCase


class TestCourseDiscoveryCoreContract(TransactionCase):
    @classmethod
    def _discovery_service(cls):
        module_name = "odoo.addons.facodi_learning.services.course_discovery"
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return None
        return importlib.import_module(module_name)

    def _process_with_provider(self, items, provider="fixture"):
        Run = self.env["facodi.learning.discovery.run"]
        run = Run.create({"provider": provider})

        def fixture_provider(_run, limit):
            if callable(items):
                return items(_run, limit)
            return list(items)[:limit]

        with patch.object(
            type(Run),
            "_get_course_discovery_registry",
            lambda records: {provider: fixture_provider, "manual": lambda _r, _l: []},
        ):
            run.action_process()
        run.invalidate_recordset()
        return run

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_learning.course_selection_mode", "manual"
        )

    def test_discovery_run_model_is_registered(self):
        self.assertIn("facodi.learning.discovery.run", self.env.registry.models)

    def test_discovery_service_is_available(self):
        service = self._discovery_service()
        self.assertIsNotNone(service)
        self.assertTrue(hasattr(service, "normalize_discovery_item"))

    def test_manual_provider_is_available_offline(self):
        self.assertIn("facodi.learning.discovery.run", self.env.registry.models)
        registry = self.env["facodi.learning.discovery.run"]._get_course_discovery_registry()
        self.assertIn("manual", registry)
        self.assertEqual(
            list(registry["manual"](self.env["facodi.learning.discovery.run"], 10)),
            [],
        )

    def test_normalizer_strips_secret_metadata_recursively(self):
        service = self._discovery_service()
        self.assertIsNotNone(service)
        normalized = service.normalize_discovery_item(
            "youtube",
            {
                "external_id": "playlist:abc",
                "name": "Database Systems",
                "duration_minutes": 120,
                "metadata": {
                    "playlist_id": "abc",
                    "token": "top-secret",
                    "nested": {
                        "Authorization": "Bearer hidden",
                        "safe": "kept",
                        "api_key": "hidden-key",
                    },
                },
            },
        )
        self.assertEqual(normalized["provider"], "youtube")
        self.assertEqual(normalized["external_id"], "playlist:abc")
        self.assertNotIn("token", normalized["metadata"])
        self.assertEqual(normalized["metadata"]["nested"], {"safe": "kept"})

    def test_normalizer_rejects_blank_identity_and_negative_duration(self):
        service = self._discovery_service()
        self.assertIsNotNone(service)
        for item in (
            {"external_id": "", "name": "Course"},
            {"external_id": "course:1", "name": "   "},
            {"external_id": "course:1", "name": "Course", "duration_minutes": -1},
        ):
            with self.assertRaises(ValueError):
                service.normalize_discovery_item("manual", item)

    def test_run_creation_does_not_accept_processing_evidence(self):
        self.assertIn("facodi.learning.discovery.run", self.env.registry.models)
        Run = self.env["facodi.learning.discovery.run"]
        with self.assertRaises(Exception):
            Run.create(
                {
                    "provider": "manual",
                    "state": "completed",
                    "items_seen": 99,
                    "last_error": "forged",
                }
            )

    def test_process_creates_and_evaluates_candidate_without_creating_course(self):
        before_channels = self.env["slide.channel"].search_count([])
        run = self._process_with_provider(
            [
                {
                    "external_id": "course:db1",
                    "name": "Database Systems",
                    "description": "Relational database foundations",
                    "institution": "Example University",
                    "language": "en",
                    "duration_minutes": 180,
                    "metadata": {"catalogue_id": "db1"},
                }
            ]
        )
        candidate = self.env["facodi.learning.course.candidate"].search(
            [("provider", "=", "fixture"), ("external_id", "=", "course:db1")]
        )
        self.assertEqual(len(candidate), 1)
        self.assertEqual(candidate.state, "evaluated")
        self.assertTrue(candidate.evaluated_at)
        self.assertTrue(candidate.discovered_at)
        self.assertTrue(candidate.last_discovered_at)
        self.assertEqual(candidate.last_discovery_run_id, run)
        self.assertEqual(run.state, "completed")
        self.assertEqual(run.items_seen, 1)
        self.assertEqual(run.candidates_created, 1)
        self.assertEqual(run.candidates_refreshed, 0)
        self.assertEqual(run.candidates_ignored, 0)
        self.assertEqual(self.env["slide.channel"].search_count([]), before_channels)

    def test_replay_refreshes_same_candidate_and_reevaluates(self):
        first = self._process_with_provider(
            [{"external_id": "course:refresh", "name": "Old Course"}]
        )
        candidate = self.env["facodi.learning.course.candidate"].search(
            [("provider", "=", "fixture"), ("external_id", "=", "course:refresh")]
        )
        candidate_id = candidate.id
        discovered_at = candidate.discovered_at
        self.assertEqual(first.candidates_created, 1)

        second = self._process_with_provider(
            [
                {
                    "external_id": "course:refresh",
                    "name": "Updated Course",
                    "description": "Now with richer metadata",
                    "institution": "Example University",
                }
            ]
        )
        candidate.invalidate_recordset()
        self.assertEqual(candidate.id, candidate_id)
        self.assertEqual(candidate.name, "Updated Course")
        self.assertEqual(candidate.state, "evaluated")
        self.assertTrue(candidate.evaluated_at)
        self.assertEqual(candidate.discovered_at, discovered_at)
        self.assertEqual(candidate.last_discovery_run_id, second)
        self.assertEqual(second.candidates_created, 0)
        self.assertEqual(second.candidates_refreshed, 1)
        self.assertEqual(
            self.env["facodi.learning.course.candidate"].search_count(
                [("provider", "=", "fixture"), ("external_id", "=", "course:refresh")]
            ),
            1,
        )

    def test_terminal_candidate_is_ignored_without_metadata_rewrite(self):
        first = self._process_with_provider(
            [{"external_id": "course:terminal", "name": "Reviewed Course"}]
        )
        candidate = self.env["facodi.learning.course.candidate"].search(
            [("provider", "=", "fixture"), ("external_id", "=", "course:terminal")]
        )
        self.assertEqual(first.candidates_created, 1)
        candidate.action_reject()

        second = self._process_with_provider(
            [{"external_id": "course:terminal", "name": "Silently Rewritten"}]
        )
        candidate.invalidate_recordset()
        self.assertEqual(candidate.state, "rejected")
        self.assertEqual(candidate.name, "Reviewed Course")
        self.assertEqual(second.candidates_created, 0)
        self.assertEqual(second.candidates_refreshed, 0)
        self.assertEqual(second.candidates_ignored, 1)

    def test_invalid_item_is_ignored_without_blocking_valid_item(self):
        run = self._process_with_provider(
            [
                {"external_id": "", "name": "Invalid"},
                {"external_id": "course:valid", "name": "Valid Course"},
            ]
        )
        self.assertEqual(run.state, "completed")
        self.assertEqual(run.items_seen, 2)
        self.assertEqual(run.candidates_created, 1)
        self.assertEqual(run.candidates_ignored, 1)

    def test_provider_failure_rolls_back_candidate_mutations_and_sanitizes_error(self):
        def failing_provider(_run, _limit):
            yield {"external_id": "course:partial", "name": "Partial Course"}
            raise RuntimeError("Authorization token=super-secret")

        run = self._process_with_provider(failing_provider)
        self.assertEqual(run.state, "failed")
        self.assertFalse(
            self.env["facodi.learning.course.candidate"].search(
                [("provider", "=", "fixture"), ("external_id", "=", "course:partial")]
            )
        )
        self.assertNotIn("super-secret", run.last_error or "")
        self.assertNotIn("Authorization", run.last_error or "")
