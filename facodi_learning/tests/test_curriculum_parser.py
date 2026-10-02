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


    def test_multiple_curriculum_tables_with_repeated_headers_are_parsed(self):
        raw = b"""
        <html>
          <body>
            <h1>Gastronomia e Inovacao Alimentar</h1>
            <div data-academic-year="2026/27">2026/27</div>

            <table>
              <tr><th>Codigo</th><th>Unidade Curricular</th><th>ECTS</th></tr>
              <tr><td>19641011</td><td>Gastronomia Tradicional e Mediterranica</td><td>6,0</td></tr>
              <tr><td>19641007</td><td>Informatica</td><td>3</td></tr>
            </table>

            <table>
              <tr><th>Codigo</th><th>Unidade Curricular</th><th>ECTS</th></tr>
              <tr><td>19641001</td><td>Comunicacao e Storytelling</td><td>3</td></tr>
              <tr><td>19641005</td><td>Gastronomia Contemporanea</td><td>6</td></tr>
            </table>
          </body>
        </html>
        """

        payload = parse_ualg_course_plan(
            raw,
            academic_year="2026/27",
            source_url="https://www.ualg.pt/curso/1964/plano",
        )

        self.assertEqual(payload["external_programme_code"], "1964")
        self.assertEqual(payload["programme_name"], "Gastronomia e Inovacao Alimentar")
        self.assertEqual(payload["parser_version"], "ualg-course-plan-v2")
        self.assertEqual(len(payload["units"]), 4)
        self.assertEqual(
            {unit["external_unit_code"] for unit in payload["units"]},
            {"19641011", "19641007", "19641001", "19641005"},
        )
        self.assertEqual(
            next(
                unit["credits"]
                for unit in payload["units"]
                if unit["external_unit_code"] == "19641011"
            ),
            6.0,
        )
