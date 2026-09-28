import re
from urllib.parse import urlencode, urlsplit

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from . import submission as submission_controller
from .submission import FacodiSubmissionController
from ..services.youtube import youtube_video_identity


class FacodiContextualSubmissionController(FacodiSubmissionController):
    _CONTACT_EMAIL_RE = re.compile(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")

    @classmethod
    def _is_valid_contact_email(cls, value):
        candidate = (value or "").strip()
        return not candidate or bool(cls._CONTACT_EMAIL_RE.fullmatch(candidate))

    @staticmethod
    def _public_record(model, raw_id, public_path_method=None, website_field=None):
        try:
            record_id = int(raw_id or 0)
        except (TypeError, ValueError):
            return request.env[model].browse()
        if record_id <= 0:
            return request.env[model].browse()
        record = request.env[model].sudo().browse(record_id).exists()
        if not record:
            return request.env[model].browse()
        if public_path_method and not getattr(record, public_path_method)():
            return request.env[model].browse()
        if website_field and not getattr(record, website_field):
            return request.env[model].browse()
        return record

    @staticmethod
    def _public_roadmap(raw_id):
        try:
            record_id = int(raw_id or 0)
        except (TypeError, ValueError):
            return request.env["facodi.learning.curriculum.reference"].browse()
        if record_id <= 0:
            return request.env["facodi.learning.curriculum.reference"].browse()
        return (
            request.env["facodi.learning.curriculum.reference"]
            .sudo()
            .search(
                [
                    ("id", "=", record_id),
                    ("website_published", "=", True),
                    ("validated_at", "!=", False),
                ],
                limit=1,
            )
        )

    @staticmethod
    def _public_area(raw_id):
        try:
            record_id = int(raw_id or 0)
        except (TypeError, ValueError):
            return request.env["slide.channel.tag"].browse()
        if record_id <= 0:
            return request.env["slide.channel.tag"].browse()
        area = request.env["slide.channel.tag"].sudo().browse(record_id).exists()
        if not area or not area.group_id or not area.group_id.website_published:
            return request.env["slide.channel.tag"].browse()
        public_course = request.env["slide.channel"].sudo().search(
            [
                ("active", "=", True),
                ("website_published", "=", True),
                ("visibility", "=", "public"),
                ("tag_ids", "in", [area.id]),
                "|",
                ("website_id", "=", False),
                ("website_id", "=", request.website.id),
            ],
            limit=1,
        )
        return area if public_course else request.env["slide.channel.tag"].browse()

    @staticmethod
    def _public_course(raw_id):
        try:
            record_id = int(raw_id or 0)
        except (TypeError, ValueError):
            return request.env["slide.channel"].browse()
        if record_id <= 0:
            return request.env["slide.channel"].browse()
        return (
            request.env["slide.channel"]
            .sudo()
            .search(
                [
                    ("id", "=", record_id),
                    ("active", "=", True),
                    ("website_published", "=", True),
                    ("visibility", "=", "public"),
                    "|",
                    ("website_id", "=", False),
                    ("website_id", "=", request.website.id),
                ],
                limit=1,
            )
        )

    @staticmethod
    def _public_slide(raw_id):
        try:
            record_id = int(raw_id or 0)
        except (TypeError, ValueError):
            return request.env["slide.slide"].browse()
        if record_id <= 0:
            return request.env["slide.slide"].browse()
        return (
            request.env["slide.slide"]
            .sudo()
            .search(
                [
                    ("id", "=", record_id),
                    ("active", "=", True),
                    ("website_published", "=", True),
                    ("channel_id.active", "=", True),
                    ("channel_id.website_published", "=", True),
                    ("channel_id.visibility", "=", "public"),
                    "|",
                    ("channel_id.website_id", "=", False),
                    ("channel_id.website_id", "=", request.website.id),
                ],
                limit=1,
            )
        )

    @staticmethod
    def _bounded_text(value, limit):
        return (value or "").strip()[:limit]

    @staticmethod
    def _safe_selection(value, allowed, default=""):
        candidate = (value or "").strip().lower()
        return candidate if candidate in allowed else default

    @staticmethod
    def _safe_origin_path(value):
        candidate = (value or "").strip()
        if not candidate:
            return ""
        base = urlsplit(request.website.get_base_url() or "")
        parsed = urlsplit(candidate)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme not in {"http", "https"} or parsed.netloc != base.netloc:
                return ""
        path = parsed.path or "/"
        return path[:2048] if path.startswith("/") else ""

    def _submission_context_from_kwargs(self, kwargs):
        Submission = request.env["facodi.learning.submission"]
        submission_type = Submission._normalize_submission_type(kwargs.get("type") or kwargs.get("submission_type"))
        curriculum_unit = self._public_curriculum_unit(kwargs.get("unit_id") or kwargs.get("curriculum_unit_id"))
        area_tag = self._public_area(kwargs.get("area_id") or kwargs.get("area"))
        roadmap = self._public_roadmap(
            kwargs.get("roadmap_id") or kwargs.get("reference_id")
        )
        module = self._public_record(
            "facodi.learning.curriculum.module",
            kwargs.get("module_id"),
            public_path_method="_facodi_public_path",
        )
        course = self._public_course(
            kwargs.get("course_id") or kwargs.get("channel_id")
        )
        suggested_slide = self._public_slide(
            kwargs.get("slide_id") or kwargs.get("suggested_slide_id")
        )
        source_cta = Submission._clean_context_slug(kwargs.get("source") or kwargs.get("source_cta"))
        source_section = Submission._clean_context_slug(kwargs.get("section") or kwargs.get("source_section"))
        source_page_url = self._safe_origin_path(
            kwargs.get("source_page_url") or kwargs.get("origin")
        )
        if not source_page_url:
            referrer = request.httprequest.referrer or ""
            website_url = (request.website.get_base_url() or "").rstrip("/")
            if website_url and referrer.startswith(website_url + "/"):
                source_page_url = self._safe_origin_path(referrer)

        resource_type = self._safe_selection(
            kwargs.get("resource_type"),
            {"video", "article", "book", "tool", "repository", "course", "other"},
            "video",
        )
        resource_level = self._safe_selection(
            kwargs.get("resource_level"),
            {"introductory", "intermediate", "advanced"},
        )
        language = self._safe_selection(
            kwargs.get("language"),
            {"pt", "en", "es", "fr"},
        )
        contact_topic_defaults = {
            "course_contact_cta": "content",
            "faq_contribution_cta": "collaboration",
            "community_collaboration_cta": "collaboration",
            "editorial_routes_contact_cta": "collaboration",
            "ecosystem_contact_cta": "partnership",
            "institutional_contact_cta": "partnership",
            "legacy_submission_followup": "content",
            "contribution_board_collaboration_cta": "collaboration",
        }
        contact_topic = self._safe_selection(
            kwargs.get("contact_topic") or kwargs.get("topic"),
            {"collaboration", "partnership", "content", "technical", "accessibility", "other"},
            contact_topic_defaults.get(source_cta, ""),
        )

        form_values = {
            "submission_type": submission_type,
            "source_cta": source_cta,
            "source_section": source_section,
            "source_page_url": source_page_url,
            "resource_type": resource_type,
            "resource_level": resource_level,
            "language": language,
            "contact_topic": contact_topic,
            "name": self._bounded_text(kwargs.get("name") or kwargs.get("title"), 200),
            "source_url": self._bounded_text(kwargs.get("source_url"), 2048),
            "context": self._bounded_text(kwargs.get("context") or kwargs.get("message"), 4000),
        }

        if not request.env.user._is_public():
            partner = request.env.user.partner_id
            form_values.update(
                {
                    "contact_name": partner.name or "",
                    "contact_email": partner.email or request.env.user.email or "",
                    "organization": partner.parent_id.name if partner.parent_id else "",
                }
            )

        profile_context = ""
        if area_tag and not curriculum_unit and not roadmap and not module and not course and not suggested_slide:
            profile_context = request.env._(
                "Suggested for learning area: %s."
            ) % area_tag.name
        if curriculum_unit:
            profile_context = request.env._(
                "Suggested for curricular unit: %s (%s)."
            ) % (
                curriculum_unit.name,
                curriculum_unit.external_unit_code or request.env._("no source code"),
            )
        elif roadmap:
            profile_context = request.env._(
                "Suggested for roadmap: %s."
            ) % roadmap.display_name
        elif module:
            profile_context = request.env._(
                "Suggested for learning module: %s."
            ) % module.name
        elif suggested_slide:
            if course:
                profile_context = request.env._(
                    "Suggested around learning item: %s (course: %s)."
                ) % (suggested_slide.name, course.name)
            else:
                profile_context = request.env._(
                    "Suggested around learning item: %s."
                ) % suggested_slide.name
        elif course:
            profile_context = request.env._(
                "Suggested for course: %s."
            ) % course.name

        cta_defaults = {
            "community_margin": request.env._(
                "I found a resource that could help learners studying this curricular unit."
            ),
            "unit_resource_cta": request.env._(
                "I suggest this resource to strengthen the learning coverage for this curricular unit."
            ),
            "roadmap_resource_cta": request.env._(
                "I suggest this resource for this learning roadmap."
            ),
            "module_resource_cta": request.env._(
                "I suggest this resource for this learning module."
            ),
            "course_resource_cta": request.env._(
                "I suggest this resource as a useful companion to this course."
            ),
            "study_player_resource_cta": request.env._(
                "I suggest this resource as a useful companion to this lesson."
            ),
            "explore_empty_shelf": request.env._(
                "I found a resource that is missing from the current FACODI catalogue."
            ),
            "area_resource_cta": request.env._(
                "I suggest this resource for this learning area."
            ),
            "community_video_cta": request.env._(
                "I want to share this public video with the FACODI community."
            ),
            "portal_resource_cta": request.env._(
                "I want to add a useful resource to the FACODI community desk."
            ),
            "roadmaps_catalog_cta": request.env._(
                "I found a resource that could strengthen one of the FACODI learning roadmaps."
            ),
            "curricular_units_catalog_cta": request.env._(
                "I found a resource that could help cover a curricular unit in the FACODI academic map."
            ),
            "curricular_units_empty_state": request.env._(
                "I found a resource that could help start the curricular-unit shelf."
            ),
            "course_catalog_cta": request.env._(
                "I found a resource that could strengthen the FACODI course catalogue."
            ),
            "community_resource_cta": request.env._(
                "I found a useful public resource to leave on the community learning trail."
            ),
            "ecosystem_resource_cta": request.env._(
                "I found a resource that could strengthen the FACODI open-learning ecosystem."
            ),
            "cta_sheet_resource_cta": request.env._(
                "I want to add another useful page to the shared FACODI learning notebook."
            ),
            "contact_sheet_resource_cta": request.env._(
                "I am using the contribution route because this is a learning resource for editorial review."
            ),
            "contribution_board_resource_cta": request.env._(
                "I want to share a useful public resource for FACODI editorial review."
            ),
        }
        if not form_values["context"] and submission_type == "resource":
            form_values["context"] = " ".join(
                part for part in (profile_context, cta_defaults.get(source_cta, "")) if part
            )
        if area_tag:
            form_values["area_tag_id"] = area_tag.id
        if curriculum_unit:
            form_values["curriculum_unit_id"] = curriculum_unit.id
        if roadmap:
            form_values["roadmap_id"] = roadmap.id
        if module:
            form_values["module_id"] = module.id
        if course:
            form_values["course_id"] = course.id
        if suggested_slide:
            form_values["suggested_slide_id"] = suggested_slide.id
        cta_labels = {
            "community_margin": request.env._("Community margin"),
            "unit_resource_cta": request.env._("Curricular unit resources"),
            "roadmap_resource_cta": request.env._("Roadmap resources"),
            "module_resource_cta": request.env._("Learning module resources"),
            "course_resource_cta": request.env._("Course resources"),
            "course_contact_cta": request.env._("Course contribution"),
            "study_player_resource_cta": request.env._("Lesson resources"),
            "study_player_correction_cta": request.env._("Lesson problem report"),
            "study_player_question_cta": request.env._("Lesson question"),
            "explore_empty_shelf": request.env._("Explore empty shelf"),
            "area_resource_cta": request.env._("Learning area resources"),
            "community_video_cta": request.env._("Community videos"),
            "portal_resource_cta": request.env._("My FACODI"),
            "roadmaps_catalog_cta": request.env._("Roadmaps catalogue"),
            "curricular_units_catalog_cta": request.env._("Curricular units catalogue"),
            "curricular_units_empty_state": request.env._("Curricular units · open shelf"),
            "course_catalog_cta": request.env._("Course catalogue"),
            "faq_contribution_cta": request.env._("FAQ contribution"),
            "community_collaboration_cta": request.env._("Community collaboration"),
            "editorial_routes_contact_cta": request.env._("Contact and contribute"),
            "ecosystem_contact_cta": request.env._("FACODI ecosystem"),
            "institutional_contact_cta": request.env._("FACODI project"),
            "unit_correction_cta": request.env._("Curricular unit provenance"),
            "roadmap_correction_cta": request.env._("Roadmap provenance"),
            "community_resource_cta": request.env._("Community resource"),
            "ecosystem_resource_cta": request.env._("Ecosystem contribution"),
            "cta_sheet_resource_cta": request.env._("Shared learning notebook"),
            "contact_sheet_resource_cta": request.env._("Contact page resource"),
            "contact_page": request.env._("Contact FACODI"),
            "contribution_board_resource_cta": request.env._("Contribution board"),
            "contribution_board_correction_cta": request.env._("Contribution board correction"),
            "contribution_board_collaboration_cta": request.env._("Contribution board collaboration"),
            "translation_correction_cta": request.env._("Translation correction"),
            "folder_tabs_contribute": request.env._("Learning navigation"),
            "course_showcase_contribute": request.env._("Learning catalogue"),
            "submission_status_followup": request.env._("Submission follow-up"),
            "my_submissions_new": request.env._("My submissions"),
            "my_submissions_empty": request.env._("My submissions empty state"),
            "legacy_submission_followup": request.env._("Submission follow-up"),
        }
        return_url = source_page_url
        return_label = request.env._("Back to Explore")
        if not return_url and curriculum_unit:
            return_url = curriculum_unit._facodi_public_catalog_path() or curriculum_unit._facodi_public_path()
            return_label = request.env._("Back to curricular unit")
        elif not return_url and roadmap:
            return_url = "/roadmaps/%s" % roadmap.id
            return_label = request.env._("Back to roadmap")
        elif not return_url and module:
            return_url = module._facodi_public_path()
            return_label = request.env._("Back to learning module")
        elif not return_url and suggested_slide:
            return_url = self._safe_origin_path(suggested_slide.website_url)
            return_label = request.env._("Back to learning item")
        elif not return_url and course:
            return_url = self._safe_origin_path(course.website_url)
            return_label = request.env._("Back to course")
        elif return_url:
            return_label = request.env._("Back to where I was")
        return_url = return_url or "/explore"

        switch_base = {
            "source": source_cta,
            "section": source_section,
            "source_page_url": source_page_url,
        }
        if area_tag:
            switch_base["area"] = area_tag.id
        if curriculum_unit:
            switch_base["unit_id"] = curriculum_unit.id
        if roadmap:
            switch_base["roadmap_id"] = roadmap.id
        if module:
            switch_base["module_id"] = module.id
        if course:
            switch_base["course_id"] = course.id
        if suggested_slide:
            switch_base["slide_id"] = suggested_slide.id
        for key in ("resource_type", "resource_level", "language", "contact_topic"):
            if form_values.get(key):
                switch_base[key] = form_values[key]
        switch_base = {
            key: value for key, value in switch_base.items() if value not in ("", False, None)
        }
        submission_type_options = [
            {
                "key": key,
                "label": label,
                "url": "/submissions/new?" + urlencode({**switch_base, "type": key}),
            }
            for key, label in (
                ("resource", request.env._("Learning resource")),
                ("contact", request.env._("Contact")),
                ("correction", request.env._("Correction")),
                ("question", request.env._("Question")),
            )
        ]

        section_labels = {
            "resources": request.env._("Learning resources"),
            "explore-areas": request.env._("Learning areas"),
            "explore-content": request.env._("Explore content"),
            "course": request.env._("Course"),
            "lesson": request.env._("Lesson"),
            "module-resources": request.env._("Module resources"),
            "courses": request.env._("Courses"),
            "roadmap": request.env._("Roadmap"),
            "roadmaps": request.env._("Roadmaps"),
            "curricular-units": request.env._("Curricular units"),
            "provenance": request.env._("Provenance"),
            "community": request.env._("Community"),
            "translation": request.env._("Translation"),
            "faq": request.env._("FAQ"),
            "ecosystem": request.env._("Ecosystem"),
            "institutional": request.env._("Project"),
            "editorial-routes": request.env._("Editorial routes"),
            "my-facodi": request.env._("My FACODI"),
            "explore-videos": request.env._("Community videos"),
            "contact": request.env._("Contact"),
            "contribution-board": request.env._("Contribution board"),
            "cta-sheet": request.env._("Contribution"),
            "learning-navigation": request.env._("Learning navigation"),
            "learning-catalogue": request.env._("Learning catalogue"),
            "submission": request.env._("Submission"),
            "submission-status": request.env._("Submission status"),
            "my-submissions": request.env._("My submissions"),
            "general": request.env._("General"),
        }
        brief_parts = []
        if source_cta:
            brief_parts.append(cta_labels.get(source_cta, request.env._("Contextual action")))
        if source_section:
            brief_parts.append(section_labels.get(source_section, source_section.replace("-", " ").title()))
        if curriculum_unit:
            brief_parts.append(curriculum_unit.name)
        elif roadmap:
            brief_parts.append(roadmap.display_name)
        elif module:
            brief_parts.append(module.name)
        elif suggested_slide:
            brief_parts.append(suggested_slide.name)
        elif course:
            brief_parts.append(course.name)
        elif area_tag:
            brief_parts.append(area_tag.name)

        contribution_brief = " · ".join(part for part in brief_parts if part)
        if not contribution_brief:
            contribution_brief = request.env._("General FACODI contribution")

        return {
            "form_values": form_values,
            "errors": [],
            "duplicate": False,
            "submission_type": submission_type,
            "curriculum_unit": curriculum_unit,
            "area_tag": area_tag,
            "roadmap": roadmap,
            "module": module,
            "course": course,
            "suggested_slide": suggested_slide,
            "source_cta": source_cta,
            "source_section": source_section,
            "source_page_url": source_page_url,
            "source_cta_label": cta_labels.get(source_cta, request.env._("Contextual action") if source_cta else ""),
            "source_section_label": section_labels.get(source_section, source_section.replace("-", " ").title() if source_section else ""),
            "contribution_brief": contribution_brief,
            "context_is_prefilled": bool(source_cta or source_section or area_tag or curriculum_unit or roadmap or module or course or suggested_slide),
            "return_url": return_url,
            "return_label": return_label,
            "submission_type_options": submission_type_options,
        }

    @http.route(
        ["/contact", "/pt/contact", "/en/contact", "/es/contact", "/fr/contact"],
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=True,
    )
    def contextual_contact_form(self, **kwargs):
        contact_kwargs = dict(kwargs)
        contact_kwargs.setdefault("type", "contact")
        contact_kwargs.setdefault("source", "contact_page")
        contact_kwargs.setdefault("section", "contact")
        return self.contextual_submission_form(**contact_kwargs)

    @http.route(
        ["/submissions/new", "/pt/submissions/new", "/en/submissions/new", "/es/submissions/new", "/fr/submissions/new", "/contribuir/recurso"],
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def contextual_submission_form(self, **kwargs):
        response = request.render(
            "facodi_learning.contextual_submission_form",
            self._submission_context_from_kwargs(kwargs),
        )
        response.headers["X-Robots-Tag"] = "noindex, follow"
        return response

    def _submission_values_from_post(self, post):
        context = self._submission_context_from_kwargs(post)
        form_values = dict(context["form_values"])
        submission_type = form_values["submission_type"]
        message = (post.get("context") or post.get("message") or "").strip()[:4000]
        name = (post.get("name") or post.get("title") or "").strip()[:200]
        contact_name = (post.get("contact_name") or "").strip()[:120]
        contact_email = (post.get("contact_email") or post.get("email") or "").strip().lower()[:254]
        organization = (post.get("organization") or "").strip()[:160]
        source_url = (post.get("source_url") or "").strip()[:2048]
        language = (post.get("language") or "").strip().lower()[:16]
        values = {
            **form_values,
            "name": name,
            "source_url": source_url,
            "context": message,
            "language": language,
            "contact_name": contact_name or False,
            "contact_email": contact_email or False,
            "organization": organization or False,
            "contact_topic": form_values.get("contact_topic") or False,
            "resource_type": (post.get("resource_type") or "video").strip()[:32],
            "resource_level": (post.get("resource_level") or "").strip()[:32] or False,
            "permission_to_contact": bool(post.get("permission_to_contact")),
        }
        errors = []
        Submission = request.env["facodi.learning.submission"]

        contextual_identifiers = (
            (
                post.get("area_id") or post.get("area"),
                context["area_tag"],
                request.env._("The learning area context is no longer publicly available."),
            ),
            (
                post.get("unit_id") or post.get("curriculum_unit_id"),
                context["curriculum_unit"],
                request.env._("The curricular unit context is no longer publicly available."),
            ),
            (
                post.get("roadmap_id") or post.get("reference_id"),
                context["roadmap"],
                request.env._("The roadmap context is no longer publicly available."),
            ),
            (
                post.get("module_id"),
                context["module"],
                request.env._("The learning module context is no longer publicly available."),
            ),
            (
                post.get("course_id") or post.get("channel_id"),
                context["course"],
                request.env._("The course context is no longer publicly available."),
            ),
            (
                post.get("slide_id") or post.get("suggested_slide_id"),
                context["suggested_slide"],
                request.env._("The learning item context is no longer publicly available."),
            ),
        )
        for raw_identifier, resolved_record, error_message in contextual_identifiers:
            if raw_identifier and not resolved_record:
                errors.append(error_message)
        if submission_type == "resource":
            youtube_identity = (
                youtube_video_identity(source_url)
                if Submission._is_valid_source_url(source_url)
                else False
            )
            if youtube_identity and (
                not values["name"]
                or not values["language"]
                or source_url != youtube_identity["source_url"]
            ):
                try:
                    discovered = submission_controller._discover_public_youtube_metadata(source_url)
                except submission_controller.MetadataDiscoveryRateLimited:
                    discovered = False
                except Exception:
                    discovered = False
                if discovered and discovered.get("supported"):
                    values["source_url"] = discovered.get("canonical_url") or source_url
                    values["name"] = values["name"] or (discovered.get("title") or "")
                    detected_language = (discovered.get("language") or "").lower()
                    detected_language = detected_language.replace("_", "-").split("-", 1)[0]
                    values["language"] = values["language"] or detected_language[:16]

            name = values["name"]
            source_url = values["source_url"]
            if not name:
                errors.append(request.env._("Enter a short title for the resource."))
            if not Submission._is_valid_source_url(source_url):
                errors.append(request.env._("Enter a valid public HTTP or HTTPS URL."))
        else:
            if not name:
                default_names = {
                    "contact": "Contact request",
                    "correction": "Correction suggestion",
                    "question": "Community question",
                }
                values["name"] = default_names.get(submission_type, "FACODI submission")
            if not message:
                errors.append(request.env._("Write a short message so FACODI can review the submission."))
            if submission_type == "contact" and not contact_email:
                errors.append(request.env._("Enter an email for follow-up."))
            if contact_email and not self._is_valid_contact_email(contact_email):
                errors.append(request.env._("Enter a valid email address."))
            if submission_type == "contact" and not values.get("contact_topic"):
                errors.append(request.env._("Choose what you are contacting FACODI about."))
        if submission_type == "resource" and contact_email and not self._is_valid_contact_email(contact_email):
            errors.append(request.env._("Enter a valid email address."))
        if values["permission_to_contact"] and not contact_email:
            errors.append(
                request.env._("Add an email address if FACODI may contact you about this submission.")
            )
        return context, values, errors

    @http.route(
        ["/submissions/new", "/pt/submissions/new", "/en/submissions/new", "/es/submissions/new", "/fr/submissions/new", "/contribuir/recurso"],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        sitemap=False,
        csrf=True,
    )
    def contextual_submission_create(self, **post):
        # Low-friction spam trap: real users never interact with this visually
        # hidden field. Do not persist its value or expose whether it fired.
        if (post.get("facodi_company_website") or "").strip():
            return request.redirect("/explore", code=303)

        context, values, errors = self._submission_values_from_post(post)
        if errors:
            context.update({"form_values": values, "errors": errors})
            return request.render("facodi_learning.contextual_submission_form", context)
        if not request.env.user._is_public():
            values["submitted_by_id"] = request.env.user.id
        try:
            submission = request.env["facodi.learning.submission"].sudo().create(values)
        except ValidationError as exc:
            context.update(
                {
                    "form_values": values,
                    "errors": [str(exc)],
                }
            )
            return request.render("facodi_learning.contextual_submission_form", context)
        except Exception:
            context.update(
                {
                    "form_values": values,
                    "errors": [request.env._("The submission could not be saved. Check the fields and try again.")],
                }
            )
            return request.render("facodi_learning.contextual_submission_form", context)
        return request.redirect("/contribuir/recurso/status/%s" % submission.access_token, code=303)
