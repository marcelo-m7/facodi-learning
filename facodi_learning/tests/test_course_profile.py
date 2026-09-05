from odoo import Command
from odoo.tests import TransactionCase


class TestCourseProfile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Course Profile Manager",
                "login": "course-profile-manager",
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
        cls.ProfileChannel = cls.env["slide.channel"].with_user(cls.manager)
        cls.ProfileSlide = cls.env["slide.slide"].with_user(cls.manager)

    def _profile(self, channel):
        self.assertTrue(
            hasattr(channel, "_facodi_course_profile"),
            "M3.2 requires slide.channel._facodi_course_profile()",
        )
        return channel._facodi_course_profile()

    def test_empty_course_profile_has_stable_schema(self):
        channel = self.ProfileChannel.create({"name": "Empty Course"})

        profile = self._profile(channel)

        self.assertEqual(profile["schema_version"], "course-profile-v1")
        self.assertEqual(profile["channel"]["id"], channel.id)
        self.assertEqual(profile["channel"]["name"], "Empty Course")
        self.assertEqual(profile["course_tags"], [])
        self.assertEqual(profile["prerequisite_channel_ids"], [])
        self.assertEqual(profile["structure"]["section_count"], 0)
        self.assertEqual(profile["structure"]["content_count"], 0)
        self.assertEqual(
            profile["structure"]["category_counts"],
            {
                "article": 0,
                "document": 0,
                "infographic": 0,
                "quiz": 0,
                "video": 0,
            },
        )
        self.assertEqual(profile["sections"], [])
        self.assertEqual(profile["contents"], [])
        self.assertEqual(
            profile["analysis"],
            {"analyzed_content_count": 0, "detected_languages": []},
        )
        self.assertEqual(
            profile["approved_content_relations"],
            {"outgoing": [], "incoming": []},
        )

    def test_profile_aggregates_standard_course_and_content_metadata(self):
        tag_group = self.env["slide.channel.tag.group"].create({"name": "Topic"})
        course_tag = self.env["slide.channel.tag"].create(
            {"name": "Databases", "group_id": tag_group.id}
        )
        content_tag = self.env["slide.tag"].create({"name": "SQL"})
        prerequisite = self.ProfileChannel.create({"name": "Programming"})
        channel = self.ProfileChannel.create(
            {
                "name": "Databases",
                "description": "<p>Relational foundations</p>",
                "description_short": "<p>DB basics</p>",
                "description_html": "<p>Detailed DB material</p>",
                "tag_ids": [Command.link(course_tag.id)],
                "prerequisite_channel_ids": [Command.link(prerequisite.id)],
            }
        )
        section = self.ProfileSlide.create(
            {
                "name": "Foundations",
                "channel_id": channel.id,
                "is_category": True,
                "sequence": 10,
            }
        )
        article = self.ProfileSlide.create(
            {
                "name": "Relational Model",
                "channel_id": channel.id,
                "slide_category": "article",
                "slide_type": "article",
                "sequence": 20,
                "completion_time": 0.5,
                "tag_ids": [Command.link(content_tag.id)],
            }
        )
        quiz = self.ProfileSlide.create(
            {
                "name": "SQL Quiz",
                "channel_id": channel.id,
                "slide_category": "quiz",
                "slide_type": "quiz",
                "sequence": 30,
                "completion_time": 1.0,
            }
        )

        profile = self._profile(channel)

        self.assertEqual(profile["channel"]["description"], "Relational foundations")
        self.assertEqual(profile["channel"]["short_description"], "DB basics")
        self.assertEqual(
            profile["channel"]["detailed_description"], "Detailed DB material"
        )
        self.assertEqual(profile["course_tags"][0]["name"], "Databases")
        self.assertEqual(profile["course_tags"][0]["group_name"], "Topic")
        self.assertEqual(profile["prerequisite_channel_ids"], [prerequisite.id])
        self.assertEqual(profile["structure"]["section_count"], 1)
        self.assertEqual(profile["structure"]["content_count"], 2)
        self.assertEqual(profile["structure"]["category_counts"]["article"], 1)
        self.assertEqual(profile["structure"]["category_counts"]["quiz"], 1)
        self.assertEqual(profile["sections"][0]["id"], section.id)
        self.assertEqual(profile["sections"][0]["content_ids"], [article.id, quiz.id])
        self.assertEqual(profile["contents"][0]["tag_names"], ["SQL"])

    def test_profile_output_is_deterministic(self):
        channel = self.ProfileChannel.create({"name": "Deterministic Course"})
        second = self.ProfileSlide.create(
            {
                "name": "B",
                "channel_id": channel.id,
                "sequence": 20,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        first = self.ProfileSlide.create(
            {
                "name": "A",
                "channel_id": channel.id,
                "sequence": 10,
                "slide_category": "article",
                "slide_type": "article",
            }
        )

        initial = self._profile(channel)
        channel.invalidate_recordset()
        repeated = self._profile(channel)

        self.assertEqual(initial, repeated)
        self.assertEqual(
            [item["id"] for item in initial["contents"]], [first.id, second.id]
        )
