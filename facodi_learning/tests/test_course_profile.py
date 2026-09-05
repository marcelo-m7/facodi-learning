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

    def _record_analysis_result(self, slide, detected_language):
        job = self.env["facodi.learning.analysis.job"].create(
            {"slide_id": slide.id, "provider": "local_metadata"}
        )
        return self.env["facodi.learning.analysis.result"]._record_output(
            {
                "job_id": job.id,
                "slide_id": slide.id,
                "provider": "local_metadata",
                "model_name": "profile-test",
                "summary": "Internal generated summary",
                "detected_language": detected_language,
                "transcript": "Internal transcript",
                "raw_payload": {"secret_like_field": "must-not-escape"},
                "suggested_tags": [],
                "proposed_mappings": [],
            }
        )

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

    def test_profile_uses_latest_language_signal_without_raw_analysis_output(self):
        channel = self.ProfileChannel.create({"name": "Languages"})
        analyzed = self.ProfileSlide.create(
            {
                "name": "Analyzed",
                "channel_id": channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        self.ProfileSlide.create(
            {
                "name": "Not analyzed",
                "channel_id": channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        self._record_analysis_result(analyzed, "en")
        self._record_analysis_result(analyzed, "pt")

        profile = self._profile(channel)

        self.assertEqual(profile["analysis"]["analyzed_content_count"], 1)
        self.assertEqual(profile["analysis"]["detected_languages"], ["pt"])
        serialized = repr(profile)
        self.assertNotIn("Internal generated summary", serialized)
        self.assertNotIn("Internal transcript", serialized)
        self.assertNotIn("secret_like_field", serialized)

    def test_profile_aggregates_only_approved_content_relations(self):
        source_channel = self.ProfileChannel.create({"name": "Source"})
        target_channel = self.ProfileChannel.create({"name": "Target"})
        incoming_channel = self.ProfileChannel.create({"name": "Incoming"})
        source = self.ProfileSlide.create(
            {
                "name": "Source Content",
                "channel_id": source_channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        approved_target = self.ProfileSlide.create(
            {
                "name": "Approved Target",
                "channel_id": target_channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        proposed_target = self.ProfileSlide.create(
            {
                "name": "Proposed Target",
                "channel_id": target_channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        rejected_target = self.ProfileSlide.create(
            {
                "name": "Rejected Target",
                "channel_id": target_channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        incoming_source = self.ProfileSlide.create(
            {
                "name": "Incoming Source",
                "channel_id": incoming_channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )

        Mapping = self.env["facodi.learning.mapping"].with_user(self.manager)
        approved = Mapping.create(
            {
                "source_slide_id": source.id,
                "target_slide_id": approved_target.id,
                "mapping_type": "related",
            }
        )
        approved.action_approve()
        Mapping.create(
            {
                "source_slide_id": source.id,
                "target_slide_id": proposed_target.id,
                "mapping_type": "recommended",
            }
        )
        rejected = Mapping.create(
            {
                "source_slide_id": source.id,
                "target_slide_id": rejected_target.id,
                "mapping_type": "supports",
            }
        )
        rejected.action_reject()
        incoming = Mapping.create(
            {
                "source_slide_id": incoming_source.id,
                "target_slide_id": source.id,
                "mapping_type": "supports",
            }
        )
        incoming.action_approve()

        profile = self._profile(source_channel)

        self.assertEqual(
            profile["approved_content_relations"]["outgoing"],
            [
                {
                    "target_channel_id": target_channel.id,
                    "mapping_type": "related",
                    "count": 1,
                }
            ],
        )
        self.assertEqual(
            profile["approved_content_relations"]["incoming"],
            [
                {
                    "source_channel_id": incoming_channel.id,
                    "mapping_type": "supports",
                    "count": 1,
                }
            ],
        )
