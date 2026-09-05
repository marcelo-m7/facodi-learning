from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestCourseMappingEngine(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Mapping Engine Officer",
                "login": "mapping-engine-officer",
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
        cls.Channel = cls.env["slide.channel"]
        cls.tag_group = cls.env["slide.channel.tag.group"].create(
            {"name": "Mapping Topics"}
        )
        cls.database_tag = cls.env["slide.channel.tag"].create(
            {"name": "Databases", "group_id": cls.tag_group.id}
        )
        cls.other_tag = cls.env["slide.channel.tag"].create(
            {"name": "Other", "group_id": cls.tag_group.id}
        )

    def _channel(self, name, **extra):
        values = {"name": name}
        values.update(extra)
        return self.Channel.create(values)

    def _mapping_candidates(self, channel, limit=20):
        self.assertTrue(
            hasattr(channel, "_facodi_course_mapping_candidates"),
            "M3.3 requires slide.channel._facodi_course_mapping_candidates()",
        )
        return channel._facodi_course_mapping_candidates(limit=limit)

    def _record_language(self, channel, language):
        slide = self.env["slide.slide"].create(
            {
                "name": f"{channel.name} language evidence",
                "channel_id": channel.id,
                "slide_category": "article",
                "slide_type": "article",
            }
        )
        job = self.env["facodi.learning.analysis.job"].create(
            {"slide_id": slide.id, "provider": "local_metadata"}
        )
        self.env["facodi.learning.analysis.result"]._record_output(
            {
                "job_id": job.id,
                "slide_id": slide.id,
                "provider": "local_metadata",
                "model_name": "mapping-engine-test",
                "summary": "",
                "detected_language": language,
                "transcript": "",
                "raw_payload": {},
                "suggested_tags": [],
                "proposed_mappings": [],
            }
        )

    def test_retrieval_excludes_source_and_inactive_courses(self):
        source = self._channel("Source")
        active = self._channel("Active Target")
        inactive = self._channel("Inactive Target", active=False)

        target_ids = {
            item["target_channel_id"] for item in self._mapping_candidates(source)
        }

        self.assertIn(active.id, target_ids)
        self.assertNotIn(source.id, target_ids)
        self.assertNotIn(inactive.id, target_ids)

    def test_retrieval_respects_specific_website_compatibility(self):
        website = self.env.ref("website.default_website")
        other_website = self.env["website"].create({"name": "Other Mapping Website"})
        source = self._channel("Website Source", website_id=website.id)
        same = self._channel("Same Website", website_id=website.id)
        global_target = self._channel("Global Target", website_id=False)
        other = self._channel("Other Website", website_id=other_website.id)

        target_ids = {
            item["target_channel_id"] for item in self._mapping_candidates(source)
        }

        self.assertIn(same.id, target_ids)
        self.assertIn(global_target.id, target_ids)
        self.assertNotIn(other.id, target_ids)

    def test_bounded_retrieval_prioritizes_shared_course_tags(self):
        source = self._channel(
            "Prioritized Source",
            sequence=1,
            tag_ids=[Command.link(self.database_tag.id)],
        )
        self._channel("Generic First", sequence=2)
        self._channel("Generic Second", sequence=3)
        relevant = self._channel(
            "Relevant Despite Sequence",
            sequence=999,
            tag_ids=[Command.link(self.database_tag.id)],
        )

        target_ids = {
            item["target_channel_id"]
            for item in self._mapping_candidates(source, limit=2)
        }

        self.assertIn(relevant.id, target_ids)
        self.assertEqual(len(target_ids), 2)

    def test_rank_prefers_shared_course_tags(self):
        source = self._channel(
            "Database Systems",
            tag_ids=[Command.link(self.database_tag.id)],
        )
        shared = self._channel(
            "Database Applications",
            tag_ids=[Command.link(self.database_tag.id)],
        )
        unrelated = self._channel(
            "Cooking Fundamentals",
            tag_ids=[Command.link(self.other_tag.id)],
        )

        ranked = self._mapping_candidates(source)
        by_id = {item["target_channel_id"]: item for item in ranked}

        self.assertGreater(by_id[shared.id]["confidence"], by_id[unrelated.id]["confidence"])
        self.assertEqual(by_id[shared.id]["signals"]["tag_overlap"], 1.0)
        self.assertEqual(by_id[unrelated.id]["signals"]["tag_overlap"], 0.0)

    def test_rank_uses_language_compatibility_from_course_profile(self):
        source = self._channel("Language Source")
        compatible = self._channel("Compatible Language")
        incompatible = self._channel("Incompatible Language")
        self._record_language(source, "pt")
        self._record_language(compatible, "pt")
        self._record_language(incompatible, "en")

        by_id = {
            item["target_channel_id"]: item
            for item in self._mapping_candidates(source)
        }

        self.assertEqual(
            by_id[compatible.id]["signals"]["language_compatibility"], 1.0
        )
        self.assertEqual(
            by_id[incompatible.id]["signals"]["language_compatibility"], 0.0
        )
        self.assertGreater(
            by_id[compatible.id]["confidence"], by_id[incompatible.id]["confidence"]
        )

    def test_rank_output_is_deterministic(self):
        source = self._channel(
            "Deterministic Source",
            tag_ids=[Command.link(self.database_tag.id)],
        )
        self._channel(
            "Deterministic Target",
            tag_ids=[Command.link(self.database_tag.id)],
        )

        first = self._mapping_candidates(source)
        source.invalidate_recordset()
        second = self._mapping_candidates(source)

        self.assertEqual(first, second)
        self.assertTrue(all(item["ranking_version"] == "course-mapping-v1" for item in first))
        self.assertTrue(all(item["mapping_type"] == "related" for item in first))

    def test_generate_proposals_is_idempotent(self):
        source = self._channel(
            "Database Course",
            user_id=self.officer.id,
            tag_ids=[Command.link(self.database_tag.id)],
        )
        target = self._channel(
            "Database Course Advanced",
            tag_ids=[Command.link(self.database_tag.id)],
        )
        source_as_officer = source.with_user(self.officer)
        self.assertTrue(
            hasattr(source_as_officer, "_facodi_propose_course_mappings"),
            "M3.3 requires slide.channel._facodi_propose_course_mappings()",
        )

        first = source_as_officer._facodi_propose_course_mappings(limit=20)
        second = source_as_officer._facodi_propose_course_mappings(limit=20)

        matching = first.filtered(lambda item: item.target_channel_id.id == target.id)
        self.assertEqual(len(matching), 1)
        self.assertEqual(second & matching, matching)
        self.assertEqual(matching.origin, "analysis")
        self.assertEqual(matching.ranking_version, "course-mapping-v1")
        self.assertEqual(matching.state, "proposed")

    def test_generation_refuses_unavailable_source_lock_before_creating_proposals(self):
        source = self._channel(
            "Concurrent Database Course",
            user_id=self.officer.id,
            tag_ids=[Command.link(self.database_tag.id)],
        )
        target = self._channel(
            "Concurrent Database Course Advanced",
            tag_ids=[Command.link(self.database_tag.id)],
        )
        source_as_officer = source.with_user(self.officer)
        Mapping = self.env["facodi.learning.course.mapping"]
        domain = [
            ("source_channel_id", "=", source.id),
            ("target_channel_id", "=", target.id),
            ("mapping_type", "=", "related"),
        ]

        with self.registry.cursor() as lock_cr:
            lock_cr.execute(
                "SELECT pg_advisory_xact_lock(%s, %s)",
                (0x4641434F, source.id),
            )
            with self.assertRaises(ValidationError):
                source_as_officer._facodi_propose_course_mappings(limit=20)
            self.assertFalse(Mapping.search(domain))

        retry = source_as_officer._facodi_propose_course_mappings(limit=20)
        matching = retry.filtered(lambda item: item.target_channel_id.id == target.id)
        self.assertEqual(len(matching), 1)
        self.assertEqual(Mapping.search_count(domain), 1)

    def test_engine_does_not_use_learner_membership(self):
        source = self._channel("Membership Source")
        self._channel("Membership Target")
        initial = self._mapping_candidates(source)
        partner = self.env["res.partner"].create({"name": "Learner"})
        self.env["slide.channel.partner"].create(
            {"channel_id": source.id, "partner_id": partner.id}
        )
        source.invalidate_recordset()

        repeated = self._mapping_candidates(source)

        self.assertEqual(initial, repeated)
