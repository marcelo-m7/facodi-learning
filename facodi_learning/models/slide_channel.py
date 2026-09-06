from odoo import models

from ..services.course_mapping import course_mapping_candidates, propose_course_mappings
from ..services.course_profile import build_course_profile


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    def _facodi_course_profile(self):
        self.ensure_one()
        return build_course_profile(self)

    def _facodi_course_mapping_candidates(self, limit=20):
        self.ensure_one()
        return course_mapping_candidates(self, limit=limit)

    def _facodi_propose_course_mappings(self, limit=20):
        self.ensure_one()
        return propose_course_mappings(self, limit=limit)

    def action_facodi_view_course_mappings(self):
        self.ensure_one()
        self.check_access("read")
        action = self.env["ir.actions.actions"]._for_xml_id(
            "facodi_learning.action_facodi_course_mappings"
        )
        action.update(
            {
                "domain": [
                    "|",
                    ("source_channel_id", "=", self.id),
                    ("target_channel_id", "=", self.id),
                ],
                "context": {"default_source_channel_id": self.id},
            }
        )
        return action

    def action_facodi_generate_course_mappings_ui(self):
        self.ensure_one()
        mappings = self._facodi_propose_course_mappings()
        action = self.action_facodi_view_course_mappings()
        action["domain"] = [("id", "in", mappings.ids)]
        return action

    def action_facodi_view_curriculum_coverage(self):
        self.ensure_one()
        self.check_access("read")
        action = self.env["ir.actions.actions"]._for_xml_id(
            "facodi_learning.action_facodi_curriculum_coverage"
        )
        action["domain"] = [("channel_id", "=", self.id)]
        action["context"] = {"default_channel_id": self.id}
        return action

    def _facodi_related_channels(self, website=None):
        """Return only approved semantic relations visible to the current learner.

        Elevation is limited to the audit-model lookup because Public and Portal
        deliberately have no ACL on FACODI course mappings. The returned course
        records use the caller's real environment and Odoo's native publication,
        visibility, membership and website rules.
        """
        self.ensure_one()
        channel = self.sudo(False)
        channel.check_access("read")

        target_ids = (
            self.env["facodi.learning.course.mapping"]
            .sudo()
            .search(
                [
                    ("source_channel_id", "=", channel.id),
                    ("state", "=", "approved"),
                    ("mapping_type", "!=", "prerequisite"),
                ]
            )
            .mapped("target_channel_id")
            .ids
        )
        if not target_ids:
            return channel.browse()

        domain = [
            ("id", "in", target_ids),
            ("active", "=", True),
            ("is_published", "=", True),
            ("is_visible", "=", True),
        ]
        if website:
            domain.append(("website_id", "in", [False, website.id]))

        return channel.search(domain, order="sequence, id", limit=8)
