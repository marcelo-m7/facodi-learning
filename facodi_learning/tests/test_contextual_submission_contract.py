from pathlib import Path

from odoo.tests.common import TransactionCase


MODULE_ROOT = Path(__file__).resolve().parents[1]


class TestContextualSubmissionModelContract(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Submission = cls.env["facodi.learning.submission"]

    def test_normalize_submission_type_falls_back_to_resource(self):
        self.assertEqual(self.Submission._normalize_submission_type("nonsense"), "resource")
        self.assertEqual(self.Submission._normalize_submission_type("CONTACT"), "contact")

    def test_context_slug_rejects_long_or_unsafe_values(self):
        self.assertTrue(self.Submission._is_valid_context_slug("unit_resource_cta"))
        self.assertFalse(self.Submission._is_valid_context_slug("../../etc/passwd"))
        self.assertFalse(self.Submission._is_valid_context_slug("x" * 80))

    def test_resource_url_validation_still_rejects_private_urls(self):
        self.assertFalse(self.Submission._is_valid_source_url("http://127.0.0.1/private"))
        self.assertFalse(self.Submission._is_valid_source_url("https://user:pass@example.com"))

    def test_new_fields_exist_on_submission_model(self):
        for field_name in (
            "submission_type",
            "source_cta",
            "source_section",
            "source_page_url",
            "roadmap_id",
            "course_id",
            "suggested_slide_id",
            "contact_name",
            "contact_email",
            "organization",
            "contact_topic",
            "resource_type",
            "resource_level",
            "permission_to_contact",
        ):
            self.assertIn(field_name, self.Submission._fields)


class TestContextualSubmissionStaticContracts(TransactionCase):
    def _read(self, relative_path):
        return (MODULE_ROOT / relative_path).read_text(encoding="utf-8")

    def test_controller_exposes_contextual_routes_and_aliases(self):
        controller = self._read("controllers/contextual_submission.py")
        self.assertIn('"/submissions/new"', controller)
        self.assertIn('"/contribuir/recurso"', controller)
        self.assertIn('"/pt/submissions/new"', controller)
        self.assertIn('"/en/submissions/new"', controller)
        self.assertIn("unit_id", controller)
        self.assertIn("_normalize_submission_type", controller)
        self.assertIn("community_video_cta", controller)
        self.assertIn("portal_resource_cta", controller)
        self.assertIn("request.httprequest.referrer", controller)
        self.assertIn("contact_name", controller)
        self.assertIn("contact_email", controller)
        self.assertIn("_safe_origin_path", controller)
        self.assertIn("contact_topic_defaults", controller)
        self.assertIn("source_cta_label", controller)
        self.assertIn("_public_roadmap", controller)
        self.assertIn("_public_course", controller)
        self.assertIn("_public_slide", controller)
        self.assertIn("_discover_public_youtube_metadata", controller)
        self.assertIn('"return_url": return_url', controller)
        self.assertIn('"return_label": return_label', controller)
        self.assertIn("_facodi_public_catalog_path", controller)
        self.assertIn("suggested_slide.website_url", controller)
        self.assertIn("course.website_url", controller)
        self.assertIn("study_player_resource_cta", controller)
        self.assertIn("study_player_correction_cta", controller)
        self.assertIn('"lesson": request.env._("Lesson")', controller)
        self.assertLess(
            controller.index("elif suggested_slide:"),
            controller.index("elif course:", controller.index("elif suggested_slide:")),
        )

    def test_template_has_contextual_form_contract(self):
        template = self._read("views/website_contextual_submission.xml")
        self.assertIn('data-facodi-submission-form="1"', template)
        self.assertIn('name="submission_type"', template)
        self.assertIn('name="source_cta"', template)
        self.assertIn('name="source_section"', template)
        self.assertIn("You are contributing in this context", template)
        self.assertIn('data-facodi-resource-submission', template)
        self.assertIn('id="facodi_submission_name"', template)
        title_field = template.split('id="facodi_submission_name"', 1)[1].split("</div>", 1)[0]
        self.assertNotIn("required=", title_field)
        self.assertNotIn("t-att-required", title_field)
        self.assertIn("A title is still required when you submit the resource for review.", template)
        self.assertIn("Context pre-filled", template)
        self.assertIn("form_values.get('resource_type'", template)
        self.assertIn("form_values.get('language'", template)
        self.assertIn("form_values.get('resource_level'", template)
        self.assertIn("form_values.get('permission_to_contact')", template)
        self.assertIn('name="contact_topic"', template)
        self.assertIn("source_cta_label", template)
        self.assertNotIn('<code t-esc="source_cta"', template)
        self.assertIn('name="curriculum_unit_id"', template)
        self.assertNotIn("Classic resource form", template)
        self.assertIn('t-att-href="return_url"', template)
        self.assertIn('t-esc="return_label"', template)
        self.assertIn("submission_type != 'resource'", template)

    def test_curriculum_ctas_pass_context(self):
        curriculum = self._read("views/website_curriculum.xml")
        additive = self._read("views/website_curriculum_contextual_ctas.xml")
        self.assertIn("/submissions/new?type=resource", curriculum)
        self.assertIn("unit_id=%s", curriculum)
        self.assertIn("source=unit_resource_cta", curriculum)
        self.assertIn("section=resources", curriculum)
        self.assertIn("source=community_margin", curriculum)
        self.assertIn("roadmap_id=%s", curriculum)
        self.assertIn("source=roadmap_resource_cta", curriculum)
        self.assertIn("source=roadmaps_catalog_cta", curriculum)
        self.assertIn("source=curricular_units_catalog_cta", curriculum)
        self.assertNotIn("/contribuir/recurso?curriculum_unit_id=", curriculum)
        self.assertIn("type=correction", additive)
        self.assertIn("source=unit_correction_cta", additive)
        self.assertIn("source=roadmap_correction_cta", additive)
        self.assertNotIn("position=\"attributes\"", additive)
        self.assertNotIn("normalize-space()", additive)
        for hook in (
            "data-facodi-unit-community-resource-cta",
            "data-facodi-unit-resource-cta",
            "data-facodi-unit-catalogue-resource-cta",
            "data-facodi-roadmap-resource-cta",
            "data-facodi-unit-provenance",
            "data-facodi-roadmap-provenance",
        ):
            self.assertIn(hook, curriculum)

    def test_admin_views_expose_context(self):
        arch = self._read("views/contextual_submission_admin_views.xml")
        self.assertIn("submission_type", arch)
        self.assertIn("source_cta", arch)
        self.assertIn("source_section", arch)
        self.assertIn("contact_email", arch)
        for marker in (
            "filter_resource_submission",
            "filter_contact_submission",
            "filter_correction_submission",
            "filter_question_submission",
            "group_source_section",
            "group_curriculum_unit",
            "group_course",
        ):
            self.assertIn(marker, arch)

    def test_major_public_ctas_use_contextual_submission_entrypoint(self):
        slides = self._read("views/website_slides.xml")
        explore = self._read("views/website_explore.xml")
        portal = self._read("views/portal_home.xml")
        self.assertIn("source=course_resource_cta", slides)
        self.assertIn("course_id=%s", slides)
        self.assertIn("type=contact", slides)
        self.assertIn("source=course_contact_cta", slides)
        self.assertIn("source=explore_empty_shelf", explore)
        self.assertIn("source=community_video_cta", explore)
        self.assertIn("resource_type=video", explore)
        self.assertIn("source=portal_resource_cta", portal)

        curriculum = self._read("views/website_curriculum.xml")
        legacy_submission = self._read("views/website_submission.xml")
        self.assertIn("source=my_submissions_new", legacy_submission)
        self.assertIn("source=my_submissions_empty", legacy_submission)
        self.assertIn("section=my-submissions", legacy_submission)
        self.assertNotIn('href="/contribuir/recurso"', curriculum)
        self.assertIn("source=roadmaps_catalog_cta", curriculum)
        self.assertIn("source=curricular_units_catalog_cta", curriculum)
        self.assertIn("source=curricular_units_empty_state", curriculum)
        self.assertNotIn('href="/contactus" class="btn btn-link">Other contribution', legacy_submission)
        self.assertIn("source=legacy_submission_followup", legacy_submission)

    def test_submission_status_followup_preserves_full_context(self):
        template = self._read("views/website_submission.xml")
        controller = self._read("controllers/submission.py")
        self.assertIn('t-att-href="followup_submission_url"', template)
        self.assertIn('"source": "submission_status_followup"', controller)
        self.assertIn('"section": "submission-status"', controller)
        for key in ("unit_id", "roadmap_id", "course_id", "slide_id"):
            self.assertIn(f'followup_params["{key}"]', controller)
        self.assertIn("urlencode(followup_params)", controller)
        self.assertNotIn('followup_params["source_page_url"]', controller)
        for label in (
            "Learning navigation",
            "Learning catalogue",
            "Submission follow-up",
            "Submission status",
        ):
            self.assertIn(label, self._read("controllers/contextual_submission.py"))
        self.assertNotIn("/contribuir/recurso?curriculum_unit_id=", template)
