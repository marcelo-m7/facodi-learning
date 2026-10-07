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
        self.assertIn("immediately visible in Community videos", response.text)
        self.assertEqual(
            " ".join(tree.xpath('//button[@type="submit"]//text()')).strip(),
            "Share video",
        )

    def test_contact_cta_prefills_topic_and_human_context(self):
        response = self.url_open(
            "/submissions/new?type=contact&source=course_contact_cta"
            "&section=course&topic=content&source_page_url=%2Fcourses%3Ftoken%3Dprivate"
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

    def test_canonical_contact_route_opens_full_contextual_contact_form(self):
        response = self.url_open("/contact")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Robots-Tag"), "noindex, follow")
        tree = html.fromstring(response.text)
        self.assertEqual(
            tree.xpath('//input[@name="submission_type"]/@value'),
            ["contact"],
        )
        self.assertEqual(
            tree.xpath('//input[@name="source_cta"]/@value'),
            ["contact_page"],
        )
        self.assertEqual(
            tree.xpath('//input[@name="source_section"]/@value'),
            ["contact"],
        )
        self.assertTrue(tree.xpath('//select[@name="contact_topic"]'))
        self.assertTrue(tree.xpath('//input[@name="organization"]'))
        self.assertTrue(tree.xpath('//input[@name="contact_email"]'))

    def test_canonical_contact_preserves_explicit_cta_origin_and_topic(self):
        response = self.url_open(
            "/contact?source=faq_contact_cta&section=faq&topic=collaboration"
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        self.assertEqual(
            tree.xpath('//input[@name="source_cta"]/@value'),
            ["faq_contact_cta"],
        )
        self.assertEqual(
            tree.xpath('//input[@name="source_section"]/@value'),
            ["faq"],
        )
        self.assertTrue(
            tree.xpath('//select[@name="contact_topic"]/option[@value="collaboration"][@selected]')
        )
        visible_text = " ".join(tree.xpath("//body//text()"))
        self.assertIn("FAQ contact", visible_text)
        self.assertNotIn("faq_contact_cta", visible_text)

    def test_community_contact_origin_is_human_readable(self):
        response = self.url_open(
            "/contact?source=forum_postit_contact_cta&section=community&topic=collaboration"
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        self.assertEqual(
            tree.xpath('//input[@name="source_cta"]/@value'),
            ["forum_postit_contact_cta"],
        )
        visible_text = " ".join(tree.xpath("//body//text()"))
        self.assertIn("Community notebook", visible_text)
        self.assertNotIn("forum_postit_contact_cta", visible_text)

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
        self.assertFalse(
            tree.xpath('//select[@name="resource_type"]/option[@value="malicious"]')
        )
        self.assertTrue(
            tree.xpath('//select[@name="resource_type"]/option[@value=""][@selected]')
        )
        self.assertFalse(
            tree.xpath('//select[@name="language"]/option[@value="xx"]')
        )
    def test_type_switcher_preserves_safe_origin_context(self):
        response = self.url_open(
            "/submissions/new?source=my_submissions_new&section=my-submissions"
            "&source_page_url=%2Fmy%2Fsubmissions"
            "&resource_type=video&resource_level=introductory&language=pt"
            "&contact_topic=collaboration"
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
            self.assertIn("resource_type=video", matching[0])
            self.assertIn("resource_level=introductory", matching[0])
            self.assertIn("language=pt", matching[0])
            self.assertIn("contact_topic=collaboration", matching[0])
            self.assertNotIn("contact_email=", matching[0])
            self.assertNotIn("context=", matching[0])



    def test_header_and_homepage_sections_use_human_labels(self):
        cases = (
            (
                "/submissions/new?type=resource&source=main_nav_contribute&section=header",
                "Main navigation",
            ),
            (
                "/submissions/new?type=resource&source=closing_cta&section=homepage",
                "Homepage",
            ),
        )
        for route, expected_label in cases:
            response = self.url_open(route)
            self.assertEqual(response.status_code, 200)
            tree = html.fromstring(response.text)
            brief = " ".join(
                tree.xpath('//*[@data-facodi-contribution-brief="1"]//text()')
            )
            self.assertIn(expected_label, brief)

    def test_contact_post_accepts_valid_email_server_side(self):
        Submission = self.env["facodi.learning.submission"].sudo()
        before = Submission.search_count([])
        response = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": self._csrf_token("/contact"),
                "type": "contact",
                "context": "Please contact me about FACODI.",
                "contact_topic": "collaboration",
                "contact_email": "marcelo@example.com",
            },
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        submission = Submission.search(
            [("contact_email", "=", "marcelo@example.com")],
            order="id desc",
            limit=1,
        )
        self.assertEqual(Submission.search_count([]), before + 1)
        self.assertTrue(submission)
        self.assertEqual(submission.submission_type, "contact")
        self.assertEqual(submission.state, "submitted")

    def test_contact_post_rejects_malformed_email_server_side(self):
        Submission = self.env["facodi.learning.submission"].sudo()
        before = Submission.search_count([])
        response = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": self._csrf_token(),
                "type": "contact",
                "context": "Please contact me about FACODI.",
                "contact_topic": "collaboration",
                "contact_email": "not-an-email",
            },
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Enter a valid email address.", response.text)
        self.assertEqual(Submission.search_count([]), before)

    def test_post_drops_unsupported_language_and_resource_level(self):
        Submission = self.env["facodi.learning.submission"].sudo()
        before = Submission.search_count([])
        response = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": self._csrf_token(),
                "type": "resource",
                "name": "Safe selection resource",
                "source_url": "https://example.org/safe-selection",
                "resource_type": "article",
                "resource_level": "expert-only",
                "language": "xx",
            },
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        submission = Submission.search(
            [("name", "=", "Safe selection resource")],
            order="id desc",
            limit=1,
        )
        self.assertEqual(Submission.search_count([]), before + 1)
        self.assertFalse(submission.resource_level)
        self.assertFalse(submission.language)

    def test_validation_error_response_remains_noindex(self):
        response = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": self._csrf_token(),
                "type": "contact",
                "context": "Please contact me.",
                "contact_topic": "collaboration",
                "contact_email": "not-an-email",
            },
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Robots-Tag"), "noindex, follow")

    def test_follow_up_permission_requires_an_email(self):
        Submission = self.env["facodi.learning.submission"].sudo()
        before = Submission.search_count([])
        response = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": self._csrf_token(),
                "type": "resource",
                "name": "Useful open resource",
                "source_url": "https://example.org/resource",
                "context": "Useful for the community.",
                "permission_to_contact": "1",
            },
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Add an email address if FACODI may contact you about this submission.",
            response.text,
        )
        self.assertEqual(Submission.search_count([]), before)

