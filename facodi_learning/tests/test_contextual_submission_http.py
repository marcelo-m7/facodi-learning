from lxml import html

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestContextualSubmissionHttp(HttpCase):
    def _csrf_token(self, route="/submissions/new"):
        response = self.url_open(route)
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        tokens = tree.xpath('//input[@name="csrf_token"]/@value')
        self.assertEqual(len(tokens), 1)
        return tokens[0]

    def test_localized_submission_aliases_render_the_unified_form(self):
        for route in ("/pt/submissions/new", "/en/submissions/new", "/es/submissions/new", "/fr/submissions/new"):
            response = self.url_open(route)
            self.assertEqual(response.status_code, 200, route)
            self.assertIn('data-facodi-submission-form="1"', response.text)

    def test_honeypot_submission_is_discarded_without_creating_a_record(self):
        Submission = self.env["facodi.learning.submission"].sudo()
        before = Submission.search_count([])
        response = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": self._csrf_token(),
                "type": "contact",
                "context": "Automated spam",
                "contact_email": "bot@example.test",
                "facodi_company_website": "https://spam.example.test",
            },
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/explore"))
        self.assertEqual(Submission.search_count([]), before)

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
    def test_type_switcher_preserves_safe_origin_context(self):
        response = self.url_open(
            "/submissions/new?source=my_submissions_new&section=my-submissions"
            "&source_page_url=%2Fmy%2Fsubmissions"
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        links = tree.xpath('//*[@data-facodi-submission-type-switcher="1"]//a/@href')
        self.assertEqual(len(links), 4)
        for submission_type in ("resource", "contact", "correction", "question"):
            matching = [href for href in links if f"type={submission_type}" in href]
            self.assertEqual(len(matching), 1, submission_type)
            self.assertIn("source=my_submissions_new", matching[0])
            self.assertIn("section=my-submissions", matching[0])
            self.assertIn("source_page_url=%2Fmy%2Fsubmissions", matching[0])

