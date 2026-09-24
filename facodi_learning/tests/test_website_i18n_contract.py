from pathlib import Path
import unittest


MODULE_ROOT = Path(__file__).resolve().parents[1]
WEBSITE_TEMPLATE = MODULE_ROOT / "views" / "website_curriculum.xml"
SUBMISSION_TEMPLATE = MODULE_ROOT / "views" / "website_submission.xml"
I18N_DIR = MODULE_ROOT / "i18n"


class TestWebsiteI18nContract(unittest.TestCase):
    def test_public_roadmap_copy_uses_english_source_strings(self):
        template = WEBSITE_TEMPLATE.read_text()

        self.assertIn("Apply filters", template)
        self.assertIn("Official curriculum alignment", template)
        self.assertIn("Explore this course", template)
        self.assertIn("Explore curricular unit", template)
        self.assertIn("related courses", template)
        self.assertNotIn("Aplicar filtros", template)
        self.assertNotIn("Ligação a currículos oficiais", template)

    def test_public_submission_copy_uses_english_source_strings(self):
        template = SUBMISSION_TEMPLATE.read_text()

        self.assertIn("Suggest a learning resource", template)
        self.assertIn("Submit for review", template)
        self.assertIn("Submission received", template)
        self.assertIn("Waiting for editorial review.", template)
        self.assertIn("Suggested for curricular unit", template)
        self.assertIn("Back to curricular unit", template)
        self.assertNotIn("Sugerir um recurso de aprendizagem", template)

    def test_public_roadmap_catalogues_cover_supported_languages(self):
        expected_translations = {
            "pt": {
                "Learning": "Aprendizagem",
                "Curricular Units": "Unidades Curriculares",
                "Explore Content": "Explorar conteúdos",
                "Apply filters": "Aplicar filtros",
                "Official curriculum alignment": "Ligação a currículos oficiais",
                "Explore this course": "Explorar este curso",
                "Explore curricular unit": "Explorar unidade curricular",
                "related courses": "cursos relacionados",
                "Suggest a learning resource": "Sugerir um recurso de aprendizagem",
                "Submit for review": "Enviar para revisão",
                "Submission received": "Submissão recebida",
                "Waiting for editorial review.": "A aguardar revisão editorial.",
                "Suggest a resource": "Sugerir um recurso",
            },
            "es": {
                "Learning": "Aprendizaje",
                "Curricular Units": "Unidades Curriculares",
                "Explore Content": "Explorar contenidos",
                "Apply filters": "Aplicar filtros",
                "Official curriculum alignment": "Vinculación con planes de estudio oficiales",
                "Explore this course": "Explorar este curso",
                "Explore curricular unit": "Explorar unidad curricular",
                "related courses": "cursos relacionados",
                "Suggest a learning resource": "Sugerir un recurso de aprendizaje",
                "Submit for review": "Enviar a revisión",
                "Submission received": "Envío recibido",
                "Waiting for editorial review.": "En espera de revisión editorial.",
                "Suggest a resource": "Sugerir un recurso",
            },
            "fr": {
                "Learning": "Apprentissage",
                "Curricular Units": "Unités d’enseignement",
                "Explore Content": "Explorer les contenus",
                "Apply filters": "Appliquer les filtres",
                "Official curriculum alignment": "Correspondance avec les cursus officiels",
                "Explore this course": "Explorer ce cours",
                "Explore curricular unit": "Explorer l'unite d'enseignement",
                "related courses": "cours associes",
                "Suggest a learning resource": "Suggérer une ressource d’apprentissage",
                "Submit for review": "Envoyer pour examen",
                "Submission received": "Soumission reçue",
                "Waiting for editorial review.": "En attente d’un examen éditorial.",
                "Suggest a resource": "Suggérer une ressource",
            },
        }

        for language, translations in expected_translations.items():
            catalogue = (I18N_DIR / f"{language}.po").read_text()
            for source, translated in translations.items():
                self.assertIn(f'msgid "{source}"', catalogue)
                self.assertIn(f'msgstr "{translated}"', catalogue)


if __name__ == "__main__":
    unittest.main()