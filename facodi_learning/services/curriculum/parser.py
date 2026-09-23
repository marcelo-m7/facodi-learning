import re
from html.parser import HTMLParser
from urllib.parse import urlparse


PARSER_VERSION = "ualg-course-plan-v1"


class CurriculumParseError(ValueError):
    pass


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.in_table = [], [], [], False
        self.year = None
        self.context = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table": self.in_table = True
        elif tag == "tr" and self.in_table: self.row = []
        elif tag in {"td", "th"} and self.in_table: self.cell = []
        if attributes.get("data-academic-year"): self.year = attributes["data-academic-year"]

    def handle_data(self, data):
        text = " ".join(data.split())
        if text:
            self.context.append(text)
            if self.in_table and self.cell is not None: self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.in_table: self.row.append(" ".join(self.cell))
        elif tag == "tr" and self.in_table and self.row: self.rows.append(self.row)
        elif tag == "table": self.in_table = False


def parse_ualg_course_plan(raw, *, academic_year, source_url):
    if not re.fullmatch(r"20\d{2}/\d{2}", academic_year or ""):
        raise CurriculumParseError("Academic year must use YYYY/YY format.")
    try: html = bytes(raw).decode("utf-8")
    except Exception as error: raise CurriculumParseError("Curriculum response is not UTF-8 HTML.") from error
    parser = _TableParser(); parser.feed(html)
    if academic_year not in html: raise CurriculumParseError("Academic year is not present in the official page.")
    code = re.search(r"/curso/([^/]+)/", urlparse(source_url).path + "/")
    programme = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", html, re.S | re.I)
    if not code or not programme: raise CurriculumParseError("Official curriculum page has no programme identity.")
    units, occurrences, sequence = {}, [], 0
    for rows in [parser.rows]:
        if len(rows) < 2: continue
        header = [" ".join(value.lower().split()) for value in rows[0]]
        def index(*names): return next((i for i, value in enumerate(header) if any(name in value for name in names)), None)
        name_i, credit_i, code_i = index("unidade curricular", "disciplina"), index("ects", "credit"), index("código", "codigo", "code")
        if None in {name_i, credit_i, code_i}: continue
        for row in rows[1:]:
            if len(row) <= max(name_i, credit_i, code_i): continue
            unit_code, name = row[code_i].strip(), row[name_i].strip()
            try: credits = float(row[credit_i].replace(",", "."))
            except ValueError as error: raise CurriculumParseError("Invalid ECTS value.") from error
            if not unit_code or not name: raise CurriculumParseError("Curriculum unit name and code are required.")
            units.setdefault(unit_code, {"external_unit_code": unit_code, "name": name, "credits": credits, "classification": "mandatory", "metadata": {}})
            sequence += 10
            occurrences.append({"external_unit_code": unit_code, "curricular_year": 1, "period": "semester_1", "option_group_external_id": False, "sequence": sequence, "metadata": {}})
    if not units: raise CurriculumParseError("Academic year has no curriculum units.")
    for number, unit in enumerate(sorted(units.values(), key=lambda row: row["external_unit_code"]), 1): unit["sequence"] = number * 10
    title = re.sub(r"<[^>]+>", "", programme.group(1)).strip()
    return {"provider": "ualg", "institution": "Universidade do Algarve", "programme_name": title, "external_programme_code": code.group(1), "academic_year": academic_year, "source_url": source_url, "parser_version": PARSER_VERSION, "units": sorted(units.values(), key=lambda row: row["external_unit_code"]), "option_groups": [], "occurrences": occurrences}