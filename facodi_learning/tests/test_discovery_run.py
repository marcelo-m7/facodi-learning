from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase


class TestDiscoveryRun(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Discovery Manager",
                "login": "discovery-manager",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("website_slides.group_website_slides_manager").id,
                        ]
                    )
                ],
            }
        )
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Discovery Officer",
                "login": "discovery-officer",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("website_slides.group_website_slides_officer").id,
                        ]
                    )
                ],
            }
        )
        cls.portal = cls.env["res.users"].create(
            {
                "name": "Discovery Portal",
                "login": "discovery-portal",
                "group_ids": [Command.set([cls.env.ref("base.group_portal").id])],
            }
        )
        cls.public = cls.env.ref("base.public_user")

    def test_discovery_run_model_and_registry_exist(self):
        Run = self.env["facodi.learning.discovery.run"]
        registry = Run._get_course_discovery_registry()
        self.assertIn("manual", registry)
        self.assertTrue(callable(registry["manual"]))

    def test_manual_provider_completes_empty_run(self):
        run = self.env["facodi.learning.discovery.run"].with_user(self.manager).create(
            {"provider": "manual"}
        )
        run.action_process()
        self.assertEqual(run.state, "completed")
        self.assertEqual(run.items_seen, 0)
        self.assertEqual(run.candidates_created, 0)
        self.assertEqual(run.candidates_refreshed, 0)
        self.assertEqual(run.candidates_ignored, 0)
        self.assertTrue(run.started_at)
        self.assertTrue(run.completed_at)
        self.assertFalse(run.last_error)

    def test_unknown_provider_is_recorded_as_failed(self):
        run = self.env["facodi.learning.discovery.run"].with_user(self.manager).create(
            {"provider": "missing-provider"}
        )
        run.action_process()
        self.assertEqual(run.state, "failed")
        self.assertIn("provider", (run.last_error or "").lower())
        self.assertNotIn("Traceback", run.last_error or "")

    def test_officer_cannot_create_or_process_discovery_run(self):
        Run = self.env["facodi.learning.discovery.run"].with_user(self.officer)
        with self.assertRaises(AccessError):
            Run.create({"provider": "manual"})

    def test_public_and_portal_cannot_read_discovery_runs(self):
        run = self.env["facodi.learning.discovery.run"].with_user(self.manager).create(
            {"provider": "manual"}
        )
        for user in (self.public, self.portal):
            with self.assertRaises(AccessError):
                run.with_user(user).check_access("read")
