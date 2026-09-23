from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FacodiLearningCurriculumModule(models.Model):
    _name = "facodi.learning.curriculum.module"
    _description = "FACODI Reusable Curriculum Module"
    _order = "name, id"

    name = fields.Char(required=True, index=True)
    description = fields.Html()
    website_published = fields.Boolean(default=False, index=True)
    assignment_ids = fields.One2many(
        "facodi.learning.curriculum.module.assignment",
        "module_id",
        string="Curricular Units",
    )
    item_ids = fields.One2many(
        "facodi.learning.curriculum.module.item",
        "module_id",
        string="Learning Items",
    )

    def _facodi_public_path(self):
        self.ensure_one()
        return "/modulos/%s" % self.id if self.website_published else False

    def _facodi_public_items(self, website=None, partner=None):
        """Project published module items without exposing authoring records.

        Module relations are editorial data with no Public/Portal ACL. Only their
        identifiers are read with sudo; course and content records are searched
        again in the caller environment so standard Odoo visibility rules decide
        what a learner can actually see.
        """
        self.ensure_one()
        items = self.env["facodi.learning.curriculum.module.item"].sudo().search(
            [("module_id", "=", self.id)], order="sequence, id"
        )
        channel_ids = items.mapped("channel_id").ids
        slide_ids = items.mapped("slide_id").ids

        channel_domain = [
            ("id", "in", channel_ids),
            ("active", "=", True),
            ("is_published", "=", True),
            ("is_visible", "=", True),
        ]
        slide_domain = [
            ("id", "in", slide_ids),
            ("is_published", "=", True),
            ("channel_id.active", "=", True),
            ("channel_id.is_published", "=", True),
            ("channel_id.is_visible", "=", True),
        ]
        if website:
            channel_domain.append(("website_id", "in", [False, website.id]))
            slide_domain.extend(
                [
                    ("website_id", "in", [False, website.id]),
                    ("channel_id.website_id", "in", [False, website.id]),
                ]
            )

        Channel = self.env["slide.channel"].sudo(False)
        Slide = self.env["slide.slide"].sudo(False)
        channels = {channel.id: channel for channel in Channel.search(channel_domain)}
        slides = {slide.id: slide for slide in Slide.search(slide_domain)}
        progress_by_channel = self._facodi_channel_progress(channels, partner)

        rows = []
        for item in items:
            if item.channel_id.id in channels:
                channel = channels[item.channel_id.id]
                rows.append(
                    {
                        "kind": "course",
                        "record": channel,
                        "name": channel.name,
                        "url": channel.website_url,
                        "progress": progress_by_channel.get(channel.id, 0.0),
                    }
                )
            elif item.slide_id.id in slides:
                slide = slides[item.slide_id.id]
                rows.append(
                    {
                        "kind": slide.slide_category,
                        "record": slide,
                        "name": slide.name,
                        "url": slide.website_url,
                        "progress": progress_by_channel.get(slide.channel_id.id, 0.0),
                    }
                )
        return rows

    def _facodi_channel_progress(self, channels, partner=None):
        """Return read-only standard eLearning membership completion by course."""
        if not channels or not partner:
            return {}
        Membership = self.env["slide.channel.partner"].sudo()
        memberships = Membership.search(
            [("channel_id", "in", list(channels)), ("partner_id", "=", partner.id)]
        )
        if "completion" not in Membership._fields:
            return {}
        progress = {}
        for membership in memberships:
            value = float(membership.completion or 0.0)
            progress[membership.channel_id.id] = value * 100 if value <= 1 else value
        return progress

    def _facodi_public_projection(self, website=None, partner=None):
        self.ensure_one()
        items = self._facodi_public_items(website=website, partner=partner)
        progress = sum(item["progress"] for item in items) / len(items) if items else 0.0
        next_item = next((item for item in items if item["progress"] < 100), False)
        return {
            "module": self,
            "module_url": self._facodi_public_path(),
            "items": items,
            "item_count": len(items),
            "progress": progress,
            "next_item": next_item,
        }


class FacodiLearningCurriculumModuleAssignment(models.Model):
    _name = "facodi.learning.curriculum.module.assignment"
    _description = "FACODI Curriculum Unit Module Assignment"
    _order = "sequence, id"

    curriculum_unit_id = fields.Many2one(
        "facodi.learning.curriculum.unit",
        required=True,
        ondelete="cascade",
        index=True,
    )
    module_id = fields.Many2one(
        "facodi.learning.curriculum.module",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10, index=True)

    _unit_module_unique = models.Constraint(
        "unique(curriculum_unit_id, module_id)",
        "A curriculum unit can include a reusable module only once.",
    )


class FacodiLearningCurriculumModuleItem(models.Model):
    _name = "facodi.learning.curriculum.module.item"
    _description = "FACODI Curriculum Module Learning Item"
    _order = "sequence, id"

    module_id = fields.Many2one(
        "facodi.learning.curriculum.module",
        required=True,
        ondelete="cascade",
        index=True,
    )
    channel_id = fields.Many2one(
        "slide.channel",
        ondelete="restrict",
        index=True,
        string="Course",
    )
    slide_id = fields.Many2one(
        "slide.slide",
        ondelete="restrict",
        index=True,
        string="Content",
    )
    sequence = fields.Integer(default=10, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_exactly_one_learning_target()
        return records

    @api.constrains("channel_id", "slide_id")
    def _check_exactly_one_learning_target(self):
        for item in self:
            if bool(item.channel_id) == bool(item.slide_id):
                raise ValidationError(
                    "A curriculum module item must reference exactly one course or content item."
                )
