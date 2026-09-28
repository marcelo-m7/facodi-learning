from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]


class TestContributionRevisionLoopContract(unittest.TestCase):
    def test_revision_state_actions_and_portal_route_stay_connected(self):
        model = (MODULE_ROOT / "models" / "submission.py").read_text(encoding="utf-8")
        contextual_model = (MODULE_ROOT / "models" / "contextual_submission.py").read_text(encoding="utf-8")
        controller = (MODULE_ROOT / "controllers" / "submission.py").read_text(encoding="utf-8")
        website = (MODULE_ROOT / "views" / "website_submission.xml").read_text(encoding="utf-8")
        backoffice = (MODULE_ROOT / "views" / "submission_views.xml").read_text(encoding="utf-8")

        self.assertIn('("changes_requested", "Changes Requested")', model)
        self.assertIn('("state", "in", ("submitted", "reviewing", "changes_requested", "accepted"))', contextual_model)
        self.assertIn("def action_request_changes", model)
        self.assertIn("def action_resubmit_by_contributor", model)
        self.assertIn("/reenviar", controller)
        self.assertIn('data-facodi-revision-request="1"', website)
        self.assertIn('data-facodi-revision-resubmit="1"', website)
        self.assertIn('name="action_request_changes"', backoffice)


if __name__ == "__main__":
    unittest.main()
