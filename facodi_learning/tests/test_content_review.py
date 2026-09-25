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

    def _slide(self, name="Governed content"):
        return self.env["slide.slide"].create(
            {
                "name": name,
                "channel_id": self.channel.id,
                "slide_category": "article",
            }
        )

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
        with self.assertRaises(ValidationError):
            slide.write({"is_published": True})

        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})
        self.assertTrue(slide.is_published)
        self.assertEqual(review.state, "approved")
        self.assertEqual(review.reviewed_by_id, self.manager)

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
        self.website.write({"facodi_publication_review_enabled": False})
        slide = self._slide("Legacy public content")
        slide.write({"is_published": True})
        self.website.action_facodi_enable_publication_review()
        slide.invalidate_recordset()
        self.assertTrue(slide.is_published)
        self.assertTrue(slide.facodi_legacy_review_pending)
        self.assertFalse(slide.facodi_content_review_ids)

    def test_editing_public_content_invalidates_approved_hash(self):
        self.website.action_facodi_enable_publication_review()
        slide = self._slide()
        review = self._complete_review(slide)
        review.with_user(self.manager).action_approve()
        slide.write({"is_published": True})
        with self.assertRaises(ValidationError):
            slide.write({"name": "Changed after approval"})

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
