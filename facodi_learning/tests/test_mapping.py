from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestFacodiLearningMapping(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["slide.channel"].create({"name": "FACODI Mapping Course"})
        cls.source = cls.env["slide.slide"].create({
            "name": "Source",
            "channel_id": cls.channel.id,
            "slide_category": "article",
        })
        cls.target = cls.env["slide.slide"].create({
            "name": "Target",
            "channel_id": cls.channel.id,
            "slide_category": "article",
        })

    def test_source_and_target_must_differ(self):
        with self.assertRaises(ValidationError):
            self.env["facodi.learning.mapping"].create({
                "source_slide_id": self.source.id,
                "target_slide_id": self.source.id,
                "mapping_type": "related",
            })

    def test_only_elearning_manager_can_review_mapping(self):
        mapping = self.env["facodi.learning.mapping"].create({
            "source_slide_id": self.source.id,
            "target_slide_id": self.target.id,
            "mapping_type": "related",
            "origin": "analysis",
        })
        self.assertEqual(mapping.state, "proposed")

        officer_group = self.env.ref("website_slides.group_website_slides_officer")
        officer = self.env["res.users"].create({
            "name": "Learning Officer",
            "login": "learning-officer",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id, officer_group.id])],
        })
        with self.assertRaises(AccessError):
            mapping.with_user(officer).action_approve()

        mapping.action_approve()
        self.assertEqual(mapping.state, "approved")
        self.assertEqual(mapping.reviewed_by_id, self.env.user)
        self.assertTrue(mapping.reviewed_at)
