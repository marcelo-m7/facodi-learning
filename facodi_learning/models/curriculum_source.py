import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..services.curriculum import (
    CurriculumFetchError,
    CurriculumParseError,
    canonical_payload_hash,
    fetch_official_curriculum,
    parse_ualg_course_plan,
)


_logger = logging.getLogger(__name__)


class CurriculumSource(models.Model):
    _name = "facodi.learning.curriculum.source"
    _description = "Official curriculum source"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    provider = fields.Char(required=True, default="ualg")
    external_id = fields.Char(required=True)
    institution = fields.Char(required=True)
    programme_name = fields.Char(required=True)
    external_programme_code = fields.Char(required=True)
    academic_year = fields.Char(required=True)
    source_url = fields.Char(required=True)
    website_id = fields.Many2one("website", required=True, ondelete="restrict")
    verification_enabled = fields.Boolean(
        default=False,
        help="Opt in this source to the bounded daily verification cron.",
    )
    responsible_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        domain=[("share", "=", False)],
        help="Internal user responsible for source-verification activities.",
    )
    checked_at = fields.Datetime(
        readonly=True,
        help="Last successful source verification.",
    )
    last_attempt_at = fields.Datetime(readonly=True)
    last_check_status = fields.Selection(
        [
            ("never", "Never checked"),
            ("ok", "No change"),
            ("changed", "Change detected"),
            ("failed", "Failed"),
        ],
        default="never",
        required=True,
        readonly=True,
    )
    last_check_error = fields.Text(readonly=True)
    current_reference_id = fields.Many2one("facodi.learning.curriculum.reference", readonly=True)
    reference_ids = fields.One2many("facodi.learning.curriculum.reference", "source_id")
    capture_ids = fields.One2many("facodi.learning.curriculum.capture", "source_id")

    def _require_manager(self):
        if not self.env.su and not self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        ):
            raise AccessError(_("Only eLearning Managers can verify curriculum sources."))

    def _problem_activity(self, problem):
        self.ensure_one()
        summaries = {
            "changed": "Review changed FACODI curriculum source",
            "failed": "Review failed FACODI curriculum source check",
        }
        summary = summaries[problem]
        todo = self.env.ref("mail.mail_activity_data_todo")
        return self.activity_ids.filtered(
            lambda activity: (
                activity.activity_type_id == todo
                and activity.summary == summary
            )
        )[:1]

    def _ensure_problem_activity(self, problem, note):
        self.ensure_one()
        if self._problem_activity(problem):
            return False
        user = self.responsible_id
        if not user or not user.active or user.share:
            user = self.env.user
        if user.share:
            user = self.env.ref("base.user_admin")
        summaries = {
            "changed": "Review changed FACODI curriculum source",
            "failed": "Review failed FACODI curriculum source check",
        }
        return self.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=user.id,
            summary=summaries[problem],
            note=note,
        )

    def _clear_problem_activity(self, problem):
        self.ensure_one()
        activity = self._problem_activity(problem)
        if activity:
            activity.unlink()

    def _record_check_failure(self, message, *, create_capture=False):
        self.ensure_one()
        if create_capture:
            self.env["facodi.learning.curriculum.capture"].create(
                {
                    "source_id": self.id,
                    "status": "failed",
                    "error": message,
                }
            )
        self.write(
            {
                "last_attempt_at": fields.Datetime.now(),
                "last_check_status": "failed",
                "last_check_error": message,
            }
        )
        self._ensure_problem_activity(
            "failed",
            _(
                "The official curriculum source could not be verified. "
                "The previously reviewed/published reference was preserved. "
                "Review the source configuration and server logs before retrying."
            ),
        )
        return "failed"

    def _verify_source_once(self):
        self.ensure_one()
        locked = self.try_lock_for_update()
        if not locked:
            return "skipped"
        source = locked
        source.invalidate_recordset()
        previous = source.current_reference_id
        try:
            raw, _final_url = fetch_official_curriculum(source.source_url)
        except CurriculumFetchError as error:
            return source._record_check_failure(str(error), create_capture=True)
        try:
            reference = source._import_raw(raw)
        except ValidationError as error:
            return source._record_check_failure(str(error), create_capture=False)
        except Exception:
            _logger.exception(
                "Unexpected curriculum verification failure for source %s",
                source.id,
            )
            return source._record_check_failure(
                _(
                    "The curriculum verification failed unexpectedly. "
                    "Please review the server logs."
                ),
                create_capture=True,
            )

        changed = not previous or reference != previous
        source.write(
            {
                "last_attempt_at": fields.Datetime.now(),
                "last_check_status": "changed" if changed else "ok",
                "last_check_error": False,
            }
        )
        source._clear_problem_activity("failed")
        if changed:
            source._ensure_problem_activity(
                "changed",
                _(
                    "The official curriculum source changed. A new draft reference "
                    "was created. Review and validate it explicitly before publication."
                ),
            )
        return "changed" if changed else "ok"

    def action_verify_now(self):
        self._require_manager()
        statuses = [source._verify_source_once() for source in self]
        if len(self) == 1:
            status = statuses[0]
            labels = {
                "ok": _("No curriculum change detected."),
                "changed": _("A curriculum change was detected and stored as draft."),
                "failed": _("Curriculum verification failed; review the pending activity."),
                "skipped": _("Curriculum verification is already running."),
            }
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Curriculum source verification"),
                    "message": labels[status],
                    "type": "warning" if status == "failed" else "success",
                    "sticky": status in {"changed", "failed"},
                },
            }
        return True

    @api.model
    def _cron_verify_enabled_sources(self):
        parameter = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("facodi_learning.curriculum_verify_batch_size", "10")
        )
        try:
            batch_size = max(1, min(int(parameter), 50))
        except (TypeError, ValueError):
            batch_size = 10

        domain = [("verification_enabled", "=", True)]
        sources = self.sudo().search(
            domain,
            limit=batch_size,
            order="last_attempt_at, id",
        )
        remaining = self.sudo().search_count(domain)
        for source in sources:
            try:
                with self.env.cr.savepoint():
                    source._verify_source_once()
            except Exception:
                _logger.exception(
                    "Unhandled curriculum cron failure for source %s",
                    source.id,
                )
                try:
                    source._record_check_failure(
                        _(
                            "The curriculum verification failed unexpectedly. "
                            "Please review the server logs."
                        ),
                        create_capture=True,
                    )
                except Exception:
                    _logger.exception(
                        "Could not persist curriculum cron failure evidence for source %s",
                        source.id,
                    )
            remaining = max(0, remaining - 1)
            if self.env.context.get("cron_id"):
                if not self.env["ir.cron"]._commit_progress(1, remaining=remaining):
                    break
        return True

    def _import_raw(self, raw):
        self.ensure_one()
        message = False
        try:
            if self.provider != "ualg":
                raise ValidationError(_("Unsupported official curriculum provider."))
            payload = parse_ualg_course_plan(
                raw,
                academic_year=self.academic_year,
                source_url=self.source_url,
            )
            payload_hash = canonical_payload_hash(payload)
        except (CurriculumParseError, ValidationError) as error:
            message = str(error)
        except Exception as error:
            _logger.exception("Unexpected curriculum import failure for source %s", self.id)
            message = _(
                "The curriculum import failed unexpectedly. Please review the server logs."
            )

        if message:
            self.env["facodi.learning.curriculum.capture"].create(
                {"source_id": self.id, "status": "failed", "error": message}
            )
            raise ValidationError(message)

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
    validated_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
        string="Validated By",
    )
    published_at = fields.Datetime(readonly=True, copy=False)
    published_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
        string="Published By",
    )
    archived_at = fields.Datetime(readonly=True, copy=False)
    archived_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
        string="Archived By",
    )
    occurrence_ids = fields.One2many("facodi.learning.curriculum.occurrence", "reference_id")

    def _require_manager(self):
        if not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError(_("Only eLearning Managers can review curriculum references."))

    def _write_lifecycle(self, vals):
        """Apply a reviewed lifecycle change without exposing a context bypass."""
        return super().write(vals)

    def action_validate(self):
        self._require_manager()
        if any(reference.state != "draft" for reference in self):
            raise ValidationError(_("Only draft curriculum references can be validated."))
        self._write_lifecycle(
            {
                "state": "validated",
                "validated_at": fields.Datetime.now(),
                "validated_by_id": self.env.user.id,
            }
        )
        for source in self.mapped("source_id"):
            source._clear_problem_activity("changed")

    def action_publish(self):
        self._require_manager()
        if any(reference.state != "validated" for reference in self):
            raise ValidationError(_("Only validated curriculum references can be published."))
        to_publish = self.filtered(lambda reference: not reference.website_published)
        if to_publish:
            to_publish._write_lifecycle(
                {
                    "is_published": True,
                    "website_published": True,
                    "published_at": fields.Datetime.now(),
                    "published_by_id": self.env.user.id,
                }
            )

    def action_archive(self):
        self._require_manager()
        to_archive = self.filtered(lambda reference: reference.state != "archived")
        if to_archive:
            to_archive._write_lifecycle(
                {
                    "state": "archived",
                    "is_published": False,
                    "website_published": False,
                    "archived_at": fields.Datetime.now(),
                    "archived_by_id": self.env.user.id,
                }
            )

    def write(self, vals):
        lifecycle_fields = {
            "state",
            "is_published",
            "website_published",
            "validated_at",
            "validated_by_id",
            "published_at",
            "published_by_id",
            "archived_at",
            "archived_by_id",
        }
        if lifecycle_fields.intersection(vals):
            raise AccessError(_("Use curriculum review actions to change lifecycle state."))
        if any(reference.state == "validated" for reference in self):
            raise AccessError(_("Validated curriculum facts are immutable."))
        return super().write(vals)