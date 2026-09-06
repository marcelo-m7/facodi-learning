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

    @api.model
    def _identity_exists(self, provider, external_id, exclude_ids=None):
        domain = [
            ("provider", "=", provider),
            ("external_id", "=", external_id),
        ]
        if exclude_ids:
            domain.append(("id", "not in", exclude_ids))
        return bool(self.search_count(domain, limit=1))

    @api.model_create_multi
    def create(self, vals_list):
        normalized_list = [self._normalize_identity_values(vals) for vals in vals_list]
        identities = set()
        for vals in normalized_list:
            provider = vals.get("provider", "manual").strip()
            external_id = vals.get("external_id", "").strip()
            identity = (provider, external_id)
            if identity in identities or self._identity_exists(provider, external_id):
                raise ValidationError("This curriculum reference already exists.")
            identities.add(identity)
            vals.update(provider=provider, external_id=external_id)
        return super().create(normalized_list)

    def write(self, vals):
        normalized = self._normalize_identity_values(vals)
        if {"provider", "external_id"} & normalized.keys():
            identities = set()
            for reference in self:
                provider = normalized.get("provider", reference.provider)
                external_id = normalized.get("external_id", reference.external_id)
                identity = (provider, external_id)
                if identity in identities or self._identity_exists(
                    provider, external_id, exclude_ids=self.ids
                ):
                    raise ValidationError("This curriculum reference already exists.")
                identities.add(identity)
        return super().write(normalized)

    def _facodi_coverage_summary(self):
        self.ensure_one()
        from ..services.curriculum_coverage import build_curriculum_reference_coverage

        return build_curriculum_reference_coverage(self)


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

    @api.model
    def _unit_identity_exists(self, reference_id, external_unit_code, exclude_ids=None):
        domain = [
            ("reference_id", "=", reference_id),
            ("external_unit_code", "=", external_unit_code),
        ]
        if exclude_ids:
            domain.append(("id", "not in", exclude_ids))
        return bool(self.search_count(domain, limit=1))

    @api.model_create_multi
    def create(self, vals_list):
        normalized_list = [self._normalize_unit_values(vals) for vals in vals_list]
        identities = set()
        for vals in normalized_list:
            reference_id = vals.get("reference_id")
            external_unit_code = vals.get("external_unit_code", "").strip()
            identity = (reference_id, external_unit_code)
            if identity in identities or self._unit_identity_exists(
                reference_id, external_unit_code
            ):
                raise ValidationError(
                    "This curricular unit already exists in this curriculum reference."
                )
            identities.add(identity)
            vals["external_unit_code"] = external_unit_code
        return super().create(normalized_list)

    def write(self, vals):
        normalized = self._normalize_unit_values(vals)
        if {"reference_id", "external_unit_code"} & normalized.keys():
            identities = set()
            for unit in self:
                reference_id = normalized.get("reference_id", unit.reference_id.id)
                external_unit_code = normalized.get(
                    "external_unit_code", unit.external_unit_code
                )
                identity = (reference_id, external_unit_code)
                if identity in identities or self._unit_identity_exists(
                    reference_id,
                    external_unit_code,
                    exclude_ids=self.ids,
                ):
                    raise ValidationError(
                        "This curricular unit already exists in this curriculum reference."
                    )
                identities.add(identity)
        return super().write(normalized)

    def _facodi_coverage_summary(self):
        self.ensure_one()
        from ..services.curriculum_coverage import build_curriculum_unit_coverage

        return build_curriculum_unit_coverage(self)
