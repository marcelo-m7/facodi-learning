from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FacodiLearningCurriculumReference(models.Model):
    _name = "facodi.learning.curriculum.reference"
    _description = "FACODI Curriculum Reference"
    _order = "institution, programme_name, academic_year desc, id"

    name = fields.Char(compute="_compute_name", store=True)
    institution = fields.Char(required=True, index=True)
    programme_name = fields.Char(required=True, index=True)
    external_programme_code = fields.Char(index=True)
    academic_year = fields.Char(required=True, index=True)
    source_url = fields.Char()
    provider = fields.Char(required=True, default="manual", index=True)
    external_id = fields.Char(required=True, index=True)
    metadata = fields.Json()
    imported_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    validated_at = fields.Datetime()
    unit_ids = fields.One2many(
        "facodi.learning.curriculum.unit",
        "reference_id",
        string="Curricular Units",
    )

    _identity_unique = models.Constraint(
        "unique(provider, external_id)",
        "This curriculum reference already exists.",
    )

    @api.depends("institution", "programme_name", "academic_year")
    def _compute_name(self):
        for reference in self:
            institution = reference.institution or ""
            programme = reference.programme_name or ""
            academic_year = reference.academic_year or ""
            reference.name = f"{institution} — {programme} ({academic_year})"

    @api.model
    def _normalize_identity_values(self, vals):
        normalized = dict(vals)
        for field_name in ("provider", "external_id"):
            if field_name in normalized:
                normalized[field_name] = (normalized[field_name] or "").strip()
                if not normalized[field_name]:
                    raise ValidationError(
                        "Curriculum provider and external identity cannot be empty."
                    )
        return normalized

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(
            [self._normalize_identity_values(vals) for vals in vals_list]
        )

    def write(self, vals):
        return super().write(self._normalize_identity_values(vals))


class FacodiLearningCurriculumUnit(models.Model):
    _name = "facodi.learning.curriculum.unit"
    _description = "FACODI Curriculum Unit"
    _order = "reference_id, sequence, id"

    reference_id = fields.Many2one(
        "facodi.learning.curriculum.reference",
        required=True,
        ondelete="cascade",
        index=True,
    )
    external_unit_code = fields.Char(required=True, index=True)
    name = fields.Char(required=True, index=True)
    credits = fields.Float(digits=(8, 2))
    curricular_year = fields.Integer(index=True)
    period = fields.Selection(
        [
            ("semester_1", "Semester 1"),
            ("semester_2", "Semester 2"),
            ("annual", "Annual"),
            ("other", "Other / Source-defined"),
        ],
        default="other",
        index=True,
    )
    classification = fields.Selection(
        [
            ("mandatory", "Mandatory"),
            ("optional", "Optional"),
            ("unspecified", "Unspecified"),
        ],
        default="unspecified",
        required=True,
        index=True,
    )
    option_group = fields.Char()
    sequence = fields.Integer(default=10, index=True)
    metadata = fields.Json()

    _unit_identity_unique = models.Constraint(
        "unique(reference_id, external_unit_code)",
        "This curricular unit already exists in this curriculum reference.",
    )

    @api.constrains("credits")
    def _check_credits(self):
        if any(unit.credits < 0 for unit in self):
            raise ValidationError("Curriculum credits cannot be negative.")

    @api.constrains("curricular_year")
    def _check_curricular_year(self):
        if any(unit.curricular_year < 0 for unit in self):
            raise ValidationError("Curricular year cannot be negative.")

    @api.model
    def _normalize_unit_values(self, vals):
        normalized = dict(vals)
        if "external_unit_code" in normalized:
            normalized["external_unit_code"] = (
                normalized["external_unit_code"] or ""
            ).strip()
            if not normalized["external_unit_code"]:
                raise ValidationError("Curricular unit external code cannot be empty.")
        return normalized

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(
            [self._normalize_unit_values(vals) for vals in vals_list]
        )

    def write(self, vals):
        return super().write(self._normalize_unit_values(vals))
