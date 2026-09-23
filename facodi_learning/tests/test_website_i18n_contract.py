from pathlib import Path
import unittest


MODULE_ROOT = Path(__file__).resolve().parents[1]
WEBSITE_TEMPLATE = MODULE_ROOT / "views" / "website_curriculum.xml"
I18N_DIR = MODULE_ROOT / "i18n"


class TestWebsiteI18nContract(unittest.TestCase):
    def test_public_roadmap_copy_uses_english_source_strings(self):
        template = WEBSITE_TEMPLATE.read_text()

        self.assertIn("Apply filters", template)
        self.assertIn("Official curriculum alignment", template)
        self.assertNotIn("Aplicar filtros", template)
        self.assertNotIn("Ligação a currículos oficiais", template)

    def test_public_roadmap_catalogues_cover_supported_languages(self):
        expected_translations = {
            "pt": {
                "Apply filters": "Aplicar filtros",
                "Official curriculum alignment": "Ligação a currículos oficiais",
            },
            "es": {
                "Apply filters": "Aplicar filtros",
                "Official curriculum alignment": "Vinculación con planes de estudio oficiales",
            },
            "fr": {
                "Apply filters": "Appliquer les filtres",
                "Official curriculum alignment": "Correspondance avec les cursus officiels",
            },
        }

        for language, translations in expected_translations.items():
            catalogue = (I18N_DIR / f"{language}.po").read_text()
            for source, translated in translations.items():
                self.assertIn(f'msgid "{source}"', catalogue)
                self.assertIn(f'msgstr "{translated}"', catalogue)


if __name__ == "__main__":
    unittest.main()