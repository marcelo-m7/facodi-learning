from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCourseMappingPrerequisite(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Prerequisite Manager",
                "login": "prerequisite-manager",
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
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Prerequisite Officer",
                "login": "prerequisite-officer",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id,
                        ]
                    )
                ],
            }
        )

    def _channel(self, name, **extra):
        vals = {"name": name}
        vals.update(extra)
        return self.env["slide.channel"].create(vals)

    def _mapping(self, source, target):
        return self.env["facodi.learning.course.mapping"].create(
            {
                "source_channel_id": source.id,
                "target_channel_id": target.id,
                "mapping_type": "prerequisite",
                "confidence": 1.0,
                "origin": "manual",
            }
        )

    def test_prerequisite_approval_writes_native_odoo_field(self):
        source = self._channel("Advanced Databases")
        target = self._channel("Database Foundations")
        mapping = self._mapping(source, target).with_user(self.manager)

        mapping.action_approve()
        source.invalidate_recordset(["prerequisite_channel_ids"])
        mapping.invalidate_recordset()

        self.assertIn(target, source.prerequisite_channel_ids)
        self.assertEqual(mapping.state, "approved")
        self.assertEqual(mapping.native_applied_by_id, self.manager)
        self.assertTrue(mapping.native_applied_at)

    def test_prerequisite_mapping_record_is_audit_not_second_truth(self):
        source = self._channel("Algorithms II")
        target = self._channel("Algorithms I")
        mapping = self._mapping(source, target).with_user(self.manager)

        mapping.action_approve()
        source.invalidate_recordset(["prerequisite_channel_ids"])

        self.assertIn(target, source.prerequisite_channel_ids)
        self.assertNotIn("facodi_prerequisite_channel_ids", source._fields)
        self.assertEqual(mapping.source_channel_id, source)
        self.assertEqual(mapping.target_channel_id, target)

    def test_prerequisite_cycle_is_rejected(self):
        source = self._channel("Course A")
        target = self._channel(
            "Course B", prerequisite_channel_ids=[Command.link(source.id)]
        )
        mapping = self._mapping(source, target).with_user(self.manager)

        with self.assertRaises(ValidationError):
            mapping.action_approve()

        source.invalidate_recordset(["prerequisite_channel_ids"])
        mapping.invalidate_recordset()
        self.assertNotIn(target, source.prerequisite_channel_ids)
        self.assertEqual(mapping.state, "proposed")

    def test_prerequisite_three_node_cycle_is_rejected(self):
        source = self._channel("Course A")
        middle = self._channel(
            "Course C", prerequisite_channel_ids=[Command.link(source.id)]
        )
        target = self._channel(
            "Course B", prerequisite_channel_ids=[Command.link(middle.id)]
        )
        mapping = self._mapping(source, target).with_user(self.manager)

        with self.assertRaises(ValidationError):
            mapping.action_approve()

        source.invalidate_recordset(["prerequisite_channel_ids"])
        self.assertNotIn(target, source.prerequisite_channel_ids)

    def test_prerequisite_approval_is_idempotent_when_native_link_exists(self):
        target = self._channel("Existing Prerequisite")
        source = self._channel(
            "Existing Consumer",
            prerequisite_channel_ids=[Command.link(target.id)],
        )
        mapping = self._mapping(source, target).with_user(self.manager)

        mapping.action_approve()
        source.invalidate_recordset(["prerequisite_channel_ids"])
        mapping.invalidate_recordset()

        self.assertEqual(source.prerequisite_channel_ids.ids.count(target.id), 1)
        self.assertEqual(mapping.state, "approved")
        self.assertEqual(mapping.native_applied_by_id, self.manager)

    def test_officer_cannot_apply_native_prerequisite(self):
        source = self._channel("Officer Source", user_id=self.officer.id)
        target = self._channel("Officer Target")
        mapping = self._mapping(source, target).with_user(self.officer)

        with self.assertRaises(AccessError):
            mapping.action_approve()

        source.invalidate_recordset(["prerequisite_channel_ids"])
        self.assertNotIn(target, source.prerequisite_channel_ids)
