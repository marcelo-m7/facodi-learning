from odoo import http
from odoo.http import request

from .submission import FacodiSubmissionController


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

    def _submission_context_from_kwargs(self, kwargs):
        Submission = request.env["facodi.learning.submission"]
        submission_type = Submission._normalize_submission_type(kwargs.get("type") or kwargs.get("submission_type"))
        curriculum_unit = self._public_curriculum_unit(kwargs.get("unit_id") or kwargs.get("curriculum_unit_id"))
        roadmap = self._public_record(
            "facodi.learning.curriculum.reference",
            kwargs.get("roadmap_id") or kwargs.get("reference_id"),
        )
        course = self._public_record(
            "slide.channel",
            kwargs.get("course_id") or kwargs.get("channel_id"),
            website_field="website_published",
        )
        suggested_slide = self._public_record(
            "slide.slide",
            kwargs.get("slide_id") or kwargs.get("suggested_slide_id"),
            website_field="website_published",
        )
        source_cta = Submission._clean_context_slug(kwargs.get("source") or kwargs.get("source_cta"))
        source_section = Submission._clean_context_slug(kwargs.get("section") or kwargs.get("source_section"))
        source_page_url = (kwargs.get("source_page_url") or kwargs.get("origin") or "").strip()[:2048]

        form_values = {
            "submission_type": submission_type,
            "source_cta": source_cta,
            "source_section": source_section,
            "source_page_url": source_page_url,
        }
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
        ["/submissions/new", "/pt/submissions/new", "/en/submissions/new"],
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
        ["/submissions/new", "/pt/submissions/new", "/en/submissions/new"],
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
        except Exception:
            context.update(
                {
                    "form_values": values,
                    "errors": [request.env._("The submission could not be saved. Check the fields and try again.")],
                }
            )
            return request.render("facodi_learning.contextual_submission_form", context)
        return request.redirect("/contribuir/recurso/status/%s" % submission.access_token, code=303)
