from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]


class TestContributionJourneyContract(unittest.TestCase):
    def test_private_status_and_manage_views_expose_journey(self):
        source = (MODULE_ROOT / "views" / "website_submission.xml").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count('data-facodi-contribution-journey="1"'), 2)
        for label in ("Contribution journey", "Review desk", "Decision", "Community route"):
            self.assertIn(label, source)
        for state in ("submitted", "reviewing", "accepted", "resolved", "rejected", "withdrawn"):
            self.assertIn(state, source)


if __name__ == "__main__":
    unittest.main()
