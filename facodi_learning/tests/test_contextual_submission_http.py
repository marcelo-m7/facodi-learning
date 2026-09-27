from lxml import html

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestContextualSubmissionHttp(HttpCase):
    def test_public_cta_prefills_resource_profile(self):
        response = self.url_open(
            "/submissions/new?type=resource&source=community_video_cta"
            "&section=explore-videos&resource_type=video&language=pt"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Robots-Tag"), "noindex, follow")
        tree = html.fromstring(response.text)

        self.assertEqual(
            tree.xpath('//input[@name="source_cta"]/@value'),
            ["community_video_cta"],
        )
        self.assertEqual(
            tree.xpath('//input[@name="source_section"]/@value'),
            ["explore-videos"],
        )
        self.assertTrue(
            tree.xpath('//select[@name="resource_type"]/option[@value="video"][@selected]')
        )
        self.assertTrue(
            tree.xpath('//select[@name="language"]/option[@value="pt"][@selected]')
        )
        context = " ".join(
            tree.xpath('//textarea[@name="context"]//text()')
        ).strip()
        self.assertIn("public video", context.lower())

    def test_contact_cta_prefills_topic_and_human_context(self):
        response = self.url_open(
            "/submissions/new?type=contact&source=course_contact_cta"
            "&section=course&topic=content&source_page_url=https%3A%2F%2Ffacodi.com%2Fcourses%3Ftoken%3Dprivate"
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        self.assertTrue(
            tree.xpath('//select[@name="contact_topic"]/option[@value="content"][@selected]')
        )
        self.assertEqual(
            tree.xpath('//input[@name="source_page_url"]/@value'),
            ["/courses"],
        )
        visible_text = " ".join(tree.xpath("//body//text()"))
        self.assertIn("Course contribution", visible_text)
        self.assertNotIn("course_contact_cta", visible_text)
        self.assertNotIn("token=private", response.text)

    def test_cross_origin_source_page_is_not_persisted_in_form(self):
        response = self.url_open(
            "/submissions/new?type=contact&source=faq_contribution_cta"
            "&source_page_url=https%3A%2F%2Fevil.example%2Fsecret"
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        self.assertEqual(tree.xpath('//input[@name="source_page_url"]/@value'), [""])

    def test_unsafe_prefill_selection_falls_back(self):
        response = self.url_open(
            "/submissions/new?type=resource&resource_type=malicious&language=xx"
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        self.assertTrue(
            tree.xpath('//select[@name="resource_type"]/option[@value="video"][@selected]')
        )
        self.assertFalse(
            tree.xpath('//select[@name="language"]/option[@value="xx"]')
        )
