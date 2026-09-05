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
