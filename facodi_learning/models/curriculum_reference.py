from odoo import api, fields, models
from odoo.exceptions import ValidationError


def _require_nonblank(values, field_names):
    for field_name in field_names:
        value = values.get(field_name)
        if isinstance(value, str) and not value.strip():
            raise ValidationError(f"{field_name.replace('_', ' ').title()} cannot be blank.")


class FacodiLearningCurriculumReference(models.Model):
    _name = "facodi.learning.curriculum.reference"
    _description = "FACODI External Curriculum Reference"
    _order = "institution, programme_name, academic_year desc, id"

    institution = fields.Char(required=True, index=True)
    programme_name = fields.Char(required=True, index=True)
    external_programme_code = fields.Char(index=True)
    academic_year = fields.Char(required=True, index=True)
    source_url = fields.Char(required=True)
    provider = fields.Char(required=True, default="manual", index=True)
    metadata = fields.Json()
    selection_enabled = fields.Boolean(default=False, index=True)
    imported_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    validated_at = fields.Datetime()
    unit_ids = fields.One2many(
        "facodi.learning.curriculum.unit",
        "reference_id",
        string="Curriculum Units",
    )

    _reference_unique = models.Constraint(
        "unique(provider, external_programme_code, academic_year)",
        "This curriculum version is already registered for this provider.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for incoming in vals_list:
            vals = dict(incoming)
            _require_nonblank(
                vals,
                ("institution", "programme_name", "academic_year", "source_url", "provider"),
            )
            provider = vals.get("provider", "manual")
            programme_code = vals.get("external_programme_code")
            academic_year = vals.get("academic_year")
            if programme_code and academic_year and self.search_count(
                [
                    ("provider", "=", provider),
                    ("external_programme_code", "=", programme_code),
                    ("academic_year", "=", academic_year),
                ],
                limit=1,
            ):
                raise ValidationError(
                    "This curriculum version is already registered for this provider."
                )
        return super().create(vals_list)

    def write(self, vals):
        _require_nonblank(
            vals,
            ("institution", "programme_name", "academic_year", "source_url", "provider"),
        )
        return super().write(vals)


class FacodiLearningCurriculumUnit(models.Model):
    _name = "facodi.learning.curriculum.unit"
    _description = "FACODI External Curriculum Unit"
    _order = "reference_id, sequence, id"

    reference_id = fields.Many2one(
        "facodi.learning.curriculum.reference",
        required=True,
        ondelete="cascade",
        index=True,
    )
    external_unit_code = fields.Char(index=True)
    name = fields.Char(required=True, index=True)
    credits = fields.Float()
    curricular_year = fields.Integer(index=True)
    period = fields.Selection(
        [
            ("semester_1", "Semester 1"),
            ("semester_2", "Semester 2"),
            ("annual", "Annual"),
            ("other", "Other"),
        ]
    )
    classification = fields.Selection(
        [
            ("mandatory", "Mandatory"),
            ("optional", "Optional"),
            ("unknown", "Not specified"),
        ],
        default="unknown",
    )
    option_group = fields.Char()
    sequence = fields.Integer(default=10, index=True)
    metadata = fields.Json()

    _unit_code_unique = models.Constraint(
        "unique(reference_id, external_unit_code)",
        "This curriculum unit code already exists in this curriculum version.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        seen = set()
        for incoming in vals_list:
            vals = dict(incoming)
            _require_nonblank(vals, ("name",))
            self._validate_numbers(vals)
            reference_id = vals.get("reference_id")
            unit_code = vals.get("external_unit_code")
            if reference_id and unit_code:
                identity = (reference_id, unit_code)
                if identity in seen or self.search_count(
                    [
                        ("reference_id", "=", reference_id),
                        ("external_unit_code", "=", unit_code),
                    ],
                    limit=1,
                ):
                    raise ValidationError(
                        "This curriculum unit code already exists in this curriculum version."
                    )
                seen.add(identity)
        return super().create(vals_list)

    def write(self, vals):
        _require_nonblank(vals, ("name",))
        self._validate_numbers(vals)
        return super().write(vals)

    @api.constrains("credits", "curricular_year")
    def _check_nonnegative_numbers(self):
        for unit in self:
            if unit.credits < 0:
                raise ValidationError("Credits cannot be negative.")
            if unit.curricular_year < 0:
                raise ValidationError("Curricular year cannot be negative.")

    @api.model
    def _validate_numbers(self, vals):
        if "credits" in vals and vals["credits"] is not False and vals["credits"] < 0:
            raise ValidationError("Credits cannot be negative.")
        if (
            "curricular_year" in vals
            and vals["curricular_year"] is not False
            and vals["curricular_year"] < 0
        ):
            raise ValidationError("Curricular year cannot be negative.")
