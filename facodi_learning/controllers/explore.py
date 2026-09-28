from urllib.parse import urlencode

from odoo import http
from odoo.http import request

from ..services.youtube import youtube_video_identity


class FacodiExploreController(http.Controller):
    PAGE_SIZE = 12
    LANGUAGE_PREFIX = "lang:"
    COMMUNITY_STATES = {
        "submitted": "Awaiting review",
        "reviewing": "Under review",
        "accepted": "Accepted for curation",
        "resolved": "Routed to FACODI",
    }

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
        website = request.website
        return [
            ("active", "=", True),
            ("website_published", "=", True),
            ("is_preview", "=", True),
            ("channel_id.active", "=", True),
            ("channel_id.website_published", "=", True),
            ("channel_id.visibility", "=", "public"),
            "|",
            ("channel_id.website_id", "=", False),
            ("channel_id.website_id", "=", website.id),
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


    @http.route(
        [
            "/explorar",
            "/explorar/areas",
            "/explorar/conteudos",
            "/explorar/conteudos/page/<int:page>",
            "/explorar/videos",
            "/explorar/videos/page/<int:page>",
            "/explorar/cursos",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def legacy_explore_routes(self, page=None, **kwargs):
        path = request.httprequest.path
        replacements = (
            ("/explorar/conteudos", "/explore/content"),
            ("/explorar/videos", "/explore/videos"),
            ("/explorar/areas", "/explore/areas"),
            ("/explorar/cursos", "/explore/courses"),
            ("/explorar", "/explore"),
        )
        for legacy, canonical in replacements:
            if path == legacy or path.startswith(legacy + "/"):
                target = canonical + path[len(legacy):]
                query = request.httprequest.query_string.decode()
                if query:
                    target += "?" + query
                return request.redirect(target, code=301)
        return request.redirect("/explore", code=301)

    @http.route(
        "/facodi/home/catalogue-fragment",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET"],
    )
    def homepage_catalogue_fragment(self, **kwargs):
        content_type = (kwargs.get("type") or "courses").strip().lower()
        if content_type not in {"courses", "roadmaps", "curricular-units"}:
            content_type = "courses"

        if content_type == "roadmaps":
            records = self._public_references()[:6]
        elif content_type == "curricular-units":
            entries = request.env[
                "facodi.learning.curriculum.unit"
            ]._facodi_public_catalog_entries(website=request.website)
            records = entries[:6]
        else:
            records = self._public_courses()[:6]

        return request.render(
            "facodi_learning.homepage_catalogue_fragment",
            {
                "content_type": content_type,
                "records": records,
            },
        )

    @http.route("/explore", type="http", auth="public", website=True, sitemap=True)
    def explore_index(self, **kwargs):
        courses = self._public_courses()
        slides = self._public_slides()
        Curriculum = request.env["facodi.learning.curriculum.reference"].sudo()
        Unit = request.env["facodi.learning.curriculum.unit"].sudo()
        references = Curriculum.search(
            [
                ("website_published", "=", True),
                ("validated_at", "!=", False),
            ]
        )
        unit_entries = Unit._facodi_public_catalog_entries(website=request.website)
        community_rows = self._community_video_rows()
        explore_stats = {
            "courses": len(courses),
            "resources": len(slides),
            "roadmaps": len(references),
            "units": len(unit_entries),
            "community": len(community_rows),
            "areas": len(self._visible_areas()),
        }
        return request.render(
            "facodi_learning.explore_landing",
            {"explore_stats": explore_stats},
        )

    @http.route(
        ["/explore/areas"],
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
        ["/explore/content", "/explore/content/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def explore_content(self, page=1, **kwargs):
        page = self._positive_integer(kwargs.get("page") or page, default=1)
        query = (kwargs.get("q") or "").strip()
        area_id = self._positive_integer(kwargs.get("area"))
        language = (kwargs.get("language") or "").strip()
        content_format = (kwargs.get("format") or "").strip()

        all_slides = self._public_slides()
        available_formats = self._format_options(all_slides)
        format_values = {value for value, _label in available_formats}
        if content_format and content_format not in format_values:
            content_format = ""

        slide_domain = list(self._public_slide_domain())
        if query:
            slide_domain += [
                "|",
                ("name", "ilike", query),
                ("description", "ilike", query),
            ]
        if area_id:
            slide_domain.append(("channel_id.tag_ids", "in", [area_id]))
        if language:
            slide_domain.append(
                ("tag_ids.name", "=", f"{self.LANGUAGE_PREFIX}{language}")
            )
        if content_format:
            slide_domain.append(("slide_category", "=", content_format))

        Slide = request.env["slide.slide"].sudo()
        total = Slide.search_count(slide_domain)
        page_count = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if page > page_count:
            page = page_count
        offset = (page - 1) * self.PAGE_SIZE
        slides = Slide.search(
            slide_domain,
            order="sequence, id",
            offset=offset,
            limit=self.PAGE_SIZE,
        )

        params = {
            "q": query,
            "area": area_id,
            "language": language,
            "format": content_format,
        }
        previous_url = False
        next_url = False
        if page > 1:
            previous_url = "/explore/content?" + self._query_string(
                {**params, "page": page - 1}
            )
        if page < page_count:
            next_url = "/explore/content?" + self._query_string(
                {**params, "page": page + 1}
            )

        active_filters = []
        if query:
            active_filters.append({"label": 'Search: "%s"' % query, "key": "q"})
        if area_id:
            area = self._visible_areas().filtered(lambda tag: tag.id == area_id)[:1]
            if area:
                active_filters.append({"label": "Area: %s" % area.name, "key": "area"})
        if language:
            active_filters.append({"label": "Language: %s" % language.upper(), "key": "language"})
        if content_format:
            format_label = dict(available_formats).get(content_format, content_format)
            active_filters.append({"label": "Format: %s" % format_label, "key": "format"})

        for filter_row in active_filters:
            remove_params = dict(params)
            remove_params[filter_row["key"]] = False
            remove_query = self._query_string(remove_params)
            filter_row["remove_url"] = "/explore/content"
            if remove_query:
                filter_row["remove_url"] += "?" + remove_query

        contribution_params = {
            "type": "resource",
            "source": "explore_empty_shelf",
            "section": "explore-content",
        }
        selected_area = self._visible_areas().filtered(lambda tag: tag.id == area_id)[:1]
        if selected_area:
            contribution_params["area"] = selected_area.id
        contribution_language = language.replace("-", "_").split("_", 1)[0].lower()
        if contribution_language in {"pt", "en", "es", "fr"}:
            contribution_params["language"] = contribution_language
        if content_format in {"video", "article"}:
            contribution_params["resource_type"] = content_format
        contribution_url = "/submissions/new?" + self._query_string(contribution_params)

        discovery_stats = {
            "resources": len(all_slides),
            "areas": len(self._visible_areas()),
            "languages": len(self._language_options(all_slides)),
            "formats": len(available_formats),
        }

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
                "active_filters": active_filters,
                "discovery_stats": discovery_stats,
                "contribution_url": contribution_url,
            },
        )

    @classmethod
    def _community_video_rows(cls, query=None, language=None):
        submissions = (
            request.env["facodi.learning.submission"]
            .sudo()
            .search(
                [("state", "in", list(cls.COMMUNITY_STATES))],
                order="create_date desc, id desc",
            )
        )
        rows = []
        needle = (query or "").strip().casefold()
        selected_language = (language or "").strip().lower()
        for submission in submissions:
            identity = youtube_video_identity(
                submission.normalized_source_url or submission.source_url
            )
            if not identity:
                continue
            if needle and needle not in (submission.name or "").casefold():
                continue
            submission_language = (submission.language or "").strip().lower()
            if selected_language and submission_language != selected_language:
                continue
            rows.append(
                {
                    "name": submission.name,
                    "source_url": identity["source_url"],
                    "language": submission_language,
                    "state": submission.state,
                    "state_label": cls.COMMUNITY_STATES[submission.state],
                }
            )
        return rows

    @http.route(
        ["/explore/videos", "/explore/videos/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def explore_community_videos(self, page=1, **kwargs):
        page = self._positive_integer(kwargs.get("page") or page, default=1)
        query = (kwargs.get("q") or "").strip()
        language = (kwargs.get("language") or "").strip().lower()

        all_rows = self._community_video_rows()
        language_options = sorted(
            {row["language"] for row in all_rows if row["language"]}
        )
        rows = self._community_video_rows(query=query, language=language)

        total = len(rows)
        page_count = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if page > page_count:
            page = page_count
        start = (page - 1) * self.PAGE_SIZE
        rows = rows[start : start + self.PAGE_SIZE]

        params = {"q": query, "language": language}
        previous_url = False
        next_url = False
        if page > 1:
            previous_url = "/explore/videos?" + self._query_string(
                {**params, "page": page - 1}
            )
        if page < page_count:
            next_url = "/explore/videos?" + self._query_string(
                {**params, "page": page + 1}
            )

        video_contribution_params = {
            "type": "resource",
            "resource_type": "video",
            "source": "community_video_cta",
            "section": "explore-videos",
        }
        if language in {"pt", "en", "es", "fr"}:
            video_contribution_params["language"] = language
        video_contribution_url = "/submissions/new?" + self._query_string(
            video_contribution_params
        )

        return request.render(
            "facodi_learning.explore_community_videos",
            {
                "videos": rows,
                "query": query,
                "selected_language": language,
                "language_options": language_options,
                "page": page,
                "page_count": page_count,
                "total": total,
                "previous_url": previous_url,
                "next_url": next_url,
                "video_contribution_url": video_contribution_url,
            },
        )

    @http.route(
        "/explore/courses",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def explore_courses(self, **kwargs):
        return request.redirect("/courses", code=302)
