from pathlib import Path
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
LOCALES = ("pt.po", "es.po", "fr.po")
KEYS = (
    "Find your next useful tab.",
    "That shelf is empty. The campus isn't.",
    "See the path. Spot the gaps.",
    "Help fill this stop →",
    "Your route through this UC",
    "Community margin",
)


class TestRecentUiI18nContract(unittest.TestCase):
    def test_recent_campus_copy_is_translated(self):
        for locale in LOCALES:
            source = (MODULE_ROOT / "i18n" / locale).read_text(encoding="utf-8")
            for key in KEYS:
                marker = f'msgid "{key}"'
                self.assertIn(marker, source, f"{locale}: {key}")
                block = source.split(marker, 1)[1].split("\n\n", 1)[0]
                self.assertRegex(block, r'msgstr ".+"', f"{locale}: {key}")


if __name__ == "__main__":
    unittest.main()
