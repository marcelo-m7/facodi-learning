from urllib.parse import urlencode

from odoo import http
from odoo.http import request


class FacodiExploreController(http.Controller):
    PAGE_SIZE = 12
    LANGUAGE_PREFIX = "lang:"

    @staticmethod
    def _positive_integer(value, default=False):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    @classmethod
    def _public_course_domain(cls):
        website = request.website
        return [
            ("active", "=", True),
            ("website_published", "=", True),
            ("visibility", "=", "public"),
            "|",
            ("website_id", "=", False),
            ("website_id", "=", website.id),
        ]

    @classmethod
    def _public_courses(cls):
        return request.env["slide.channel"].sudo().search(cls._public_course_domain())

    @classmethod
    def _public_slide_domain(cls):
        courses = cls._public_courses()
        return [
            ("active", "=", True),
            ("website_published", "=", True),
            ("is_preview", "=", True),
            ("channel_id", "in", courses.ids),
        ]

    @classmethod
    def _public_slides(cls):
        return request.env["slide.slide"].sudo().search(
            cls._public_slide_domain(), order="sequence, id"
        )

    @classmethod
    def _visible_areas(cls, query=None):
        courses = cls._public_courses()
        areas = courses.mapped("tag_ids").filtered(
            lambda tag: tag.group_id and tag.group_id.website_published
        )
        if query:
            needle = query.casefold()
            areas = areas.filtered(lambda tag: needle in (tag.name or "").casefold())
        return areas.sorted(key=lambda tag: ((tag.group_id.name or ""), (tag.name or ""), tag.id))

    @classmethod
    def _language_options(cls, slides):
        values = set()
        for tag in slides.mapped("tag_ids"):
            name = (tag.name or "").strip()
            if name.startswith(cls.LANGUAGE_PREFIX):
                code = name[len(cls.LANGUAGE_PREFIX) :].strip()
                if code:
                    values.add(code)
        return sorted(values)

    @staticmethod
    def _format_options(slides):
        labels = dict(slides._fields["slide_category"].selection)
        values = sorted({slide.slide_category for slide in slides if slide.slide_category})
        return [(value, labels.get(value, value.title())) for value in values]

    @staticmethod
    def _query_string(params):
        return urlencode(
            {
                key: value
                for key, value in params.items()
                if value not in (None, False, "")
            }
        )

    @http.route("/explorar", type="http", auth="public", website=True, sitemap=True)
    def explore_index(self, **kwargs):
        return request.render("facodi_learning.explore_landing")

    @http.route(
        ["/explorar/areas"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def explore_areas(self, **kwargs):
        query = (kwargs.get("q") or "").strip()
        return request.render(
            "facodi_learning.explore_areas",
            {
                "areas": self._visible_areas(query=query),
                "query": query,
            },
        )

    @http.route(
        ["/explorar/conteudos", "/explorar/conteudos/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def explore_content(self, page=1, **kwargs):
        page = self._positive_integer(page, default=1)
        query = (kwargs.get("q") or "").strip()
        area_id = self._positive_integer(kwargs.get("area"))
        language = (kwargs.get("language") or "").strip()
        content_format = (kwargs.get("format") or "").strip()

        all_slides = self._public_slides()
        filtered = all_slides

        if query:
            needle = query.casefold()
            filtered = filtered.filtered(
                lambda slide: needle in (slide.name or "").casefold()
                or needle in (slide.description or "").casefold()
            )

        if area_id:
            filtered = filtered.filtered(
                lambda slide: area_id in slide.channel_id.tag_ids.ids
            )

        if language:
            expected = f"{self.LANGUAGE_PREFIX}{language}"
            filtered = filtered.filtered(
                lambda slide: expected in slide.tag_ids.mapped("name")
            )

        available_formats = self._format_options(all_slides)
        format_values = {value for value, _label in available_formats}
        if content_format and content_format in format_values:
            filtered = filtered.filtered(
                lambda slide: slide.slide_category == content_format
            )
        elif content_format:
            content_format = ""

        total = len(filtered)
        page_count = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if page > page_count:
            page = page_count
        start = (page - 1) * self.PAGE_SIZE
        slides = filtered[start : start + self.PAGE_SIZE]

        params = {
            "q": query,
            "area": area_id,
            "language": language,
            "format": content_format,
        }
        previous_url = False
        next_url = False
        if page > 1:
            previous_url = "/explorar/conteudos?" + self._query_string(
                {**params, "page": page - 1}
            )
        if page < page_count:
            next_url = "/explorar/conteudos?" + self._query_string(
                {**params, "page": page + 1}
            )

        return request.render(
            "facodi_learning.explore_content",
            {
                "slides": slides,
                "areas": self._visible_areas(),
                "language_options": self._language_options(all_slides),
                "format_options": available_formats,
                "query": query,
                "selected_area_id": area_id,
                "selected_language": language,
                "selected_format": content_format,
                "page": page,
                "page_count": page_count,
                "total": total,
                "previous_url": previous_url,
                "next_url": next_url,
            },
        )

    @http.route(
        "/explorar/cursos",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def explore_courses(self, **kwargs):
        return request.redirect("/slides", code=302)
