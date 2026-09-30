from pathlib import Path

from odoo.tests.common import TransactionCase

from ..services.curriculum import CurriculumParseError, parse_ualg_course_plan


MODULE_ROOT = Path(__file__).resolve().parents[1]


class TestCurriculumParserBoundary(TransactionCase):
    def test_invalid_utf8_is_reported_as_curriculum_parse_error(self):
        with self.assertRaisesRegex(
            CurriculumParseError,
            "Curriculum response is not UTF-8 HTML",
        ):
            parse_ualg_course_plan(
                b"\xff\xfe",
                academic_year="2026/27",
                source_url="https://www.ualg.pt/curso/1941/plano",
            )

    def test_invalid_raw_type_is_reported_as_curriculum_parse_error(self):
        with self.assertRaisesRegex(
            CurriculumParseError,
            "Curriculum response is not UTF-8 HTML",
        ):
            parse_ualg_course_plan(
                "not-bytes",
                academic_year="2026/27",
                source_url="https://www.ualg.pt/curso/1941/plano",
            )

    def test_parser_does_not_use_blanket_exception_for_decode_boundary(self):
        source = (
            MODULE_ROOT
            / "services"
            / "curriculum"
            / "parser.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "except (TypeError, UnicodeDecodeError) as error:",
            source,
        )
        self.assertNotIn(
            'except Exception as error: raise CurriculumParseError("Curriculum response is not UTF-8 HTML.")',
            source,
        )
