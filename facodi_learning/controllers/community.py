from urllib.parse import urlencode

from odoo import http
from odoo.http import request


class FacodiCommunityController(http.Controller):
    """Bridge FACODI learning context into Odoo's native forum composer."""

    @staticmethod
    def _forum():
        if "forum.forum" not in request.env.registry.models:
            return False
        return (
            request.env["forum.forum"]
            .sudo()
            .search(
                [("website_id", "in", [False, request.website.id])],
                order="website_id desc, id",
                limit=1,
            )
        )

    @staticmethod
    def _positive_int(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return False
        return value if value > 0 else False

    @staticmethod
    def _public_course(course_id):
        if not course_id:
            return False
        return (
            request.env["slide.channel"]
            .sudo()
            .search(
                [
                    ("id", "=", course_id),
                    ("active", "=", True),
                    ("website_published", "=", True),
                    ("visibility", "=", "public"),
                    ("website_id", "in", [False, request.website.id]),
                ],
                limit=1,
            )
        )

    @staticmethod
    def _public_slide(slide_id):
        if not slide_id:
            return False
        return (
            request.env["slide.slide"]
            .sudo()
            .search(
                [
                    ("id", "=", slide_id),
                    ("active", "=", True),
                    ("website_published", "=", True),
                    ("channel_id.active", "=", True),
                    ("channel_id.website_published", "=", True),
                    ("channel_id.visibility", "=", "public"),
                    ("channel_id.website_id", "in", [False, request.website.id]),
                ],
                limit=1,
            )
        )

    @staticmethod
    def _public_unit(unit_id):
        if not unit_id:
            return False
        return (
            request.env["facodi.learning.curriculum.unit"]
            .sudo()
            .search(
                [
                    ("id", "=", unit_id),
                    ("reference_id.website_published", "=", True),
                    ("reference_id.validated_at", "!=", False),
                ],
                limit=1,
            )
        )

    @http.route(
        "/community/new",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def contextual_forum_post(self, **kwargs):
        forum = self._forum()
        if not forum:
            return request.redirect("/forum")

        kind = kwargs.get("kind") if kwargs.get("kind") in {"question", "share"} else "question"
        unit = self._public_unit(self._positive_int(kwargs.get("unit_id")))
        slide = self._public_slide(self._positive_int(kwargs.get("slide_id")))
        course = self._public_course(self._positive_int(kwargs.get("course_id")))
        if slide and not course:
            course = slide.channel_id

        context_label = "FACODI"
        context_url = request.httprequest.referrer or "/"
        if unit:
            code = unit.external_unit_code or ""
            context_label = f"{code} — {unit.name}" if code else unit.name
            context_url = unit._facodi_public_catalog_path()
        elif slide:
            context_label = f"{slide.channel_id.name} — {slide.name}"
            context_url = slide.website_url
        elif course:
            context_label = course.name
            context_url = f"/slides/{request.env['ir.http']._slug(course)}"

        if kind == "share":
            title = f"Partilha: {context_label}"
            intro = "Quero partilhar esta informação/recurso com a comunidade FACODI."
            prompt = "O que estás a partilhar e porque pode ser útil para outras pessoas?"
        else:
            title = f"Dúvida: {context_label}"
            intro = "Tenho uma dúvida neste contexto de aprendizagem."
            prompt = "O que estás a tentar compreender? Explica o que já tentaste e onde surgiu a dúvida."

        content = (
            f"<p><strong>Contexto:</strong> {context_label}</p>"
            f"<p>{intro}</p>"
            f"<p><br></p><p><em>{prompt}</em></p>"
            f"<p><br></p><p><small>Referência FACODI: {context_url}</small></p>"
        )
        slug = request.env["ir.http"]._slug
        query = urlencode(
            {
                "facodi_context": "1",
                "facodi_kind": kind,
                "facodi_title": title,
                "facodi_content": content,
                "facodi_label": context_label,
            }
        )
        return request.redirect(f"/forum/{slug(forum)}/ask?{query}")
