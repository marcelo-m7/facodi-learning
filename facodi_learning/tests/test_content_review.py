import base64
from unittest.mock import patch

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
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id
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
        self.env.cr.execute(
            """
            UPDATE slide_slide
               SET is_published = FALSE,
                   website_published = TRUE
             WHERE id = %s
            """,
            [slide.id],
        )
        slide.invalidate_recordset(["is_published", "website_published"])
        self.assertFalse(slide.is_published)
        self.assertTrue(slide.website_published)
        self.website.action_facodi_enable_publication_review()
        slide.invalidate_recordset()
        self.assertTrue(slide.website_published)
        self.assertTrue(slide.facodi_legacy_review_pending)

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
                            self.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id
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
