from odoo import SUPERUSER_ID, Command, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..services.course_mapping_policy import (
    get_course_mapping_policy,
    is_course_mapping_auto_eligible,
)


class FacodiLearningCourseMapping(models.Model):
    _name = "facodi.learning.course.mapping"
    _description = "FACODI Course Mapping"
    _order = "create_date desc, id desc"

    source_channel_id = fields.Many2one(
        "slide.channel",
        required=True,
        ondelete="restrict",
        index=True,
        string="Source Course",
    )
    target_channel_id = fields.Many2one(
        "slide.channel",
        required=True,
        ondelete="restrict",
        index=True,
        string="Target Course",
    )
    mapping_type = fields.Selection(
        [
            ("related", "Related"),
            ("alternative", "Alternative"),
            ("continuation", "Continuation"),
            ("complements", "Complements"),
            ("equivalent", "Equivalent"),
            ("prerequisite", "Prerequisite"),
        ],
        required=True,
        default="related",
        index=True,
    )
    confidence = fields.Float(digits=(5, 4))
    origin = fields.Selection(
        [("manual", "Manual"), ("analysis", "Analysis")],
        required=True,
        default="manual",
        index=True,
    )
    state = fields.Selection(
        [
            ("proposed", "Proposed"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        required=True,
        default="proposed",
        index=True,
    )
    evidence = fields.Json()
    ranking_version = fields.Char(readonly=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    policy_version = fields.Char(readonly=True)
    decision_snapshot = fields.Json(readonly=True)
    native_applied_by_id = fields.Many2one("res.users", readonly=True)
    native_applied_at = fields.Datetime(readonly=True)

    _mapping_unique = models.Constraint(
        "unique(source_channel_id, target_channel_id, mapping_type)",
        "This course mapping already exists.",
    )

    @api.constrains("source_channel_id", "target_channel_id")
    def _check_distinct_channels(self):
        if any(
            mapping.source_channel_id == mapping.target_channel_id
            for mapping in self
        ):
            raise ValidationError("Source and target courses must be different.")

    @api.constrains("confidence")
    def _check_confidence(self):
        for mapping in self:
            if not 0 <= mapping.confidence <= 1:
                raise ValidationError("Confidence must be between zero and one.")

    def _is_manager(self):
        return self.env.uid == SUPERUSER_ID or self.env.user.has_group(
            "website_slides.group_website_slides_manager"
        )

    def _check_manager(self):
        if not self._is_manager():
            raise AccessError(
                "Only eLearning Managers can review FACODI course mappings."
            )

    @api.model_create_multi
    def create(self, vals_list):
        protected = (
            "reviewed_by_id",
            "reviewed_at",
            "policy_version",
            "decision_snapshot",
            "native_applied_by_id",
            "native_applied_at",
        )
        identities = set()
        for vals in vals_list:
            if vals.get("state", "proposed") != "proposed" or any(
                vals.get(field_name) for field_name in protected
            ):
                raise AccessError("Use the explicit course mapping review actions.")

            source_id = vals.get("source_channel_id")
            target_id = vals.get("target_channel_id")
            mapping_type = vals.get("mapping_type", "related")
            identity = (source_id, target_id, mapping_type)
            if identity in identities or self.search_count(
                [
                    ("source_channel_id", "=", source_id),
                    ("target_channel_id", "=", target_id),
                    ("mapping_type", "=", mapping_type),
                ],
                limit=1,
            ):
                raise ValidationError("This course mapping already exists.")
            identities.add(identity)

            vals.update(
                state="proposed",
                reviewed_by_id=False,
                reviewed_at=False,
                policy_version=False,
                decision_snapshot=False,
                native_applied_by_id=False,
                native_applied_at=False,
            )
        return super().create(vals_list)

    def write(self, vals):
        protected = {
            "state",
            "reviewed_by_id",
            "reviewed_at",
            "source_channel_id",
            "target_channel_id",
            "mapping_type",
            "origin",
            "ranking_version",
            "policy_version",
            "decision_snapshot",
            "native_applied_by_id",
            "native_applied_at",
        }
        if protected & vals.keys():
            raise AccessError("Use the explicit course mapping review actions.")
        if any(mapping.state != "proposed" for mapping in self):
            raise AccessError("Reviewed course mappings are historical evidence.")
        return super().write(vals)

    def unlink(self):
        if any(
            mapping.state != "proposed" or mapping.origin != "manual"
            for mapping in self
        ):
            raise AccessError("Reviewed and generated course mappings are audit history.")
        return super().unlink()

    def _would_create_prerequisite_cycle(self):
        self.ensure_one()
        if self.mapping_type != "prerequisite":
            return False

        source_id = self.source_channel_id.id
        pending_ids = list(self.target_channel_id.prerequisite_channel_ids.ids)
        visited = set()
        while pending_ids:
            channel_id = pending_ids.pop()
            if channel_id == source_id:
                return True
            if channel_id in visited:
                continue
            visited.add(channel_id)
            channel = self.env["slide.channel"].browse(channel_id)
            channel.check_access("read")
            pending_ids.extend(
                prerequisite_id
                for prerequisite_id in channel.prerequisite_channel_ids.ids
                if prerequisite_id not in visited
            )
        return False

    def _apply_native_prerequisite(self, applied_at):
        self.ensure_one()
        if self.mapping_type != "prerequisite":
            return {}

        source = self.source_channel_id
        target = self.target_channel_id
        source.check_access("write")
        if target not in source.prerequisite_channel_ids:
            if self._would_create_prerequisite_cycle():
                raise ValidationError(
                    "This prerequisite would create a cycle in the eLearning course graph."
                )
            source.write({"prerequisite_channel_ids": [Command.link(target.id)]})

        return {
            "native_applied_by_id": self.env.uid,
            "native_applied_at": applied_at,
        }

    def _maybe_auto_approve(self):
        self.ensure_one()
        policy = get_course_mapping_policy(self.env)
        if not is_course_mapping_auto_eligible(self, policy):
            return False

        self.check_access("write")
        locked = self.try_lock_for_update()
        if not locked:
            return False
        locked.invalidate_recordset()
        if not is_course_mapping_auto_eligible(locked, policy):
            return False

        decision_at = fields.Datetime.now()
        snapshot = {
            "confidence": locked.confidence,
            "mapping_type": locked.mapping_type,
            "ranking_version": locked.ranking_version or False,
            "min_confidence": policy["min_confidence"],
            "auto_types": sorted(policy["auto_types"]),
            "policy_version": policy["policy_version"],
        }
        super(FacodiLearningCourseMapping, locked).write(
            {
                "state": "approved",
                "reviewed_by_id": False,
                "reviewed_at": decision_at,
                "policy_version": policy["policy_version"],
                "decision_snapshot": snapshot,
                "native_applied_by_id": False,
                "native_applied_at": False,
            }
        )
        return True

    def _review(self, state):
        if state not in {"approved", "rejected"}:
            raise ValidationError("Unsupported course mapping review state.")
        self._check_manager()
        self.check_access("write")
        records = self.try_lock_for_update()
        records.invalidate_recordset()
        if len(records) != len(self) or any(
            mapping.state != "proposed" for mapping in records
        ):
            raise ValidationError(
                "Only available proposed course mappings can be reviewed."
            )

        reviewed_at = fields.Datetime.now()
        for mapping in records:
            values = {
                "state": state,
                "reviewed_by_id": self.env.uid,
                "reviewed_at": reviewed_at,
            }
            if state == "approved":
                values.update(mapping._apply_native_prerequisite(reviewed_at))
            super(FacodiLearningCourseMapping, mapping).write(values)
        return True

    def action_approve(self):
        return self._review("approved")

    def action_reject(self):
        return self._review("rejected")
