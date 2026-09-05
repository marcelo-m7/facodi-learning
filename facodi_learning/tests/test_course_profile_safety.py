from odoo import Command
from odoo.tests import TransactionCase


class TestCourseProfileSafety(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Course Profile Safety Manager",
                "login": "course-profile-safety-manager",
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
        cls.Channel = cls.env["slide.channel"].with_user(cls.manager)
        cls.Slide = cls.env["slide.slide"].with_user(cls.manager)

    def test_profile_is_independent_from_learner_membership(self):
        channel = self.Channel.create({"name": "Privacy Course"})
        self.Slide.create(
            {
                "name": "Lesson",
                "channel_id": channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        before = channel._facodi_course_profile()
        learner = self.env["res.partner"].create(
            {"name": "Profile Learner", "email": "learner@example.invalid"}
        )
        self.env["slide.channel.partner"].with_user(self.manager).create(
            {"channel_id": channel.id, "partner_id": learner.id}
        )
        channel.invalidate_recordset()
        after = channel._facodi_course_profile()

        self.assertEqual(before, after)
        serialized = repr(after)
        self.assertNotIn("learner@example.invalid", serialized)
        forbidden_keys = {
            "partner_ids",
            "channel_partner_ids",
            "members_count",
            "completion",
            "completed",
            "is_member",
            "user_has_completed",
        }
        self.assertTrue(forbidden_keys.isdisjoint(after.keys()))
        self.assertTrue(forbidden_keys.isdisjoint(after["channel"].keys()))

    def test_profile_generation_does_not_write_course_or_content(self):
        channel = self.Channel.create({"name": "Read Only Profile"})
        slide = self.Slide.create(
            {
                "name": "Lesson",
                "channel_id": channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        channel.flush_recordset()
        slide.flush_recordset()
        channel_write_date = channel.write_date
        slide_write_date = slide.write_date

        channel._facodi_course_profile()
        channel.invalidate_recordset()
        slide.invalidate_recordset()

        self.assertEqual(channel.write_date, channel_write_date)
        self.assertEqual(slide.write_date, slide_write_date)

    def test_internal_profile_includes_current_unpublished_content(self):
        channel = self.Channel.create({"name": "Draft Course"})
        published = self.Slide.create(
            {
                "name": "Published",
                "channel_id": channel.id,
                "slide_category": "article",
                "slide_type": "article",
                "is_published": True,
            }
        )
        draft = self.Slide.create(
            {
                "name": "Draft",
                "channel_id": channel.id,
                "slide_category": "article",
                "slide_type": "article",
                "is_published": False,
            }
        )

        profile = channel._facodi_course_profile()

        self.assertEqual(
            {item["id"] for item in profile["contents"]},
            {published.id, draft.id},
        )
