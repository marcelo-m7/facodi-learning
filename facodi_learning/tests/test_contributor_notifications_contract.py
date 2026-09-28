from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]


class TestContributorNotificationContract(unittest.TestCase):
    def test_review_actions_queue_transactional_notifications(self):
        model = (MODULE_ROOT / "models" / "submission.py").read_text(encoding="utf-8")
        self.assertIn("def _contributor_notification_email", model)
        self.assertIn("self.sudo().submitted_by_id", model)
        self.assertIn("def _contributor_tracking_url", model)
        self.assertIn("force_send=False", model)
        self.assertIn("mail_template_submission_changes_requested", model)
        controller = (MODULE_ROOT / "controllers" / "contextual_submission.py").read_text(encoding="utf-8")
        self.assertIn("mail_template_submission_received", controller)
        self.assertIn("mail_template_submission_accepted", model)
        self.assertIn("mail_template_submission_rejected", model)
        self.assertIn("_logger.exception", model)

    def test_templates_never_render_internal_decision_note(self):
        templates = (MODULE_ROOT / "data" / "submission_mail_templates.xml").read_text(encoding="utf-8")
        self.assertNotIn("decision_note", templates)
        self.assertIn("editorial_reply", templates)
        self.assertIn("_contributor_tracking_url()", templates)
        self.assertIn('id="mail_template_submission_received"', templates)
        self.assertIn("Track your contribution", templates)


if __name__ == "__main__":
    unittest.main()
