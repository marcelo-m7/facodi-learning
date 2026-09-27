from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from .submission import (
    FacodiSubmissionController,
    MetadataDiscoveryRateLimited,
    _discover_public_youtube_metadata,
)
from ..services.youtube import youtube_video_identity


class FacodiContextualSubmissionController(FacodiSubmissionController):
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

    def _submission_context_from_kwargs(self, kwargs):
        Submission = request.env["facodi.learning.submission"]
        submission_type = Submission._normalize_submission_type(kwargs.get("type") or kwargs.get("submission_type"))
        curriculum_unit = self._public_curriculum_unit(kwargs.get("unit_id") or kwargs.get("curriculum_unit_id"))
        roadmap = self._public_roadmap(
            kwargs.get("roadmap_id") or kwargs.get("reference_id")
        )
        course = self._public_course(
            kwargs.get("course_id") or kwargs.get("channel_id")
        )
        suggested_slide = self._public_slide(
            kwargs.get("slide_id") or kwargs.get("suggested_slide_id")
        )
        source_cta = Submission._clean_context_slug(kwargs.get("source") or kwargs.get("source_cta"))
        source_section = Submission._clean_context_slug(kwargs.get("section") or kwargs.get("source_section"))
        source_page_url = self._bounded_text(
            kwargs.get("source_page_url") or kwargs.get("origin"),
            2048,
        )
        if not source_page_url:
            referrer = request.httprequest.referrer or ""
            website_url = (request.website.get_base_url() or "").rstrip("/")
            if website_url and referrer.startswith(website_url + "/"):
                source_page_url = referrer[:2048]

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

        form_values = {
            "submission_type": submission_type,
            "source_cta": source_cta,
            "source_section": source_section,
            "source_page_url": source_page_url,
            "resource_type": resource_type,
            "resource_level": resource_level,
            "language": language,
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
        elif course:
            profile_context = request.env._(
                "Suggested for course: %s."
            ) % course.name
        elif suggested_slide:
            profile_context = request.env._(
                "Suggested around learning item: %s."
            ) % suggested_slide.name

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
            "course_resource_cta": request.env._(
                "I suggest this resource as a useful companion to this course."
            ),
            "explore_empty_shelf": request.env._(
                "I found a resource that is missing from the current FACODI catalogue."
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
            "course_catalog_cta": request.env._(
                "I found a resource that could strengthen the FACODI course catalogue."
            ),
        }
        if not form_values["context"] and submission_type == "resource":
            form_values["context"] = " ".join(
                part for part in (profile_context, cta_defaults.get(source_cta, "")) if part
            )
        if curriculum_unit:
            form_values["curriculum_unit_id"] = curriculum_unit.id
        if roadmap:
            form_values["roadmap_id"] = roadmap.id
        if course:
            form_values["course_id"] = course.id
        if suggested_slide:
            form_values["suggested_slide_id"] = suggested_slide.id
        return {
            "form_values": form_values,
            "errors": [],
            "duplicate": False,
            "submission_type": submission_type,
            "curriculum_unit": curriculum_unit,
            "roadmap": roadmap,
            "course": course,
            "suggested_slide": suggested_slide,
            "source_cta": source_cta,
            "source_section": source_section,
            "source_page_url": source_page_url,
        }

    @http.route(
        ["/submissions/new", "/pt/submissions/new", "/en/submissions/new", "/contribuir/recurso"],
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=True,
    )
    def contextual_submission_form(self, **kwargs):
        return request.render(
            "facodi_learning.contextual_submission_form",
            self._submission_context_from_kwargs(kwargs),
        )

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
            "contact_name": contact_name,
            "contact_email": contact_email,
            "organization": organization,
            "resource_type": (post.get("resource_type") or "video").strip()[:32],
            "resource_level": (post.get("resource_level") or "").strip()[:32] or False,
            "permission_to_contact": bool(post.get("permission_to_contact")),
        }
        errors = []
        Submission = request.env["facodi.learning.submission"]
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
                    discovered = _discover_public_youtube_metadata(source_url)
                except MetadataDiscoveryRateLimited:
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
            if not contact_email:
                errors.append(request.env._("Enter an email for follow-up."))
        return context, values, errors

    @http.route(
        ["/submissions/new", "/pt/submissions/new", "/en/submissions/new", "/contribuir/recurso"],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        sitemap=False,
        csrf=True,
    )
    def contextual_submission_create(self, **post):
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
