from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def facodi_home_field_notebook(self):
        """Two actual, public records for the homepage's field notebook."""
        self.ensure_one()
        course = self.env['slide.channel'].search([
            ('active', '=', True), ('website_published', '=', True),
            ('visibility', '=', 'public'), ('is_visible', '=', True), '|',
            ('website_id', '=', False), ('website_id', '=', self.id),
        ], order='write_date desc, id desc', limit=1)
        reference = self.env['facodi.learning.curriculum.reference'].sudo().search([
            ('website_published', '=', True), ('validated_at', '!=', False),
        ], order='validated_at desc, id desc', limit=1)
        return {'course': course, 'reference': reference}
