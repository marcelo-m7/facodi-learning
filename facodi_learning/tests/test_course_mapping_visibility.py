from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase


class TestCourseMappingVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Course Relation Manager",
                "login": "course-relation-manager",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id,
                        ]
                    )
                ],
            }
        )
        cls.website = cls.env["website"].search([], limit=1)
        cls.other_website = cls.env["website"].create({"name": "FACODI Other Website"})

    def _course(self, name, website=None, published=True, visibility="public"):
        return self.env["slide.channel"].with_user(self.manager).create(
            {
                "name": name,
                "website_id": (website or self.website).id,
                "website_published": published,
                "visibility": visibility,
                "user_id": self.manager.id,
            }
        )

    def _mapping(self, source, target, mapping_type="related", approve=False):
        mapping = self.env["facodi.learning.course.mapping"].with_user(self.manager).create(
            {
                "source_channel_id": source.id,
                "target_channel_id": target.id,
                "mapping_type": mapping_type,
                "confidence": 0.9,
                "origin": "manual",
            }
        )
        if approve:
            mapping.action_approve()
        return mapping

    def test_only_approved_semantic_relations_are_learner_visible(self):
        source = self._course("Visible Source")
        approved = self._course("Approved Related")
        proposed = self._course("Proposed Related")
        rejected = self._course("Rejected Related")
        prerequisite = self._course("Native Prerequisite")

        self._mapping(source, approved, approve=True)
        self._mapping(source, proposed)
        self._mapping(source, rejected).action_reject()
        self._mapping(source, prerequisite, mapping_type="prerequisite", approve=True)

        visible = source.with_user(self.env.ref("base.public_user"))._facodi_related_channels(
            self.website
        )

        self.assertEqual(visible, approved.with_user(self.env.ref("base.public_user")))
        source.invalidate_recordset(["prerequisite_channel_ids"])
        self.assertIn(prerequisite, source.prerequisite_channel_ids)

    def test_unpublished_and_other_website_targets_are_hidden(self):
        source = self._course("Website Source")
        unpublished = self._course("Unpublished", published=False)
        other = self._course("Other Website", website=self.other_website)
        self._mapping(source, unpublished, approve=True)
        self._mapping(source, other, approve=True)

        public_source = source.with_user(self.env.ref("base.public_user"))

        self.assertFalse(public_source._facodi_related_channels(self.website))

    def test_native_link_visibility_is_respected(self):
        source = self._course("Public Source")
        hidden = self._course("Link Only", visibility="link")
        self._mapping(source, hidden, approve=True)

        visible = source.with_user(self.env.ref("base.public_user"))._facodi_related_channels(
            self.website
        )

        self.assertFalse(visible)

    def test_connected_visibility_respects_native_user_context(self):
        source = self._course("Connected Source")
        connected = self._course("Connected Target", visibility="connected")
        self._mapping(source, connected, approve=True)
        portal = self.env["res.users"].create(
            {
                "name": "Course Relation Portal",
                "login": "course-relation-portal",
                "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
            }
        )

        public_result = source.with_user(
            self.env.ref("base.public_user")
        )._facodi_related_channels(self.website)
        portal_result = source.with_user(portal)._facodi_related_channels(self.website)

        self.assertFalse(public_result)
        self.assertEqual(portal_result, connected.with_user(portal))

    def test_learner_does_not_gain_audit_model_access(self):
        source = self._course("Audit Source")
        target = self._course("Audit Target")
        mapping = self._mapping(source, target, approve=True)
        public_mapping = mapping.with_user(self.env.ref("base.public_user"))

        with self.assertRaises(AccessError):
            public_mapping.check_access("read")

        self.assertEqual(
            source.with_user(self.env.ref("base.public_user"))._facodi_related_channels(
                self.website
            ).ids,
            [target.id],
        )
