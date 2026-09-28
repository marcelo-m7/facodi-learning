from urllib.parse import urlencode

from lxml import html

from odoo import Command
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestExploreLearningWebsite(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].get_current_website()
        cls.website.sudo().write({"facodi_publication_review_enabled": False})

        cls.area_group = cls.env["slide.channel.tag.group"].create(
            {"name": "Learning Areas", "website_published": True}
        )
        cls.area_math = cls.env["slide.channel.tag"].create(
            {"name": "Mathematics", "group_id": cls.area_group.id}
        )
        cls.area_data = cls.env["slide.channel.tag"].create(
            {"name": "Data", "group_id": cls.area_group.id}
        )
        cls.area_hidden = cls.env["slide.channel.tag"].create(
            {"name": "Hidden Area", "group_id": cls.area_group.id}
        )

        cls.lang_en = cls.env["slide.tag"].create({"name": "lang:en_GB"})
        cls.lang_pt = cls.env["slide.tag"].create({"name": "lang:pt_PT"})
        cls.topic_sql = cls.env["slide.tag"].create({"name": "SQL"})

        cls.math_course = cls.env["slide.channel"].create(
            {
                "name": "Public Mathematics",
                "website_id": cls.website.id,
                "website_published": True,
                "visibility": "public",
                "tag_ids": [Command.set([cls.area_math.id])],
            }
        )
        cls.data_course = cls.env["slide.channel"].create(
            {
                "name": "Public Data",
                "website_id": cls.website.id,
                "website_published": True,
                "visibility": "public",
                "tag_ids": [Command.set([cls.area_data.id])],
            }
        )
        cls.members_course = cls.env["slide.channel"].create(
            {
                "name": "Members Hidden Course",
                "website_id": cls.website.id,
                "website_published": True,
                "visibility": "members",
                "enroll": "invite",
                "tag_ids": [Command.set([cls.area_hidden.id])],
            }
        )
        cls.draft_course = cls.env["slide.channel"].create(
            {
                "name": "Draft Hidden Course",
                "website_id": cls.website.id,
                "website_published": False,
                "visibility": "public",
                "tag_ids": [Command.set([cls.area_hidden.id])],
            }
        )
        cls.other_website = cls.env["website"].create({"name": "Other FACODI Site"})
        cls.other_website.sudo().write({"facodi_publication_review_enabled": False})
        cls.other_course = cls.env["slide.channel"].create(
            {
                "name": "Other Website Course",
                "website_id": cls.other_website.id,
                "website_published": True,
                "visibility": "public",
                "tag_ids": [Command.set([cls.area_hidden.id])],
            }
        )

        cls.math_video = cls.env["slide.slide"].create(
            {
                "name": "Algebra video",
                "channel_id": cls.math_course.id,
                "slide_category": "video",
                "website_published": True,
                "is_preview": True,
                "tag_ids": [Command.set([cls.lang_en.id])],
            }
        )
        cls.data_article = cls.env["slide.slide"].create(
            {
                "name": "SQL foundations",
                "channel_id": cls.data_course.id,
                "slide_category": "article",
                "website_published": True,
                "is_preview": True,
                "html_content": "<p>Relational databases.</p>",
                "tag_ids": [Command.set([cls.lang_pt.id, cls.topic_sql.id])],
            }
        )
        cls.env["slide.slide"].create(
            {
                "name": "Members secret",
                "channel_id": cls.members_course.id,
                "slide_category": "article",
                "website_published": True,
                "is_preview": False,
            }
        )
        cls.env["slide.slide"].create(
            {
                "name": "Draft secret",
                "channel_id": cls.draft_course.id,
                "slide_category": "article",
                "website_published": True,
                "is_preview": True,
            }
        )
        cls.env["slide.slide"].create(
            {
                "name": "Other website secret",
                "channel_id": cls.other_course.id,
                "slide_category": "article",
                "website_published": True,
                "is_preview": True,
            }
        )

    def test_explore_landing_and_courses_redirect(self):
        landing = self.url_open("/explore")
        self.assertEqual(landing.status_code, 200)
        self.assertIn("/explore/areas", landing.text)
        self.assertIn("/explore/content", landing.text)
        self.assertIn("/explore/videos", landing.text)
        self.assertIn("/explore/courses", landing.text)

        courses = self.url_open("/explore/courses", allow_redirects=False)
        self.assertIn(courses.status_code, (301, 302, 303, 307, 308))
        self.assertTrue(courses.headers["Location"].endswith("/courses"))

    def test_areas_expose_only_accessible_published_current_website_tags(self):
        response = self.url_open("/explore/areas")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Mathematics", response.text)
        self.assertIn("Data", response.text)
        self.assertNotIn("Hidden Area", response.text)
        self.assertNotIn("Other Website Course", response.text)
        tree = html.fromstring(response.text)
        math_cta = tree.xpath(
            '//a[contains(@href, "source=area_resource_cta") and contains(@href, "area=%s")]/@href'
            % self.area_math.id
        )
        self.assertEqual(len(math_cta), 1)
        contextual = self.url_open(math_cta[0])
        self.assertEqual(contextual.status_code, 200)
        contextual_tree = html.fromstring(contextual.text)
        self.assertEqual(
            contextual_tree.xpath('//input[@name="area_id"]/@value'),
            [str(self.area_math.id)],
        )
        self.assertIn(
            "Learning area resources",
            " ".join(contextual_tree.xpath("//body//text()")),
        )

        filtered = self.url_open("/explore/areas?" + urlencode({"q": "Math"}))
        self.assertIn("Mathematics", filtered.text)
        self.assertNotIn(">Data<", filtered.text)

    def test_content_search_filters_access_website_area_language_and_format(self):
        response = self.url_open("/explore/content")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Algebra video", response.text)
        self.assertIn("SQL foundations", response.text)
        self.assertNotIn("Members secret", response.text)
        self.assertNotIn("Draft secret", response.text)
        self.assertNotIn("Other website secret", response.text)

        area = self.url_open(
            "/explore/content?" + urlencode({"area": self.area_data.id})
        )
        self.assertIn("SQL foundations", area.text)
        self.assertNotIn("Algebra video", area.text)

        language = self.url_open(
            "/explore/content?" + urlencode({"language": "pt_PT"})
        )
        self.assertIn("SQL foundations", language.text)
        self.assertNotIn("Algebra video", language.text)

        content_format = self.url_open(
            "/explore/content?" + urlencode({"format": "video"})
        )
        self.assertIn("Algebra video", content_format.text)
        self.assertNotIn("SQL foundations", content_format.text)

        search = self.url_open("/explore/content?" + urlencode({"q": "SQL"}))
        self.assertIn("SQL foundations", search.text)
        self.assertNotIn("Algebra video", search.text)

    def test_content_pagination_preserves_public_boundary(self):
        for index in range(13):
            self.env["slide.slide"].create(
                {
                    "name": f"Pagination resource {index:02d}",
                    "channel_id": self.math_course.id,
                    "slide_category": "document",
                    "website_published": True,
                    "is_preview": True,
                    "tag_ids": [Command.set([self.lang_en.id])],
                }
            )

        first = self.url_open(
            "/explore/content?" + urlencode({"q": "Pagination resource"})
        )
        self.assertEqual(first.status_code, 200)
        self.assertIn("Pagination resource 00", first.text)
        self.assertIn("page=2", first.text)

        second = self.url_open(
            "/explore/content/page/2?"
            + urlencode({"q": "Pagination resource"})
        )
        self.assertEqual(second.status_code, 200)
        self.assertIn("Pagination resource", second.text)
        self.assertNotIn("Members secret", second.text)

    def test_language_filter_options_come_only_from_visible_content_tags(self):
        hidden_language = self.env["slide.tag"].create({"name": "lang:fr_FR"})
        self.env["slide.slide"].create(
            {
                "name": "Hidden French content",
                "channel_id": self.members_course.id,
                "slide_category": "article",
                "website_published": True,
                "tag_ids": [Command.set([hidden_language.id])],
            }
        )

        response = self.url_open("/explore/content")
        self.assertIn('value="en_GB"', response.text)
        self.assertIn('value="pt_PT"', response.text)
        self.assertNotIn('value="fr_FR"', response.text)


    def test_empty_filtered_shelf_prefills_area_language_and_format(self):
        response = self.url_open(
            "/explore/content?"
            + urlencode(
                {
                    "area": self.area_data.id,
                    "language": "en_US",
                    "format": "video",
                }
            )
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        hrefs = tree.xpath('//a[normalize-space()="Drop a resource"]/@href')
        self.assertEqual(len(hrefs), 1)
        href = hrefs[0]
        self.assertIn(f"area={self.area_data.id}", href)
        self.assertIn("language=en", href)
        self.assertIn("resource_type=video", href)

        form = self.url_open(href)
        self.assertEqual(form.status_code, 200)
        form_tree = html.fromstring(form.text)
        self.assertEqual(
            form_tree.xpath('//input[@name="area_id"]/@value'),
            [str(self.area_data.id)],
        )
        self.assertIn("Data", " ".join(form_tree.xpath("//body//text()")))
        self.assertTrue(
            form_tree.xpath('//select[@name="language"]/option[@value="en"][@selected]')
        )
        self.assertTrue(
            form_tree.xpath('//select[@name="resource_type"]/option[@value="video"][@selected]')
        )


    def test_community_video_cta_prefills_selected_language(self):
        response = self.url_open("/explore/videos?language=pt")
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        hrefs = tree.xpath('//a[normalize-space()="Share a video"]/@href')
        self.assertGreaterEqual(len(hrefs), 1)
        self.assertEqual(len(set(hrefs)), 1)
        for href in hrefs:
            self.assertIn("type=resource", href)
            self.assertIn("resource_type=video", href)
            self.assertIn("source=community_video_cta", href)
            self.assertIn("section=explore-videos", href)
            self.assertIn("language=pt", href)

        form = self.url_open(hrefs[0])
        self.assertEqual(form.status_code, 200)
        form_tree = html.fromstring(form.text)
        self.assertTrue(
            form_tree.xpath('//select[@name="resource_type"]/option[@value="video"][@selected]')
        )
        self.assertTrue(
            form_tree.xpath('//select[@name="language"]/option[@value="pt"][@selected]')
        )

    def test_community_video_cta_drops_unsupported_language_prefill(self):
        response = self.url_open("/explore/videos?language=xx")
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        hrefs = tree.xpath('//a[normalize-space()="Share a video"]/@href')
        self.assertGreaterEqual(len(hrefs), 1)
        self.assertEqual(len(set(hrefs)), 1)
        for href in hrefs:
            self.assertNotIn("language=xx", href)

    def test_contextual_form_rejects_non_public_area_context(self):
        response = self.url_open(
            "/submissions/new?"
            + urlencode(
                {
                    "type": "resource",
                    "area": self.area_hidden.id,
                    "source": "explore_empty_shelf",
                    "section": "explore-content",
                }
            )
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        self.assertFalse(tree.xpath('//input[@name="area_id"]'))
        self.assertNotIn("Hidden Area", " ".join(tree.xpath("//body//text()")))
