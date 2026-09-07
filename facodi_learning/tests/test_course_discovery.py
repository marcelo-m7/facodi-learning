import importlib
import importlib.util

from odoo.tests import TransactionCase


class TestCourseDiscoveryCoreContract(TransactionCase):
    @classmethod
    def _discovery_service(cls):
        module_name = "odoo.addons.facodi_learning.services.course_discovery"
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return None
        return importlib.import_module(module_name)

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
