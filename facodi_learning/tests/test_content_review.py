import base64
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestContentPublicationGovernance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.manager = cls.env["res.users"].create(
            {
                "name": "FACODI Governance Manager",
                "login": "facodi-governance-manager",
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
        cls.channel = cls.env["slide.channel"].create(
            {
                "name": "Governance Course",
                "website_id": cls.website.id,
                "user_id": cls.manager.id,
            }
        )

    def _slide(self, name="Governed content", **extra):
        values = {
            "name": name,
            "channel_id": self.channel.id,
            "slide_category": "article",
        }
        values.update(extra)
        return self.env["slide.slide"].create(values)

    def _complete_review(self, slide, **extra):
        values = {
            "slide_id": slide.id,
            "author": "FACODI contributor",
            "rights_mode": "original",
            "usage_basis": (
                "Author confirms original authorship and FACODI publication use."
            ),
            "purpose": "Open educational resource for the FACODI catalogue.",
        }
        values.update(extra)
        return self.env["facodi.learning.content.review"].create(values)

    def test_new_publication_is_blocked_until_current_review_is_approved(self):
        self.website.action_facodi_enable_publication_review()
        slide = self._slide()
        try:
            slide.write({"is_published": True})
        except ValidationError:
            pass
        else:
            self.fail("Publishing without review must be rejected.")
        slide.invalidate_recordset()
        self.assertFalse(slide.is_published)

        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})
        self.assertTrue(slide.is_published)
        self.assertEqual(review.state, "approved")
        self.assertEqual(review.reviewed_by_id, self.manager)

    def test_published_create_rolls_back_when_review_is_missing(self):
        before = self.env["slide.slide"].search_count([])
        try:
            self.env["slide.slide"].create(
                {
                    "name": "Atomic blocked publication",
                    "channel_id": self.channel.id,
                    "slide_category": "article",
                    "is_published": True,
                }
            )
        except ValidationError:
            pass
        else:
            self.fail("Published create without review must be rejected.")
        self.assertEqual(self.env["slide.slide"].search_count([]), before)
        self.assertFalse(
            self.env["slide.slide"].search(
                [("name", "=", "Atomic blocked publication")],
                limit=1,
            )
        )

    def test_incomplete_pending_review_does_not_invent_provenance(self):
        slide = self._slide()
        review = self.env["facodi.learning.content.review"].create(
            {"slide_id": slide.id, "origin": "legacy_reconciliation"}
        )
        self.assertFalse(review.author)
        self.assertFalse(review.rights_mode)
        self.assertFalse(review.source_url)
        with self.assertRaises(ValidationError):
            review.with_user(self.manager).action_approve()

    def test_external_review_requires_source_provenance(self):
        slide = self._slide()
        review = self._complete_review(
            slide,
            rights_mode="external",
            usage_basis=(
                "Public external resource linked by FACODI; no copy is claimed."
            ),
        )
        with self.assertRaises(ValidationError):
            review.with_user(self.manager).action_approve()
        review.write({"source_url": "https://example.org/learning-resource"})
        review.with_user(self.manager).action_approve()
        self.assertEqual(review.state, "approved")

    def test_legacy_public_content_remains_public_and_is_flagged(self):
        self.website.sudo().write({"facodi_publication_review_enabled": False})
        slide = self._slide("Legacy public content")
        slide.write({"is_published": True})
        self.website.action_facodi_enable_publication_review()
        slide.invalidate_recordset()
        self.assertTrue(slide.is_published)
        self.assertTrue(slide.facodi_legacy_review_pending)
        self.assertFalse(slide.facodi_content_review_ids)

    def test_legacy_website_published_content_is_backfilled(self):
        self.website.sudo().write({"facodi_publication_review_enabled": False})
        slide = self._slide("Legacy website publication")
        slide.write({"website_published": True})
        slide.invalidate_recordset()
        self.assertTrue(slide.website_published)
        self.website.action_facodi_enable_publication_review()
        slide.invalidate_recordset()
        self.assertTrue(slide.website_published)
        self.assertTrue(slide.facodi_legacy_review_pending)

    def test_legacy_backfill_skips_currently_approved_public_content(self):
        self.website.sudo().write({"facodi_publication_review_enabled": False})
        slide = self._slide("Approved before governance enablement")
        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})

        self.website.action_facodi_enable_publication_review()
        slide.invalidate_recordset()
        self.assertTrue(slide.is_published)
        self.assertFalse(slide.facodi_legacy_review_pending)
        self.assertEqual(review.state, "approved")

    def test_batch_reenable_backfills_each_website_without_flagging_approved(self):
        other_website = self.env["website"].create({"name": "Governance Batch Site"})
        other_channel = self.env["slide.channel"].create(
            {
                "name": "Governance Batch Course",
                "website_id": other_website.id,
                "user_id": self.manager.id,
            }
        )
        websites = self.website | other_website
        websites.sudo().write({"facodi_publication_review_enabled": False})

        approved_slide = self._slide("Approved batch legacy content")
        approved_review = self._complete_review(approved_slide)
        approved_review.with_user(self.manager).action_approve()
        approved_slide.write({"is_published": True})

        pending_slide = self.env["slide.slide"].create(
            {
                "name": "Pending batch legacy content",
                "channel_id": other_channel.id,
                "slide_category": "article",
                "is_published": True,
            }
        )

        websites.sudo().write({"facodi_publication_review_enabled": True})
        approved_slide.invalidate_recordset()
        pending_slide.invalidate_recordset()

        self.assertFalse(approved_slide.facodi_legacy_review_pending)
        self.assertTrue(pending_slide.facodi_legacy_review_pending)

    def test_governance_cannot_be_disabled_through_normal_orm(self):
        self.website.action_facodi_enable_publication_review()
        admin = self.env.ref("base.user_admin")
        with self.assertRaises(AccessError):
            self.website.with_user(admin).write(
                {"facodi_publication_review_enabled": False}
            )
        self.assertTrue(self.website.facodi_publication_review_enabled)

    def test_site_less_content_is_not_accidentally_governed(self):
        channel = self.env["slide.channel"].create({"name": "Site-less course"})
        slide = self.env["slide.slide"].create(
            {
                "name": "Site-less public content",
                "channel_id": channel.id,
                "slide_category": "article",
                "is_published": True,
            }
        )
        self.assertTrue(slide.is_published)
        self.assertFalse(slide._facodi_requires_review())

    def test_moving_public_content_into_governed_scope_requires_review(self):
        self.website.sudo().write({"facodi_publication_review_enabled": False})
        site_less = self.env["slide.channel"].create({"name": "Scope source course"})
        slide = self.env["slide.slide"].create(
            {
                "name": "Public before entering FACODI scope",
                "channel_id": site_less.id,
                "slide_category": "article",
                "is_published": True,
            }
        )
        self.website.action_facodi_enable_publication_review()

        with self.assertRaises(ValidationError):
            slide.write({"channel_id": self.channel.id})
        slide.invalidate_recordset()
        self.assertEqual(slide.channel_id, site_less)

    def test_assigning_governed_website_to_public_channel_requires_review(self):
        self.website.sudo().write({"facodi_publication_review_enabled": False})
        channel = self.env["slide.channel"].create({"name": "Scope channel"})
        slide = self.env["slide.slide"].create(
            {
                "name": "Public site-less content",
                "channel_id": channel.id,
                "slide_category": "article",
                "is_published": True,
            }
        )
        self.website.action_facodi_enable_publication_review()

        with self.assertRaises(ValidationError):
            channel.write({"website_id": self.website.id})
        channel.invalidate_recordset()
        self.assertFalse(channel.website_id)
        self.assertTrue(slide.is_published)

    def test_editing_public_content_invalidates_approved_hash(self):
        self.website.action_facodi_enable_publication_review()
        slide = self._slide()
        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})
        try:
            slide.write({"name": "Changed after approval"})
        except ValidationError:
            pass
        else:
            self.fail("Editing reviewed public content must be rejected.")
        slide.invalidate_recordset()
        self.assertEqual(slide.name, "Governed content")

    def test_approved_hash_is_language_context_independent(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        slide = self._slide("Governed multilingual content")
        slide.update_field_translations(
            "name",
            {
                "en_US": "Governed multilingual content",
                "fr_FR": "Contenu multilingue gouverné",
            },
        )
        review = self._complete_review(slide.with_context(lang="en_US"))
        review.with_user(self.manager).with_context(lang="en_US").action_approve()

        slide.with_user(self.manager).with_context(lang="fr_FR").write(
            {"is_published": True}
        )
        slide.invalidate_recordset()
        self.assertTrue(slide.is_published)

    def test_translation_update_invalidates_public_review_atomically(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        slide = self._slide("Stable reviewed title")
        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})

        with self.assertRaises(ValidationError):
            slide.update_field_translations(
                "name",
                {"fr_FR": "Titre modifié après validation"},
            )

        slide.invalidate_recordset(["name"])
        self.assertEqual(
            slide.with_context(lang="fr_FR").name,
            "Stable reviewed title",
        )
        self.assertTrue(slide.is_published)

    def test_moving_approved_sourced_content_to_another_course_requires_new_review(self):
        slide = self._slide("Course-scoped reviewed content")
        source = self.env["facodi.learning.source"].ingest_manual(
            {
                "name": "Course-scoped canonical source",
                "external_id": "governance-source-move",
                "channel_id": self.channel.id,
                "url": "https://example.org/scoped-source",
            },
            slide_id=slide.id,
        )
        review = self.env["facodi.learning.content.review"].search(
            [
                ("slide_id", "=", slide.id),
                ("source_id", "=", source.id),
                ("state", "=", "pending"),
            ],
            limit=1,
        )
        review.write(
            {
                "author": "External contributor",
                "rights_mode": "external",
                "usage_basis": "Public external resource linked by FACODI.",
                "purpose": "Course-scoped learning resource.",
            }
        )
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})

        other_channel = self.env["slide.channel"].create(
            {
                "name": "Other governed course",
                "website_id": self.website.id,
                "user_id": self.manager.id,
            }
        )
        try:
            slide.write({"channel_id": other_channel.id})
        except ValidationError:
            pass
        else:
            self.fail("Moving reviewed sourced content must require a new review.")
        slide.invalidate_recordset()
        self.assertEqual(slide.channel_id, self.channel)

    def _reviewed_public_quiz(self):
        slide = self._slide("Governed quiz", slide_category="quiz")
        question = self.env["slide.question"].create(
            {
                "slide_id": slide.id,
                "sequence": 10,
                "question": "Which option is correct?",
                "answer_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "text_value": "Correct answer",
                            "is_correct": True,
                            "comment": "Correct feedback",
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "text_value": "Incorrect answer",
                            "is_correct": False,
                            "comment": "Incorrect feedback",
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 30,
                            "text_value": "Another incorrect answer",
                            "is_correct": False,
                            "comment": "Alternative feedback",
                        }
                    ),
                ],
            }
        )
        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})
        return slide, question

    def test_public_quiz_question_write_requires_new_review(self):
        slide, question = self._reviewed_public_quiz()

        with self.assertRaises(ValidationError):
            question.write({"question": "Changed after Manager approval"})

        question.invalidate_recordset(["question"])
        self.assertEqual(question.question, "Which option is correct?")
        self.assertTrue(slide.is_published)

    def test_public_quiz_answer_crud_requires_new_review_atomically(self):
        slide, question = self._reviewed_public_quiz()
        answers = question.answer_ids.sorted("sequence")
        edited = answers[0]
        removable = answers[-1]

        with self.assertRaises(ValidationError):
            edited.write({"text_value": "Changed reviewed answer"})
        edited.invalidate_recordset(["text_value"])
        self.assertEqual(edited.text_value, "Correct answer")

        correctness_edit = answers[1]
        with self.assertRaises(ValidationError):
            correctness_edit.write({"is_correct": True})
        correctness_edit.invalidate_recordset(["is_correct"])
        self.assertFalse(correctness_edit.is_correct)

        before = self.env["slide.answer"].search_count(
            [("question_id", "=", question.id)]
        )
        with self.assertRaises(ValidationError):
            self.env["slide.answer"].create(
                {
                    "question_id": question.id,
                    "sequence": 40,
                    "text_value": "Unreviewed extra answer",
                    "is_correct": False,
                }
            )
        self.assertEqual(
            self.env["slide.answer"].search_count(
                [("question_id", "=", question.id)]
            ),
            before,
        )

        with self.assertRaises(ValidationError):
            removable.unlink()
        self.assertTrue(removable.exists())
        self.assertTrue(slide.is_published)

    def test_public_quiz_translation_updates_roll_back_atomically(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        slide, question = self._reviewed_public_quiz()
        answer = question.answer_ids.sorted("sequence")[0]

        with self.assertRaises(ValidationError):
            question.update_field_translations(
                "question",
                {"fr_FR": "Question modifiée après validation"},
            )
        question.invalidate_recordset(["question"])
        self.assertEqual(
            question.with_context(lang="fr_FR").question,
            "Which option is correct?",
        )

        with self.assertRaises(ValidationError):
            answer.update_field_translations(
                "text_value",
                {"fr_FR": "Réponse modifiée après validation"},
            )
        answer.invalidate_recordset(["text_value"])
        self.assertEqual(
            answer.with_context(lang="fr_FR").text_value,
            "Correct answer",
        )
        self.assertTrue(slide.is_published)

    def test_public_quiz_question_create_and_unlink_require_new_review(self):
        slide, question = self._reviewed_public_quiz()

        with self.assertRaises(ValidationError):
            self.env["slide.question"].create(
                {
                    "slide_id": slide.id,
                    "sequence": 20,
                    "question": "Unreviewed new question",
                    "answer_ids": [
                        Command.create(
                            {"text_value": "Yes", "is_correct": True}
                        ),
                        Command.create(
                            {"text_value": "No", "is_correct": False}
                        ),
                    ],
                }
            )
        self.assertFalse(
            self.env["slide.question"].search(
                [
                    ("slide_id", "=", slide.id),
                    ("question", "=", "Unreviewed new question"),
                ],
                limit=1,
            )
        )

        with self.assertRaises(ValidationError):
            question.unlink()
        self.assertTrue(question.exists())
        self.assertTrue(slide.is_published)

    def test_replacing_public_document_payload_invalidates_review(self):
        slide = self._slide(
            "Governed document",
            slide_category="document",
            binary_content=base64.b64encode(b"first reviewed document"),
        )
        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})

        try:
            slide.write(
                {"binary_content": base64.b64encode(b"replacement document")}
            )
        except ValidationError:
            pass
        else:
            self.fail("Replacing a reviewed public document must be rejected.")
        slide.invalidate_recordset()
        self.assertEqual(
            slide.binary_content,
            base64.b64encode(b"first reviewed document"),
        )

    def test_officer_can_publish_after_manager_approval(self):
        officer = self.env["res.users"].create(
            {
                "name": "FACODI Governance Officer",
                "login": "facodi-governance-officer",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id,
                        ],
                    )
                ],
            }
        )
        channel = self.env["slide.channel"].create(
            {
                "name": "Officer-owned governed course",
                "website_id": self.website.id,
                "user_id": officer.id,
            }
        )
        slide = self.env["slide.slide"].create(
            {
                "name": "Officer publication",
                "channel_id": channel.id,
                "slide_category": "article",
            }
        )
        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()

        slide.with_user(officer).write({"website_published": True})
        self.assertTrue(slide.website_published)

    def test_review_source_must_belong_to_reviewed_slide_channel(self):
        other_channel = self.env["slide.channel"].create(
            {"name": "Different provenance course"}
        )
        source = self.env["facodi.learning.source"].create(
            {
                "name": "Cross-course source",
                "external_id": "cross-course-source",
                "provider": "manual",
                "channel_id": other_channel.id,
            }
        )
        slide = self._slide("Reviewed in another course")

        with self.assertRaises(ValidationError):
            self.env["facodi.learning.content.review"].create(
                {
                    "slide_id": slide.id,
                    "source_id": source.id,
                }
            )

    def test_terminal_review_requires_row_lock(self):
        slide = self._slide()
        review = self._complete_review(slide)
        empty = self.env["facodi.learning.content.review"]
        with patch.object(type(review), "try_lock_for_update", return_value=empty):
            with self.assertRaises(ValidationError):
                review.with_user(self.manager).action_approve()
        review.invalidate_recordset()
        self.assertEqual(review.state, "pending")

    def test_completed_review_is_immutable(self):
        slide = self._slide()
        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        with self.assertRaises(AccessError):
            review.write({"purpose": "Changed"})
        with self.assertRaises(AccessError):
            review.unlink()

    def test_source_ingestion_creates_explicit_pending_review(self):
        slide = self._slide("Ingested external content")
        source = self.env["facodi.learning.source"].ingest_manual(
            {
                "name": "External source",
                "external_id": "governance-source-1",
                "channel_id": self.channel.id,
                "url": "https://example.org/source",
            },
            slide_id=slide.id,
        )
        review = self.env["facodi.learning.content.review"].search(
            [("slide_id", "=", slide.id), ("state", "=", "pending")],
            limit=1,
        )
        self.assertTrue(review)
        self.assertEqual(review.source_id, source)
        self.assertEqual(review.source_url, source.url)
        self.assertFalse(review.author)
        self.assertFalse(review.rights_mode)
        self.assertFalse(slide.is_published)

    def test_reenabling_governance_via_write_backfills_legacy_public_content(self):
        self.website.sudo().write({"facodi_publication_review_enabled": False})
        slide = self._slide("Legacy public via direct enable")
        slide.write({"is_published": True})

        self.website.sudo().write({"facodi_publication_review_enabled": True})
        slide.invalidate_recordset()
        self.assertTrue(slide.is_published)
        self.assertTrue(slide.facodi_legacy_review_pending)
