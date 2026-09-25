from pathlib import Path
import unittest


MODULE_ROOT = Path(__file__).resolve().parents[1]
WEBSITE_TEMPLATE = MODULE_ROOT / "views" / "website_curriculum.xml"
WEBSITE_SLIDES_TEMPLATE = MODULE_ROOT / "views" / "website_slides.xml"
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

    def test_contextual_resource_contribution_ctas_use_canonical_route(self):
        curriculum = WEBSITE_TEMPLATE.read_text()
        slides = WEBSITE_SLIDES_TEMPLATE.read_text()
        submission = SUBMISSION_TEMPLATE.read_text()

        self.assertGreaterEqual(curriculum.count("/contribuir/recurso"), 6)
        self.assertIn(
            "/contribuir/recurso?curriculum_unit_id=%s",
            curriculum,
        )
        self.assertGreaterEqual(slides.count("/contribuir/recurso"), 2)
        self.assertIn("/contactus", slides)
        self.assertIn("/contribuir/recurso", submission)

    def test_public_submission_copy_uses_english_source_strings(self):
        template = SUBMISSION_TEMPLATE.read_text()

        self.assertIn("Suggest a learning resource", template)
        self.assertIn("Submit for review", template)
        self.assertIn("Submission received", template)
        self.assertIn("Waiting for editorial review.", template)
        self.assertNotIn("Sugerir um recurso de aprendizagem", template)

    def test_public_roadmap_catalogues_cover_supported_languages(self):
        expected_translations = {
            "pt": {
                "Learning": "Aprendizagem",
                "Curricular Units": "Unidades Curriculares",
                "Explore Content": "Explorar conteúdos",
                "Apply filters": "Aplicar filtros",
                "Official curriculum alignment": "Ligação a currículos oficiais",
                "Content correspondence - not academic equivalence": "Correspondência de conteúdo — não equivalência académica",
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
                "Content correspondence - not academic equivalence": "Correspondencia de contenido — no equivalencia académica",
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
                "Content correspondence - not academic equivalence": "Correspondance de contenu — pas une équivalence académique",
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

    def test_public_curriculum_academic_boundary_is_fully_translated(self):
        source_entry = (
            'msgid ""\n'
            '"<strong>Provenance and limits.</strong>\\n"\n'
            '"                                ECTS and the curricular structure shown are facts from the external source.\\n"\n'
            '"                                FACODI does not grant credits, enrolment, academic equivalence, or replace the institution."\n'
        )
        expected_msgstr = {
            "pt": (
                'msgstr ""\n'
                '"<strong>Proveniência e limites.</strong>\\n"\n'
                '"                                Os ECTS e a estrutura curricular apresentada são factos da fonte externa.\\n"\n'
                '"                                A FACODI não atribui créditos, matrícula, equivalência académica nem substitui a instituição."'
            ),
            "es": (
                'msgstr ""\n'
                '"<strong>Procedencia y límites.</strong>\\n"\n'
                '"                                Los ECTS y la estructura curricular mostrados son datos de la fuente externa.\\n"\n'
                '"                                FACODI no otorga créditos, matrícula, equivalencia académica ni sustituye a la institución."'
            ),
            "fr": (
                'msgstr ""\n'
                '"<strong>Provenance et limites.</strong>\\n"\n'
                '"                                Les ECTS et la structure du cursus présentés sont des faits provenant de la source externe.\\n"\n'
                '"                                FACODI n\'accorde pas de crédits, d\'inscription ni d\'équivalence académique et ne remplace pas l\'établissement."'
            ),
        }

        for language, translated_entry in expected_msgstr.items():
            catalogue = (I18N_DIR / f"{language}.po").read_text()
            complete_entry = f"{source_entry}{translated_entry}"
            self.assertIn(complete_entry, catalogue)


if __name__ == "__main__":
    unittest.main()