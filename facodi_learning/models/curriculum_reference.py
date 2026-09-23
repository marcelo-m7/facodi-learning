import re
import unicodedata
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


_TERMINAL_COVERAGE_STATES = ("approved", "rejected")
_REFERENCE_IDENTITY_FIELDS = {"provider", "external_id"}
_REFERENCE_REVIEWED_FACT_FIELDS = {
    "institution",
    "programme_name",
    "external_programme_code",
    "academic_year",
    "source_url",
    "source_title",
    "source_hash",
    "source_retrieved_at",
    "metadata",
}
_UNIT_IDENTITY_FIELDS = {"reference_id", "external_unit_code"}
_UNIT_REVIEWED_FACT_FIELDS = {
    "name",
    "credits",
    "curricular_year",
    "period",
    "classification",
    "option_group",
    "sequence",
    "metadata",
}


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
    source_title = fields.Char()
    source_hash = fields.Char(index=True)
    source_retrieved_at = fields.Datetime()
    website_published = fields.Boolean(
        default=False,
        index=True,
        help="Expose this validated external curriculum reference on the public FACODI website.",
    )
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

    def _has_terminal_coverage(self):
        if not self:
            return False
        return bool(
            self.env["facodi.learning.curriculum.coverage"].search_count(
                [
                    ("curriculum_unit_id.reference_id", "in", self.ids),
                    ("state", "in", _TERMINAL_COVERAGE_STATES),
                ],
                limit=1,
            )
        )

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
        if _REFERENCE_IDENTITY_FIELDS & normalized.keys():
            raise AccessError(
                "Curriculum reference identity is immutable; create a new versioned reference."
            )
        if (
            _REFERENCE_REVIEWED_FACT_FIELDS & normalized.keys()
            and self._has_terminal_coverage()
        ):
            raise AccessError(
                "Reviewed curriculum reference facts are immutable; create a new versioned reference."
            )
        return super().write(normalized)

    def _facodi_coverage_summary(self):
        self.ensure_one()
        from ..services.curriculum_coverage import build_curriculum_reference_coverage

        return build_curriculum_reference_coverage(self)

    def _facodi_is_public(self):
        self.ensure_one()
        return bool(self.website_published and self.validated_at)

    def _facodi_public_units_grouped(self):
        self.ensure_one()
        grouped = []
        for year in sorted(set(self.unit_ids.mapped("curricular_year"))):
            units = self.unit_ids.filtered(lambda unit: unit.curricular_year == year).sorted(
                key=lambda unit: (unit.sequence, unit.id)
            )
            grouped.append((year, units))
        return grouped

    def _facodi_public_coverage_map(self, website=None):
        """Return reviewed curriculum coverage limited to learner-visible courses.

        ACL elevation is restricted to the audit relation lookup. Course records are
        re-read without sudo so native Odoo publication, visibility and website rules
        remain authoritative for learner-facing pages.
        """
        self.ensure_one()
        if not self._facodi_is_public():
            return {}

        coverages = self.env["facodi.learning.curriculum.coverage"].sudo().search(
            [
                ("curriculum_unit_id.reference_id", "=", self.id),
                ("state", "=", "approved"),
            ],
            order="curriculum_unit_id, channel_id, id",
        )
        if not coverages:
            return {}

        channel_ids = coverages.mapped("channel_id").ids
        channel_model = self.env["slide.channel"].sudo(False)
        domain = [
            ("id", "in", channel_ids),
            ("active", "=", True),
            ("is_published", "=", True),
            ("is_visible", "=", True),
        ]
        if website:
            domain.append(("website_id", "in", [False, website.id]))

        visible_channels = channel_model.search(domain, order="sequence, id")
        channel_by_id = {channel.id: channel for channel in visible_channels}
        if not channel_by_id:
            return {}

        strength = {
            "supports": 1,
            "partial": 2,
            "covers": 3,
            "equivalent": 4,
        }
        labels = {
            "supports": _("Supplementary support"),
            "partial": _("Partial coverage"),
            "covers": _("Curriculum coverage"),
            "equivalent": _(
                "Content correspondence - not academic equivalence"
            ),
        }
        grouped = {}
        by_unit_channel = {}
        for coverage in coverages:
            channel = channel_by_id.get(coverage.channel_id.id)
            if not channel:
                continue
            key = (coverage.curriculum_unit_id.id, channel.id)
            existing = by_unit_channel.get(key)
            if existing and strength[existing.coverage_type] >= strength[coverage.coverage_type]:
                continue
            by_unit_channel[key] = coverage

        for (unit_id, channel_id), coverage in by_unit_channel.items():
            coverage_status = (
                "covered"
                if coverage.coverage_type in {"covers", "equivalent"}
                else "partial"
            )
            grouped.setdefault(unit_id, []).append(
                {
                    "channel": channel_by_id[channel_id],
                    "coverage_type": coverage.coverage_type,
                    "coverage_label": labels[coverage.coverage_type],
                    "coverage_status": coverage_status,
                }
            )

        for rows in grouped.values():
            rows.sort(key=lambda row: (row["channel"].sequence, row["channel"].id))
        return grouped

    def _facodi_public_unit_matrix(self, website=None):
        self.ensure_one()
        if not self._facodi_is_public():
            return []

        coverage_map = self._facodi_public_coverage_map(website=website)
        matrix = []
        for unit in self.unit_ids.sorted(key=lambda item: (item.sequence, item.id)):
            rows = coverage_map.get(unit.id, [])
            if any(row["coverage_status"] == "covered" for row in rows):
                coverage_status = "covered"
            elif rows:
                coverage_status = "partial"
            else:
                coverage_status = "gap"
            matrix.append(
                {
                    "unit": unit,
                    "unit_url": unit._facodi_public_path(),
                    "coverage_status": coverage_status,
                    "published_course_count": len(rows),
                    "coverage_rows": rows,
                }
            )
        return matrix

    def _facodi_public_unit_matrix_grouped(self, website=None):
        self.ensure_one()
        grouped = []
        matrix = self._facodi_public_unit_matrix(website=website)
        for year in sorted({entry["unit"].curricular_year for entry in matrix}):
            grouped.append(
                (
                    year,
                    [
                        entry
                        for entry in matrix
                        if entry["unit"].curricular_year == year
                    ],
                )
            )
        return grouped

    def _facodi_public_unit_matrix_by_period(self, website=None):
        self.ensure_one()
        grouped = []
        for year, entries in self._facodi_public_unit_matrix_grouped(website=website):
            periods = []
            for period in ("semester_1", "semester_2", "annual", "other"):
                period_entries = [
                    entry for entry in entries if entry["unit"].period == period
                ]
                if period_entries:
                    periods.append((period, period_entries))
            grouped.append((year, periods))
        return grouped

    def _facodi_public_coverage_links(self, website=None):
        self.ensure_one()
        links = []
        for unit_id, rows in self._facodi_public_coverage_map(website=website).items():
            unit = self.env["facodi.learning.curriculum.unit"].browse(unit_id)
            for row in rows:
                links.append(
                    {
                        "unit": unit,
                        "unit_url": unit._facodi_public_path(),
                        "channel": row["channel"],
                        "coverage_type": row["coverage_type"],
                        "coverage_label": row["coverage_label"],
                    }
                )
        links.sort(
            key=lambda link: (
                link["unit"].sequence,
                link["unit"].id,
                link["channel"].sequence,
                link["channel"].id,
            )
        )
        return links

    @api.model
    def _facodi_public_curriculum_map(self, website=None):
        """Project the approved public curriculum hierarchy for website visitors."""
        references = self.sudo().search(
            [
                ("website_published", "=", True),
                ("validated_at", "!=", False),
            ],
            order="institution, programme_name, academic_year desc, id",
        )
        curriculum_map = []
        for reference in references:
            unit_matrix = reference._facodi_public_unit_matrix(website=website)
            for entry in unit_matrix:
                entry["learning"] = entry["unit"]._facodi_public_learning_projection(
                    website=website
                )
            curriculum_map.append(
                {
                    "reference": reference,
                    "reference_url": "/roadmaps/%s" % reference.id,
                    "unit_matrix": unit_matrix,
                }
            )
        return curriculum_map


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

    def _has_terminal_coverage(self):
        if not self:
            return False
        return bool(
            self.env["facodi.learning.curriculum.coverage"].search_count(
                [
                    ("curriculum_unit_id", "in", self.ids),
                    ("state", "in", _TERMINAL_COVERAGE_STATES),
                ],
                limit=1,
            )
        )

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
        if _UNIT_IDENTITY_FIELDS & normalized.keys():
            raise AccessError(
                "Curriculum unit identity is immutable; create a new versioned unit/reference."
            )
        if _UNIT_REVIEWED_FACT_FIELDS & normalized.keys() and self._has_terminal_coverage():
            raise AccessError(
                "Reviewed curriculum unit facts are immutable; create a new versioned curriculum reference."
            )
        return super().write(normalized)

    def _facodi_coverage_summary(self):
        self.ensure_one()
        from ..services.curriculum_coverage import build_curriculum_unit_coverage

        return build_curriculum_unit_coverage(self)

    def _facodi_public_path(self):
        self.ensure_one()
        if not self.reference_id._facodi_is_public():
            return False
        return "/roadmaps/%s/units/%s" % (
            self.reference_id.id,
            quote(self.external_unit_code or "", safe=""),
        )

    def _facodi_public_catalog_path(self):
        self.ensure_one()
        if not self.reference_id._facodi_is_public():
            return False
        normalized_name = unicodedata.normalize("NFKD", self.name or "")
        normalized_name = normalized_name.encode("ascii", "ignore").decode("ascii")
        readable_name = re.sub(r"[^a-z0-9]+", "-", normalized_name.lower()).strip("-")
        return "/unidades-curriculares/%s/%s-%s" % (
            self.reference_id.id,
            quote(self.external_unit_code or "", safe=""),
            readable_name or "unidade-curricular",
        )

    @api.model
    def _facodi_public_catalog_entries(
        self,
        *,
        reference_id=None,
        curricular_year=None,
        period=None,
        credits=None,
        website=None,
    ):
        domain = [
            ("reference_id.website_published", "=", True),
            ("reference_id.validated_at", "!=", False),
        ]
        if reference_id:
            domain.append(("reference_id", "=", reference_id))
        if curricular_year:
            domain.append(("curricular_year", "=", curricular_year))
        if period:
            domain.append(("period", "=", period))
        if credits is not None:
            domain.append(("credits", "=", credits))

        units = self.sudo().search(
            domain,
            order="reference_id, curricular_year, period, sequence, id",
        )
        coverage_maps = {
            reference.id: reference._facodi_public_coverage_map(website=website)
            for reference in units.mapped("reference_id")
        }
        entries = []
        for unit in units:
            coverage_rows = coverage_maps[unit.reference_id.id].get(unit.id, [])
            if any(row["coverage_status"] == "covered" for row in coverage_rows):
                coverage_status = "covered"
            elif coverage_rows:
                coverage_status = "partial"
            else:
                coverage_status = "gap"
            entries.append(
                {
                    "unit": unit,
                    "reference": unit.reference_id,
                    "unit_url": unit._facodi_public_catalog_path(),
                    "coverage_status": coverage_status,
                    "published_course_count": len(coverage_rows),
                }
            )
        return entries

    def _facodi_public_module_rows(self, website=None, partner=None, viewer_env=None):
        """Return ordered reusable learning modules for this public UC."""
        self.ensure_one()
        if not self.reference_id._facodi_is_public():
            return []
        assignments = self.env[
            "facodi.learning.curriculum.module.assignment"
        ].sudo().search(
            [
                ("curriculum_unit_id", "=", self.id),
                ("module_id.website_published", "=", True),
            ],
            order="sequence, id",
        )
        rows = []
        for assignment in assignments:
            projection = assignment.module_id._facodi_public_projection(
                website=website,
                partner=partner,
                viewer_env=viewer_env,
            )
            projection["sequence"] = assignment.sequence
            rows.append(projection)
        return rows

    def _facodi_public_learning_projection(self, website=None, partner=None, viewer_env=None):
        self.ensure_one()
        modules = self._facodi_public_module_rows(
            website=website,
            partner=partner,
            viewer_env=viewer_env,
        )
        measured_modules = [row for row in modules if row["progress"] is not None]
        progress = (
            sum(row["progress"] for row in measured_modules) / len(measured_modules)
            if measured_modules
            else None
        )
        next_item = next((row["next_item"] for row in modules if row["next_item"]), False)
        return {
            "modules": modules,
            "module_count": len(modules),
            "progress": progress,
            "next_item": next_item,
        }

    def _facodi_public_coverage_rows(self, website=None):
        self.ensure_one()
        if not self.reference_id._facodi_is_public():
            return []
        return self.reference_id._facodi_public_coverage_map(website=website).get(
            self.id, []
        )

    def _facodi_public_coverage_status(self, website=None):
        self.ensure_one()
        rows = self._facodi_public_coverage_rows(website=website)
        if any(row["coverage_status"] == "covered" for row in rows):
            return "covered"
        if rows:
            return "partial"
        return "gap"
