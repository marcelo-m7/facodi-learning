from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('-at_install', 'post_install')
class TestHomeFieldNotebook(TransactionCase):
    def setUp(self):
        super().setUp()
        self.website = self.env['website'].search([], limit=1)
        self.env['slide.channel'].search([]).write({'website_published': False})
        self.env['facodi.learning.curriculum.reference'].search([]).write({'website_published': False})

    def test_empty_catalogue_returns_no_invented_records(self):
        result = self.website.facodi_home_field_notebook()
        self.assertFalse(result['course'])
        self.assertFalse(result['reference'])

    def test_private_unpublished_and_other_website_courses_are_excluded(self):
        Channel = self.env['slide.channel']
        course = Channel.create({'name': 'Public notebook course', 'website_id': self.website.id, 'visibility': 'public', 'website_published': True})
        Channel.create({'name': 'Private notebook course', 'website_id': self.website.id, 'visibility': 'members', 'website_published': True})
        Channel.create({'name': 'Unpublished notebook course', 'website_id': self.website.id, 'visibility': 'public'})
        other = self.env['website'].create({'name': 'Other campus'})
        Channel.create({'name': 'Other website course', 'website_id': other.id, 'visibility': 'public', 'website_published': True})
        self.assertEqual(self.website.facodi_home_field_notebook()['course'], course)

    def test_only_published_validated_references_are_exposed(self):
        Reference = self.env['facodi.learning.curriculum.reference']
        base = {'institution': 'Test campus', 'programme_name': 'Real programme', 'academic_year': '2026', 'source_url': 'https://example.org/programme'}
        reference = Reference.create({**base, 'external_id': 'notebook-valid', 'website_published': True, 'validated_at': fields.Datetime.now()})
        Reference.create({**base, 'external_id': 'notebook-unreviewed', 'website_published': True})
        Reference.create({**base, 'external_id': 'notebook-unpublished', 'validated_at': fields.Datetime.now()})
        self.assertEqual(self.website.facodi_home_field_notebook()['reference'], reference)
