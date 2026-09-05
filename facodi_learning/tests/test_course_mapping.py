from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCourseMapping(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Course Mapping Manager",
                "login": "course-mapping-manager",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Course Mapping Officer",
                "login": "course-mapping-officer",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.portal = cls.env["res.users"].create(
            {
                "name": "Course Mapping Portal",
                "login": "course-mapping-portal",
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )
        cls.source = cls.env["slide.channel"].create(
            {"name": "Source Course", "user_id": cls.officer.id}
        )
        cls.target = cls.env["slide.channel"].create({"name": "Target Course"})

    def _values(self, **extra):
        values = {
            "source_channel_id": self.source.id,
            "target_channel_id": self.target.id,
            "mapping_type": "related",
            "confidence": 0.75,
        }
        values.update(extra)
        return values

    def test_course_mapping_model_exists(self):
        self.assertIn("facodi.learning.course.mapping", self.env.registry.models)

    def test_course_mapping_has_audit_schema(self):
        Mapping = self.env["facodi.learning.course.mapping"]
        expected_fields = {
            "source_channel_id",
            "target_channel_id",
            "mapping_type",
            "confidence",
            "origin",
            "state",
            "evidence",
            "ranking_version",
            "reviewed_by_id",
            "reviewed_at",
            "policy_version",
            "decision_snapshot",
            "native_applied_by_id",
            "native_applied_at",
        }
        self.assertTrue(expected_fields <= set(Mapping._fields))

    def test_course_mapping_rejects_self_relation(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["facodi.learning.course.mapping"].create(
                self._values(target_channel_id=self.source.id)
            )

    def test_course_mapping_rejects_confidence_outside_zero_one(self):
        Mapping = self.env["facodi.learning.course.mapping"]
        for confidence in (-0.01, 1.01):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                Mapping.create(self._values(confidence=confidence))

    def test_course_mapping_unique_directed_triple(self):
        Mapping = self.env["facodi.learning.course.mapping"]
        Mapping.create(self._values())
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            Mapping.create(self._values())

    def test_direct_terminal_evidence_is_rejected_on_create(self):
        Mapping = self.env["facodi.learning.course.mapping"]
        for forged in (
            {"state": "approved"},
            {"reviewed_by_id": self.manager.id},
            {"policy_version": "forged-policy"},
        ):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                Mapping.create(self._values(**forged))

    def test_direct_generated_provenance_is_rejected_on_create(self):
        Mapping = self.env["facodi.learning.course.mapping"].with_user(self.officer)
        for forged in (
            {"origin": "analysis"},
            {"ranking_version": "forged-ranking"},
            {
                "origin": "analysis",
                "ranking_version": "forged-ranking",
                "evidence": {"signals": {"title_overlap": 1.0}},
            },
        ):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                Mapping.create(self._values(**forged))

    def test_generated_proposal_ranking_evidence_is_immutable(self):
        mapping = self.env["facodi.learning.course.mapping"]._create_generated(
            self._values(
                confidence=0.81,
                ranking_version="course-mapping-v1",
                evidence={"signals": {"title_overlap": 0.7}},
            )
        )

        for user in (self.officer, self.manager):
            for values in (
                {"confidence": 0.99},
                {"evidence": {"signals": {"title_overlap": 1.0}}},
            ):
                with self.assertRaises(AccessError):
                    mapping.with_user(user).write(values)

        mapping.invalidate_recordset()
        self.assertEqual(mapping.confidence, 0.81)
        self.assertEqual(mapping.evidence, {"signals": {"title_overlap": 0.7}})

    def test_manager_can_approve_semantic_relation(self):
        mapping = self.env["facodi.learning.course.mapping"].create(self._values())
        self.assertTrue(hasattr(mapping, "action_approve"))
        mapping.with_user(self.manager).action_approve()
        mapping.invalidate_recordset()
        self.assertEqual(mapping.state, "approved")
        self.assertEqual(mapping.reviewed_by_id, self.manager)
        self.assertTrue(mapping.reviewed_at)

    def test_officer_cannot_review(self):
        mapping = self.env["facodi.learning.course.mapping"].create(self._values())
        self.assertTrue(hasattr(mapping, "action_approve"))
        with self.assertRaises(AccessError):
            mapping.with_user(self.officer).action_approve()

    def test_officer_can_create_mapping_for_owned_source_course(self):
        try:
            mapping = self.env["facodi.learning.course.mapping"].with_user(
                self.officer
            ).create(self._values())
        except AccessError as error:
            self.fail(f"Officer should be able to create an owned proposal: {error}")
        self.assertEqual(mapping.state, "proposed")
        self.assertEqual(mapping.origin, "manual")
        self.assertFalse(mapping.ranking_version)

    def test_public_and_portal_cannot_read_course_mapping(self):
        Mapping = self.env["facodi.learning.course.mapping"]
        for user in (self.env.ref("base.public_user"), self.portal):
            with self.assertRaises(AccessError):
                Mapping.with_user(user).search([])
