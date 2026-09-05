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
