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
