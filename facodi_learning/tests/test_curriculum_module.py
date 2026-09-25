from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCurriculumModule(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.reference = cls.env["facodi.learning.curriculum.reference"].create(
            {
                "institution": "FACODI Test Institute",
                "programme_name": "Applied Learning",
                "academic_year": "2026/27",
                "provider": "test",
                "external_id": "module-composition",
            }
        )
        cls.unit_a = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "TEST-UC-A",
                "name": "Curricular Unit A",
                "curricular_year": 1,
                "classification": "mandatory",
            }
        )
        cls.unit_b = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "TEST-UC-B",
                "name": "Curricular Unit B",
                "curricular_year": 1,
                "classification": "mandatory",
            }
        )
        cls.course_a = cls.env["slide.channel"].create(
            {
                "name": "Reusable Course A",
                "is_published": True,
                "website_published": True,
                "website_id": cls.website.id,
            }
        )
        cls.course_b = cls.env["slide.channel"].create(
            {"name": "Reusable Course B", "is_published": True}
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Module Manager",
                "login": "module-manager",
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
        cls.published_slide = cls.env["slide.slide"].create(
            {
                "channel_id": cls.course_a.id,
                "name": "Published Resource",
                "slide_category": "document",
                "is_preview": True,
            }
        )
        review = cls.env["facodi.learning.content.review"].create(
            {
                "slide_id": cls.published_slide.id,
                "author": "FACODI fixture",
                "rights_mode": "original",
                "usage_basis": "Test fixture content authored for FACODI.",
                "purpose": "Exercise public curriculum module projection.",
            }
        )
        review.with_user(cls.manager).action_approve()
        cls.published_slide.write(
            {"is_published": True, "website_published": True}
        )
        cls.unpublished_slide = cls.env["slide.slide"].create(
            {
                "channel_id": cls.course_a.id,
                "name": "Unpublished Resource",
                "slide_category": "document",
                "is_published": False,
            }
        )

    def _module(self, name="Reusable Module"):
        return self.env["facodi.learning.curriculum.module"].create(
            {"name": name, "website_published": True}
        )

    def _publish_reference(self):
        self.reference.with_user(self.manager).action_validate()
        self.reference.with_user(self.manager).action_publish()


    def test_public_module_view_keeps_progress_model_backed(self):
        view = self.env.ref("facodi_learning.curriculum_public_module")
        self.assertIn("facodi-module-detail", view.arch_db)
        self.assertIn("show_learning_progress", view.arch_db)
        self.assertIn("module_row['progress']", view.arch_db)
        self.assertIn("module_row['next_item']", view.arch_db)
        self.assertNotIn("module_row_index", view.arch_db)

    def test_unit_can_order_multiple_modules(self):
        first = self._module("First Module")
        second = self._module("Second Module")
        Assignment = self.env["facodi.learning.curriculum.module.assignment"]
        Assignment.create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": second.id, "sequence": 20}
        )
        Assignment.create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": first.id, "sequence": 10}
        )

        assignments = Assignment.search(
            [("curriculum_unit_id", "=", self.unit_a.id)], order="sequence, id"
        )
        self.assertEqual(assignments.mapped("module_id"), first | second)

    def test_module_is_reusable_by_multiple_curricular_units(self):
        module = self._module()
        Assignment = self.env["facodi.learning.curriculum.module.assignment"]
        Assignment.create({"curriculum_unit_id": self.unit_a.id, "module_id": module.id})
        Assignment.create({"curriculum_unit_id": self.unit_b.id, "module_id": module.id})

        self.assertEqual(module.assignment_ids.mapped("curriculum_unit_id"), self.unit_a | self.unit_b)

    def test_module_can_reference_courses_and_individual_content(self):
        module = self._module()
        Item = self.env["facodi.learning.curriculum.module.item"]
        course_item = Item.create({"module_id": module.id, "channel_id": self.course_a.id})
        slide_item = Item.create({"module_id": module.id, "slide_id": self.published_slide.id})

        self.assertEqual(course_item.channel_id, self.course_a)
        self.assertEqual(slide_item.slide_id, self.published_slide)
        self.assertFalse(course_item.slide_id)
        self.assertFalse(slide_item.channel_id)

    def test_course_can_be_reused_by_different_modules(self):
        Item = self.env["facodi.learning.curriculum.module.item"]
        first = self._module("Module One")
        second = self._module("Module Two")
        Item.create({"module_id": first.id, "channel_id": self.course_a.id})
        Item.create({"module_id": second.id, "channel_id": self.course_a.id})

        self.assertEqual(
            Item.search_count([("channel_id", "=", self.course_a.id)]), 2
        )

    def test_item_requires_exactly_one_existing_target(self):
        module = self._module()
        Item = self.env["facodi.learning.curriculum.module.item"]
        with self.assertRaises(ValidationError):
            Item.create({"module_id": module.id})
        with self.assertRaises(ValidationError):
            Item.create(
                {
                    "module_id": module.id,
                    "channel_id": self.course_a.id,
                    "slide_id": self.published_slide.id,
                }
            )

    def test_module_without_items_and_unit_without_modules_are_valid(self):
        module = self._module("Empty Module")
        self.assertFalse(module.item_ids)
        self.assertFalse(
            self.env["facodi.learning.curriculum.module.assignment"].search(
                [("curriculum_unit_id", "=", self.unit_a.id)]
            )
        )

    def test_public_user_cannot_read_module_authoring_models(self):
        module = self._module()
        public = self.env.ref("base.public_user")
        with self.assertRaises(AccessError):
            module.with_user(public).read(["name"])

    def test_coverage_remains_independent_from_module_composition(self):
        module = self._module()
        self.env["facodi.learning.curriculum.module.assignment"].create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": module.id}
        )
        self.env["facodi.learning.curriculum.module.item"].create(
            {"module_id": module.id, "channel_id": self.course_a.id}
        )

        self.assertFalse(
            self.env["facodi.learning.curriculum.coverage"].search(
                [
                    ("curriculum_unit_id", "=", self.unit_a.id),
                    ("channel_id", "=", self.course_a.id),
                ]
            )
        )

    def test_public_projection_excludes_unpublished_content(self):
        self._publish_reference()
        module = self._module()
        self.env["facodi.learning.curriculum.module.assignment"].create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": module.id}
        )
        Item = self.env["facodi.learning.curriculum.module.item"]
        Item.create({"module_id": module.id, "slide_id": self.published_slide.id})
        Item.create({"module_id": module.id, "slide_id": self.unpublished_slide.id})

        rows = self.unit_a._facodi_public_module_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_count"], 1)
        self.assertEqual(rows[0]["items"][0]["record"], self.published_slide)

    def test_public_projection_excludes_published_non_preview_content(self):
        self._publish_reference()
        module = self._module("Preview Boundary Module")
        self.env["facodi.learning.curriculum.module.assignment"].create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": module.id}
        )
        non_preview_slide = self.env["slide.slide"].create(
            {
                "channel_id": self.course_a.id,
                "name": "Members Only Resource",
                "slide_category": "document",
                "is_preview": False,
            }
        )
        review = self.env["facodi.learning.content.review"].create(
            {
                "slide_id": non_preview_slide.id,
                "author": "FACODI fixture",
                "rights_mode": "original",
                "usage_basis": "Test fixture content authored for FACODI.",
                "purpose": "Exercise private curriculum module projection.",
            }
        )
        review.with_user(self.manager).action_approve()
        non_preview_slide.write(
            {"is_published": True, "website_published": True}
        )
        self.env["facodi.learning.curriculum.module.item"].create(
            {"module_id": module.id, "slide_id": non_preview_slide.id}
        )

        public = self.env.ref("base.public_user")
        rows = self.unit_a.sudo()._facodi_public_module_rows(
            website=self.website.with_user(public)
        )

        self.assertEqual(rows[0]["item_count"], 0)
        self.assertFalse(rows[0]["items"])

    def test_public_user_can_project_published_module_items(self):
        self._publish_reference()
        module = self._module("Public Projection Module")
        self.env["facodi.learning.curriculum.module.assignment"].create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": module.id}
        )
        self.env["facodi.learning.curriculum.module.item"].create(
            {"module_id": module.id, "slide_id": self.published_slide.id}
        )

        public = self.env.ref("base.public_user")
        rows = self.unit_a.sudo()._facodi_public_module_rows(
            website=self.website.with_user(public)
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["items"][0]["record"], self.published_slide)

    def test_sudo_editorial_module_uses_public_website_visibility(self):
        self._publish_reference()
        module = self._module("Sudo Public Projection Module")
        self.env["facodi.learning.curriculum.module.assignment"].create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": module.id}
        )
        self.env["facodi.learning.curriculum.module.item"].create(
            {"module_id": module.id, "slide_id": self.published_slide.id}
        )

        public = self.env.ref("base.public_user")
        rows = self.unit_a.sudo()._facodi_public_module_rows(
            website=self.website.with_user(public)
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["items"][0]["record"], self.published_slide)

    def test_projection_uses_existing_course_membership_progress(self):
        self._publish_reference()
        module = self._module()
        self.env["facodi.learning.curriculum.module.assignment"].create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": module.id}
        )
        self.env["facodi.learning.curriculum.module.item"].create(
            {"module_id": module.id, "channel_id": self.course_a.id}
        )
        learner = self.env["res.users"].create(
            {"name": "Module Learner", "login": "module-learner"}
        )
        membership_values = {
            "channel_id": self.course_a.id,
            "partner_id": learner.partner_id.id,
        }
        if "completion" in self.env["slide.channel.partner"]._fields:
            membership_values["completion"] = 50.0
        self.env["slide.channel.partner"].create(membership_values)

        projection = self.unit_a._facodi_public_learning_projection(
            partner=learner.partner_id
        )
        expected = 50.0 if "completion" in self.env["slide.channel.partner"]._fields else 0.0
        self.assertEqual(projection["progress"], expected)
        self.assertEqual(projection["next_item"]["record"], self.course_a)

    def test_projection_does_not_double_count_a_slide_included_by_its_course(self):
        self._publish_reference()
        module = self._module("Deduplicated Module")
        self.env["facodi.learning.curriculum.module.item"].create(
            {"module_id": module.id, "channel_id": self.course_a.id}
        )
        self.env["facodi.learning.curriculum.module.item"].create(
            {"module_id": module.id, "slide_id": self.published_slide.id}
        )

        projection = module._facodi_public_projection()

        self.assertEqual(projection["item_count"], 1)
        self.assertEqual(projection["items"][0]["record"], self.course_a)

    def test_unit_projection_keeps_unknown_progress_unavailable(self):
        self._publish_reference()
        module = self._module("Unknown Progress Module")
        self.env["facodi.learning.curriculum.module.assignment"].create(
            {"curriculum_unit_id": self.unit_a.id, "module_id": module.id}
        )
        self.env["facodi.learning.curriculum.module.item"].create(
            {"module_id": module.id, "channel_id": self.course_a.id}
        )

        projection = self.unit_a._facodi_public_learning_projection()

        self.assertIsNone(projection["progress"])
        self.assertEqual(projection["next_item"]["record"], self.course_a)