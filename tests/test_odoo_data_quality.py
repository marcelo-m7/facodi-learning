import ast
import csv
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "facodi_learning"
MANIFEST = ast.literal_eval((ADDON / "__manifest__.py").read_text(encoding="utf-8"))
EXTERNAL_ID_TAGS = {"record", "template", "menuitem"}


class OdooDataQualityTest(unittest.TestCase):
    def test_manifest_data_files_exist_and_are_unique(self):
        paths = [*MANIFEST.get("data", []), *MANIFEST.get("demo", [])]
        duplicates = sorted(path for path, count in Counter(paths).items() if count > 1)
        self.assertFalse(duplicates, f"duplicate manifest data entries: {duplicates}")
        missing = sorted(path for path in paths if not (ADDON / path).is_file())
        self.assertFalse(missing, f"manifest references missing data files: {missing}")

    def test_manifest_xml_is_well_formed_and_has_no_duplicate_external_ids(self):
        for relative_path in [*MANIFEST.get("data", []), *MANIFEST.get("demo", [])]:
            if not relative_path.endswith(".xml"):
                continue
            path = ADDON / relative_path
            with self.subTest(path=relative_path):
                root = ET.parse(path).getroot()
                external_ids = [
                    element.attrib["id"]
                    for element in root.iter()
                    if element.tag in EXTERNAL_ID_TAGS and element.attrib.get("id")
                ]
                duplicates = sorted(
                    external_id
                    for external_id, count in Counter(external_ids).items()
                    if count > 1
                )
                self.assertFalse(
                    duplicates,
                    f"{relative_path} declares duplicate external IDs: {duplicates}",
                )

    def test_curriculum_verification_documentation_matches_runtime(self):
        validation = (ROOT / "docs" / "validation.md").read_text(encoding="utf-8")
        source = (
            ADDON / "models" / "curriculum_source.py"
        ).read_text(encoding="utf-8")

        self.assertIn("def _cron_verify_enabled_sources", source)
        self.assertIn("def action_verify_now", source)
        self.assertIn("explicitly opted in", validation)
        self.assertIn("changed sources create a new private", validation)
        self.assertNotIn(
            "No live curriculum scraper, scheduled sync or AI matcher is bundled",
            validation,
        )

    def test_github_actions_are_commit_pinned(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        for expected in (
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        ):
            self.assertIn(expected, workflow)
        self.assertNotIn("actions/checkout@v4", workflow)
        self.assertNotIn("actions/upload-artifact@v4", workflow)

    def test_access_control_csv_has_unique_external_ids(self):
        path = ADDON / "security" / "ir.model.access.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        external_ids = [row["id"] for row in rows if row.get("id")]
        duplicates = sorted(
            external_id
            for external_id, count in Counter(external_ids).items()
            if count > 1
        )
        self.assertFalse(duplicates, f"duplicate ACL external IDs: {duplicates}")


if __name__ == "__main__":
    unittest.main()
