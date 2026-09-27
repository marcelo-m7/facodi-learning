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
        self.assertIn("_public_roadmap", controller)
        self.assertIn("_public_course", controller)
        self.assertIn("_public_slide", controller)
        self.assertIn("_discover_public_youtube_metadata", controller)

    def test_template_has_contextual_form_contract(self):
        template = self._read("views/website_contextual_submission.xml")
        self.assertIn('data-facodi-submission-form="1"', template)
        self.assertIn('name="submission_type"', template)
        self.assertIn('name="source_cta"', template)
        self.assertIn('name="source_section"', template)
        self.assertIn("You are contributing in this context", template)
        self.assertIn('data-facodi-resource-submission', template)
        self.assertIn('id="facodi_submission_name"', template)
        self.assertIn("Context pre-filled", template)
        self.assertIn("form_values.get('resource_type'", template)
        self.assertIn("form_values.get('language'", template)
        self.assertIn("form_values.get('resource_level'", template)
        self.assertIn("form_values.get('permission_to_contact')", template)
        self.assertIn('name="curriculum_unit_id"', template)
        self.assertNotIn("Classic resource form", template)

    def test_curriculum_ctas_pass_context(self):
        template = self._read("views/website_curriculum_contextual_ctas.xml")
        self.assertIn("/submissions/new?type=resource", template)
        self.assertIn("unit_id=", template)
        self.assertIn("source=unit_resource_cta", template)
        self.assertIn("section=resources", template)
        self.assertIn("source=community_margin", template)
        self.assertIn("roadmap_detail_contextual_resource_cta", template)
        self.assertIn("roadmap_id=%s", template)
        self.assertIn("source=roadmap_resource_cta", template)
        self.assertIn("source=roadmaps_catalog_cta", template)
        self.assertIn("source=curricular_units_catalog_cta", template)
        self.assertIn("type=correction", template)
        self.assertIn("source=unit_correction_cta", template)
        self.assertIn("source=roadmap_correction_cta", template)

    def test_admin_views_expose_context(self):
        arch = self._read("views/contextual_submission_admin_views.xml")
        self.assertIn("submission_type", arch)
        self.assertIn("source_cta", arch)
        self.assertIn("source_section", arch)
        self.assertIn("contact_email", arch)

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
