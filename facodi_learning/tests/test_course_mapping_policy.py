from odoo import Command
from odoo.tests import TransactionCase


class TestCourseMappingPolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Mapping Policy Manager",
                "login": "mapping-policy-manager",
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
                "name": "Mapping Policy Officer",
                "login": "mapping-policy-officer",
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
        cls.source = cls.env["slide.channel"].create(
            {"name": "Policy Source", "user_id": cls.officer.id}
        )
        cls.target = cls.env["slide.channel"].create({"name": "Policy Target"})

    def setUp(self):
        super().setUp()
        params = self.env["ir.config_parameter"].sudo()
        for key in (
            "facodi_learning.course_mapping_mode",
            "facodi_learning.course_mapping_auto_types",
            "facodi_learning.course_mapping_min_confidence",
        ):
            params.search([("key", "=", key)]).unlink()

    def _policy(self):
        from odoo.addons.facodi_learning.services.course_mapping_policy import (
            get_course_mapping_policy,
        )

        return get_course_mapping_policy(self.env)

    def _mapping(self, mapping_type="related", confidence=0.90, user=None):
        user = user or self.manager
        return self.env["facodi.learning.course.mapping"].with_user(user).create(
            {
                "source_channel_id": self.source.id,
                "target_channel_id": self.target.id,
                "mapping_type": mapping_type,
                "confidence": confidence,
                "origin": "analysis",
                "ranking_version": "course-mapping-v1",
            }
        )

    def _set_auto(self, types="related", threshold="0.85"):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("facodi_learning.course_mapping_mode", "auto")
        params.set_param("facodi_learning.course_mapping_auto_types", types)
        params.set_param("facodi_learning.course_mapping_min_confidence", threshold)

    def test_mapping_policy_defaults_to_manual(self):
        policy = self._policy()

        self.assertEqual(policy["mode"], "manual")
        self.assertEqual(policy["auto_types"], {"related"})
        self.assertEqual(policy["min_confidence"], 0.85)
        self.assertEqual(policy["policy_version"], "course-mapping-policy-v1")

    def test_related_can_auto_approve_above_threshold_for_manager(self):
        self._set_auto()
        mapping = self._mapping().with_user(self.manager)

        self.assertTrue(mapping._maybe_auto_approve())
        mapping.invalidate_recordset()

        self.assertEqual(mapping.state, "approved")
        self.assertFalse(mapping.reviewed_by_id)
        self.assertTrue(mapping.reviewed_at)
        self.assertEqual(mapping.policy_version, "course-mapping-policy-v1")

    def test_complements_can_auto_approve_when_configured(self):
        self._set_auto(types="related,complements")
        mapping = self._mapping(mapping_type="complements").with_user(self.manager)

        self.assertTrue(mapping._maybe_auto_approve())
        mapping.invalidate_recordset()

        self.assertEqual(mapping.state, "approved")

    def test_alternative_equivalent_continuation_never_auto_approve(self):
        self._set_auto(types="related,complements,alternative,equivalent,continuation")

        for mapping_type in ("alternative", "equivalent", "continuation"):
            mapping = self._mapping(mapping_type=mapping_type).with_user(self.manager)
            self.assertFalse(mapping._maybe_auto_approve())
            mapping.invalidate_recordset()
            self.assertEqual(mapping.state, "proposed")

    def test_prerequisite_never_auto_approves(self):
        self._set_auto(types="related,complements,prerequisite")
        mapping = self._mapping(mapping_type="prerequisite").with_user(self.manager)

        self.assertFalse(mapping._maybe_auto_approve())
        mapping.invalidate_recordset()

        self.assertEqual(mapping.state, "proposed")
        self.source.invalidate_recordset(["prerequisite_channel_ids"])
        self.assertNotIn(self.target, self.source.prerequisite_channel_ids)

    def test_officer_context_never_escalates_to_auto_approve(self):
        self._set_auto()
        mapping = self._mapping(user=self.officer).with_user(self.officer)

        self.assertFalse(mapping._maybe_auto_approve())
        mapping.invalidate_recordset()

        self.assertEqual(mapping.state, "proposed")
        self.assertFalse(mapping.reviewed_by_id)

    def test_auto_decision_snapshot_is_immutable(self):
        self._set_auto(types="related,complements", threshold="0.80")
        mapping = self._mapping(confidence=0.91).with_user(self.manager)

        self.assertTrue(mapping._maybe_auto_approve())
        mapping.invalidate_recordset()
        initial = dict(mapping.decision_snapshot)

        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_learning.course_mapping_min_confidence", "0.99"
        )
        mapping.invalidate_recordset()

        self.assertEqual(mapping.decision_snapshot, initial)
        self.assertEqual(initial["confidence"], 0.91)
        self.assertEqual(initial["mapping_type"], "related")
        self.assertEqual(initial["ranking_version"], "course-mapping-v1")
        self.assertEqual(initial["min_confidence"], 0.80)
        self.assertEqual(initial["auto_types"], ["complements", "related"])
        self.assertEqual(initial["policy_version"], "course-mapping-policy-v1")

    def test_manager_generation_applies_auto_approve_policy(self):
        self._set_auto(types="related", threshold="0.80")
        group = self.env["slide.channel.tag.group"].create({"name": "Policy Topic"})
        tag = self.env["slide.channel.tag"].create(
            {"name": "Policy Shared", "group_id": group.id}
        )
        source = self.env["slide.channel"].with_user(self.manager).create(
            {
                "name": "Integration Mapping Course",
                "user_id": self.manager.id,
                "tag_ids": [Command.link(tag.id)],
            }
        )
        target = self.env["slide.channel"].with_user(self.manager).create(
            {
                "name": "Integration Mapping Course Advanced",
                "tag_ids": [Command.link(tag.id)],
            }
        )

        proposals = source.with_user(self.manager)._facodi_propose_course_mappings(limit=20)
        mapping = proposals.filtered(lambda row: row.target_channel_id == target)

        self.assertTrue(mapping)
        self.assertEqual(mapping.state, "approved")
        self.assertFalse(mapping.reviewed_by_id)
        self.assertEqual(mapping.policy_version, "course-mapping-policy-v1")
