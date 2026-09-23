from odoo import fields, models
from odoo.exceptions import AccessError, ValidationError

from ..services.curriculum import canonical_payload_hash, parse_ualg_course_plan


class CurriculumSource(models.Model):
    _name = "facodi.learning.curriculum.source"
    _description = "Official curriculum source"

    provider = fields.Char(required=True, default="ualg")
    external_id = fields.Char(required=True)
    institution = fields.Char(required=True)
    programme_name = fields.Char(required=True)
    external_programme_code = fields.Char(required=True)
    academic_year = fields.Char(required=True)
    source_url = fields.Char(required=True)
    website_id = fields.Many2one("website", required=True, ondelete="restrict")
    checked_at = fields.Datetime(readonly=True)
    current_reference_id = fields.Many2one("facodi.learning.curriculum.reference", readonly=True)
    reference_ids = fields.One2many("facodi.learning.curriculum.reference", "source_id")
    capture_ids = fields.One2many("facodi.learning.curriculum.capture", "source_id")

    def _import_raw(self, raw):
        self.ensure_one()
        try:
            if self.provider != "ualg":
                raise ValidationError("Unsupported official curriculum provider.")
            payload = parse_ualg_course_plan(raw, academic_year=self.academic_year, source_url=self.source_url)
            payload_hash = canonical_payload_hash(payload)
        except Exception as error:
            self.env["facodi.learning.curriculum.capture"].create({
                "source_id": self.id, "status": "failed", "error": str(error),
            })
            raise ValidationError(str(error)) from error
        self.env["facodi.learning.curriculum.capture"].create({
            "source_id": self.id, "status": "success", "payload_hash": payload_hash,
        })
        current = self.current_reference_id
        if current and current.source_hash == payload_hash:
            self.checked_at = fields.Datetime.now()
            return current
        revision = (max(self.reference_ids.mapped("revision")) if self.reference_ids else 0) + 1
        reference = self.env["facodi.learning.curriculum.reference"].create({
            "source_id": self.id, "provider": self.provider,
            "external_id": "%s:r%s" % (self.external_id, revision),
            "institution": payload["institution"], "programme_name": payload["programme_name"],
            "external_programme_code": payload["external_programme_code"],
            "academic_year": payload["academic_year"], "source_url": self.source_url,
            "source_hash": payload_hash, "revision": revision, "state": "draft",
            "metadata": {"parser_version": payload["parser_version"]},
        })
        units = self.env["facodi.learning.curriculum.unit"]
        for values in payload["units"]:
            units |= units.create(dict(values, reference_id=reference.id))
        by_code = {unit.external_unit_code: unit for unit in units}
        groups = {}
        for values in payload["option_groups"]:
            groups[values["external_id"]] = self.env["facodi.learning.curriculum.option.group"].create(dict(values, reference_id=reference.id))
        for values in payload["occurrences"]:
            self.env["facodi.learning.curriculum.occurrence"].create({
                "reference_id": reference.id, "unit_id": by_code[values["external_unit_code"]].id,
                "option_group_id": groups.get(values.get("option_group_external_id")).id if values.get("option_group_external_id") else False,
                "curricular_year": values["curricular_year"], "period": values["period"], "sequence": values["sequence"],
            })
        self.write({"current_reference_id": reference.id, "checked_at": fields.Datetime.now()})
        return reference


class CurriculumCapture(models.Model):
    _name = "facodi.learning.curriculum.capture"
    _description = "Official curriculum import capture"
    _order = "id desc"
    source_id = fields.Many2one("facodi.learning.curriculum.source", required=True, ondelete="cascade")
    status = fields.Selection([("success", "Success"), ("failed", "Failed")], required=True)
    payload_hash = fields.Char()
    error = fields.Text()


class CurriculumOptionGroup(models.Model):
    _name = "facodi.learning.curriculum.option.group"
    _description = "Curriculum option group"
    reference_id = fields.Many2one("facodi.learning.curriculum.reference", required=True, ondelete="cascade")
    external_id = fields.Char(required=True)
    name = fields.Char(required=True)
    curricular_year = fields.Integer()
    period = fields.Char()
    sequence = fields.Integer()


class CurriculumOccurrence(models.Model):
    _name = "facodi.learning.curriculum.occurrence"
    _description = "Curriculum unit occurrence"
    reference_id = fields.Many2one("facodi.learning.curriculum.reference", required=True, ondelete="cascade")
    unit_id = fields.Many2one("facodi.learning.curriculum.unit", required=True, ondelete="cascade")
    option_group_id = fields.Many2one("facodi.learning.curriculum.option.group", ondelete="set null")
    curricular_year = fields.Integer(required=True)
    period = fields.Selection([("semester_1", "Semester 1"), ("semester_2", "Semester 2"), ("annual", "Annual"), ("other", "Other")], required=True)
    sequence = fields.Integer(default=10)


class CurriculumReference(models.Model):
    _inherit = "facodi.learning.curriculum.reference"

    source_id = fields.Many2one("facodi.learning.curriculum.source", ondelete="restrict", readonly=True)
    revision = fields.Integer(default=1, readonly=True)
    state = fields.Selection([("draft", "Draft"), ("validated", "Validated"), ("archived", "Archived")], default="draft", required=True, readonly=True)
    is_published = fields.Boolean(readonly=True)
    occurrence_ids = fields.One2many("facodi.learning.curriculum.occurrence", "reference_id")

    def _require_manager(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError("Only eLearning Managers can review curriculum references.")

    def action_validate(self):
        self._require_manager()
        self.with_context(facodi_curriculum_review=True).write({"state": "validated", "validated_at": fields.Datetime.now()})

    def action_publish(self):
        self._require_manager()
        if any(reference.state != "validated" for reference in self):
            raise ValidationError("Only validated curriculum references can be published.")
        self.with_context(facodi_curriculum_review=True).write({"is_published": True, "website_published": True})

    def action_archive(self):
        self._require_manager()
        self.with_context(facodi_curriculum_review=True).write({"state": "archived", "website_published": False})

    def write(self, vals):
        if any(reference.state == "validated" for reference in self) and not self.env.context.get("facodi_curriculum_review"):
            allowed = {"state", "is_published", "website_published", "validated_at"}
            if set(vals) - allowed:
                raise AccessError("Validated curriculum facts are immutable.")
        if "state" in vals and not self.env.context.get("facodi_curriculum_review"):
            raise AccessError("Use curriculum review actions to change state.")
        return super().write(vals)