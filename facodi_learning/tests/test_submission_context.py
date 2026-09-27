from lxml import html

from odoo.tests import HttpCase, TransactionCase, tagged

from ..services.curriculum_bootstrap import ensure_lesti_2026_27


class TestSubmissionContextModel(TransactionCase):
    def test_source_url_normalization_is_stable_for_duplicate_checks(self):
        Submission = self.env["facodi.learning.submission"]
        self.assertEqual(
            Submission._normalize_source_url(
                "HTTPS://Example.org:443/resource/#section"
            ),
            "https://example.org/resource",
        )
        self.assertEqual(
            Submission._normalize_source_url(
                "https://example.org/resource?b=2&a=1"
            ),
            "https://example.org/resource?b=2&a=1",
        )


@tagged("-at_install", "post_install")
class TestSubmissionContextWebsite(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reference = ensure_lesti_2026_27(cls.env)
        cls.database_unit = cls.reference.unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19411017"
        )
        cls.programming_unit = cls.reference.unit_ids.filtered(
            lambda unit: unit.external_unit_code == "19411000"
        )
        cls.private_reference = cls.env[
            "facodi.learning.curriculum.reference"
        ].create(
            {
                "institution": "Private",
                "programme_name": "Private",
                "academic_year": "2026/27",
                "provider": "manual",
                "external_id": "private-submission-context",
            }
        )
        cls.private_unit = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.private_reference.id,
                "external_unit_code": "PRIVATE-SUBMISSION",
                "name": "Private Submission Unit",
            }
        )
        cls.public_module = cls.env["facodi.learning.curriculum.module"].create(
            {
                "name": "Public Contribution Module",
                "website_published": True,
            }
        )
        cls.private_module = cls.env["facodi.learning.curriculum.module"].create(
            {
                "name": "Private Contribution Module",
                "website_published": False,
            }
        )

    def _csrf_token(self, route="/contribuir/recurso"):
        response = self.url_open(route)
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        tokens = tree.xpath('//input[@name="csrf_token"]/@value')
        self.assertEqual(len(tokens), 1)
        return tokens[0]

    def test_legacy_resource_url_uses_contextual_form(self):
        response = self.url_open("/contribuir/recurso")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-facodi-submission-form="1"', response.text)
        self.assertIn("Submission details", response.text)
        self.assertNotIn("Classic resource form", response.text)

    def test_private_roadmap_context_is_not_disclosed(self):
        response = self.url_open(
            "/submissions/new?type=resource&roadmap_id=%s"
            % self.private_reference.id
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.private_reference.programme_name, response.text)
        tree = html.fromstring(response.text)
        self.assertFalse(tree.xpath('//input[@name="roadmap_id"]/@value'))

    def test_module_context_is_prefilled_persisted_and_private_modules_are_rejected(self):
        route = (
            "/submissions/new?type=resource&module_id=%s"
            "&source=module_resource_cta&section=module-resources"
            % self.public_module.id
        )
        response = self.url_open(route)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.public_module.name, response.text)
        self.assertIn("Learning module resources", response.text)
        self.assertIn("I suggest this resource for this learning module.", response.text)
        tree = html.fromstring(response.text)
        self.assertEqual(
            tree.xpath('//input[@name="module_id"]/@value'),
            [str(self.public_module.id)],
        )

        created = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": tree.xpath('//input[@name="csrf_token"]/@value')[0],
                "submission_type": "resource",
                "module_id": str(self.public_module.id),
                "source_cta": "module_resource_cta",
                "source_section": "module-resources",
                "name": "Module-context resource",
                "source_url": "https://example.org/module-context",
                "context": "Useful for this reusable module.",
            },
        )
        self.assertEqual(created.status_code, 200)
        submission = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "Module-context resource")],
            order="id desc",
            limit=1,
        )
        self.assertEqual(submission.module_id, self.public_module)

        another_module = self.env["facodi.learning.curriculum.module"].create(
            {
                "name": "Another Public Contribution Module",
                "website_published": True,
            }
        )
        another_route = (
            "/submissions/new?type=resource&module_id=%s"
            "&source=module_resource_cta&section=module-resources"
            % another_module.id
        )
        another_page = self.url_open(another_route)
        another_tree = html.fromstring(another_page.text)
        another_created = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": another_tree.xpath('//input[@name="csrf_token"]/@value')[0],
                "submission_type": "resource",
                "module_id": str(another_module.id),
                "source_cta": "module_resource_cta",
                "source_section": "module-resources",
                "name": "Same resource in another module",
                "source_url": "https://example.org/module-context",
                "context": "The same public resource is useful in another reusable module.",
            },
        )
        self.assertEqual(another_created.status_code, 200)
        second = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "Same resource in another module")],
            limit=1,
        )
        self.assertEqual(second.module_id, another_module)

        private_route = (
            "/submissions/new?type=resource&module_id=%s"
            "&source=module_resource_cta&section=module-resources"
            % self.private_module.id
        )
        private = self.url_open(private_route)
        self.assertEqual(private.status_code, 200)
        private_tree = html.fromstring(private.text)
        self.assertFalse(private_tree.xpath('//input[@name="module_id"]/@value'))
        self.assertNotIn(self.private_module.name, private.text)

        rejected = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": private_tree.xpath('//input[@name="csrf_token"]/@value')[0],
                "submission_type": "resource",
                "module_id": str(self.private_module.id),
                "source_cta": "module_resource_cta",
                "source_section": "module-resources",
                "name": "Private module resource",
                "source_url": "https://example.org/private-module-context",
            },
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertIn(
            "The learning module context is no longer publicly available.",
            rejected.text,
        )
        self.assertFalse(
            self.env["facodi.learning.submission"].sudo().search(
                [("name", "=", "Private module resource")],
                limit=1,
            )
        )

    def test_correction_requires_authored_message_but_not_email(self):
        route = (
            "/submissions/new?type=correction&unit_id=%s"
            "&source=unit_correction_cta&section=provenance"
            % self.database_unit.id
        )
        response = self.url_open(route)
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        textarea = tree.xpath('//textarea[@name="context"]')[0]
        self.assertEqual((textarea.text or "").strip(), "")
        self.assertEqual(
            tree.xpath('//input[@name="contact_email"]/@required'),
            [],
        )

        token = tree.xpath('//input[@name="csrf_token"]/@value')[0]
        missing_message = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": token,
                "submission_type": "correction",
                "unit_id": str(self.database_unit.id),
                "source_cta": "unit_correction_cta",
                "source_section": "provenance",
                "context": "",
            },
        )
        self.assertEqual(missing_message.status_code, 200)
        self.assertIn(
            "Write a short message so FACODI can review the submission.",
            missing_message.text,
        )

        token = html.fromstring(missing_message.text).xpath(
            '//input[@name="csrf_token"]/@value'
        )[0]
        created = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": token,
                "submission_type": "correction",
                "unit_id": str(self.database_unit.id),
                "source_cta": "unit_correction_cta",
                "source_section": "provenance",
                "context": "The source period shown here needs editorial review.",
            },
        )
        self.assertEqual(created.status_code, 200)
        submission = self.env["facodi.learning.submission"].sudo().search(
            [
                ("submission_type", "=", "correction"),
                ("curriculum_unit_id", "=", self.database_unit.id),
            ],
            order="id desc",
            limit=1,
        )
        self.assertTrue(submission)
        self.assertEqual(submission.contact_email, False)

    def test_theme_resource_ctas_render_human_context_and_prefill(self):
        cases = (
            ("community_resource_cta", "community", "Community resource", "community learning trail"),
            ("ecosystem_resource_cta", "ecosystem", "Ecosystem contribution", "open-learning ecosystem"),
            ("cta_sheet_resource_cta", "cta-sheet", "Shared learning notebook", "shared FACODI learning notebook"),
            ("contact_sheet_resource_cta", "contact", "Contact page resource", "learning resource for editorial review"),
            ("contribution_board_resource_cta", "contribution-board", "Contribution board", "public resource for FACODI editorial review"),
        )
        for source, section, label, prefill in cases:
            response = self.url_open(
                "/submissions/new?type=resource&source=%s&section=%s"
                % (source, section)
            )
            self.assertEqual(response.status_code, 200, source)
            self.assertIn(label, response.text, source)
            self.assertIn(prefill, response.text, source)
            self.assertNotIn("Contextual action", response.text, source)

    def test_study_player_ctas_have_specific_human_context(self):
        resource = self.url_open(
            "/submissions/new?type=resource&source=study_player_resource_cta"
            "&section=lesson"
        )
        self.assertEqual(resource.status_code, 200)
        self.assertIn("Lesson resources", resource.text)
        self.assertIn("useful companion to this lesson", resource.text)
        self.assertNotIn("Contextual action", resource.text)

        correction = self.url_open(
            "/submissions/new?type=correction&source=study_player_correction_cta"
            "&section=lesson"
        )
        self.assertEqual(correction.status_code, 200)
        self.assertIn("Lesson problem report", correction.text)
        self.assertIn(">Lesson<", correction.text)
        self.assertNotIn("Contextual action", correction.text)

    def test_contact_requires_message_and_email(self):
        response = self.url_open(
            "/submissions/new?type=contact&source=general_contact_cta&section=general"
        )
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        self.assertEqual(
            tree.xpath('//input[@name="contact_email"]/@required'),
            ["required"],
        )
        token = tree.xpath('//input[@name="csrf_token"]/@value')[0]
        invalid = self.url_open(
            "/submissions/new",
            data={
                "csrf_token": token,
                "submission_type": "contact",
                "source_cta": "general_contact_cta",
                "source_section": "general",
                "context": "I would like to talk about contributing.",
                "contact_email": "",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertIn("Enter an email for follow-up.", invalid.text)

    def test_contextual_form_persists_only_public_curricular_unit(self):
        route = (
            "/contribuir/recurso?curriculum_unit_id=%s"
            % self.database_unit.id
        )
        response = self.url_open(route)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.database_unit.name, response.text)
        tree = html.fromstring(response.text)
        self.assertEqual(
            tree.xpath('//input[@name="curriculum_unit_id"]/@value'),
            [str(self.database_unit.id)],
        )

        before_coverage = self.env[
            "facodi.learning.curriculum.coverage"
        ].sudo().search_count([])
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(route),
                "name": "Contextual database resource",
                "source_url": "https://example.org/contextual-database",
                "curriculum_unit_id": str(self.database_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        submission = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "Contextual database resource")],
            limit=1,
        )
        self.assertEqual(submission.curriculum_unit_id, self.database_unit)
        self.assertIn(self.database_unit.name, response.text)
        self.assertEqual(
            self.env[
                "facodi.learning.curriculum.coverage"
            ].sudo().search_count([]),
            before_coverage,
        )

    def test_private_or_forged_curricular_context_is_not_persisted(self):
        before = self.env["facodi.learning.submission"].sudo().search_count([])
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(),
                "name": "Forged context",
                "source_url": "https://example.org/forged-context",
                "curriculum_unit_id": str(self.private_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "The curricular unit context is no longer publicly available.",
            response.text,
        )
        self.assertEqual(
            self.env["facodi.learning.submission"].sudo().search_count([]),
            before,
        )

    def test_active_duplicate_is_suppressed_without_leaking_tracking_token(self):
        first = self.env["facodi.learning.submission"].sudo().create(
            {
                "name": "Existing contextual suggestion",
                "source_url": "https://EXAMPLE.org:443/duplicate/#section",
                "curriculum_unit_id": self.database_unit.id,
            }
        )
        before = self.env["facodi.learning.submission"].sudo().search_count([])
        route = (
            "/contribuir/recurso?curriculum_unit_id=%s"
            % self.database_unit.id
        )
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(route),
                "name": "Duplicate contextual suggestion",
                "source_url": "https://example.org/duplicate",
                "curriculum_unit_id": str(self.database_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "already under editorial review for this context",
            response.text,
        )
        self.assertNotIn(first.access_token, response.text)
        self.assertEqual(
            self.env["facodi.learning.submission"].sudo().search_count([]),
            before,
        )

        other_route = (
            "/contribuir/recurso?curriculum_unit_id=%s"
            % self.programming_unit.id
        )
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(other_route),
                "name": "Same resource, different curricular unit",
                "source_url": "https://example.org/duplicate",
                "curriculum_unit_id": str(self.programming_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        second = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "Same resource, different curricular unit")],
            limit=1,
        )
        self.assertEqual(second.curriculum_unit_id, self.programming_unit)

    def test_rejected_history_does_not_block_resubmission(self):
        previous = self.env["facodi.learning.submission"].sudo().create(
            {
                "name": "Historical suggestion",
                "source_url": "https://example.org/history",
                "curriculum_unit_id": self.database_unit.id,
            }
        )
        previous.sudo().action_reject()

        route = (
            "/contribuir/recurso?curriculum_unit_id=%s"
            % self.database_unit.id
        )
        response = self.url_open(
            "/contribuir/recurso",
            data={
                "csrf_token": self._csrf_token(route),
                "name": "New suggestion after rejection",
                "source_url": "https://example.org/history",
                "curriculum_unit_id": str(self.database_unit.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        current = self.env["facodi.learning.submission"].sudo().search(
            [("name", "=", "New suggestion after rejection")],
            limit=1,
        )
        self.assertTrue(current)
        self.assertEqual(current.state, "submitted")
