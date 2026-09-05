from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCourseSelection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Course Selection Manager",
                "login": "course-selection-manager",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.officer = cls.env["res.users"].create(
            {
                "name": "Course Selection Officer",
                "login": "course-selection-officer",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(
                                "website_slides.group_website_slides_officer"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.channel = cls.env["slide.channel"].create({"name": "Python Basics"})
        cls.other_channel = cls.env["slide.channel"].create({"name": "Databases"})

    def _candidate_values(self, **extra):
        values = {
            "provider": "manual",
            "external_id": "manual-python-1",
            "name": "Python Fundamentals",
            "description": "Programming foundations using Python.",
            "institution": "FACODI",
            "language": "pt",
            "level": "beginner",
            "duration_minutes": 600,
        }
        values.update(extra)
        return values

    def test_candidate_identity_is_unique(self):
        Candidate = self.env["facodi.learning.course.candidate"]
        Candidate.create(self._candidate_values())
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            Candidate.create(self._candidate_values())

    def test_candidate_cannot_forge_terminal_state_or_decision(self):
        Candidate = self.env["facodi.learning.course.candidate"]
        for values in (
            {"state": "resolved"},
            {"decision_origin": "automatic"},
            {"resolved_channel_id": self.channel.id},
        ):
            with self.assertRaises(AccessError):
                Candidate.create(self._candidate_values(**values))

    def test_provider_and_external_identity_are_immutable(self):
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values()
        )
        with self.assertRaises(AccessError):
            candidate.write({"external_id": "changed"})
        with self.assertRaises(AccessError):
            candidate.write({"provider": "other"})

    def test_unresolved_metadata_can_be_refreshed(self):
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values()
        )
        candidate.write(
            {"description": "Updated description", "metadata": {"v": 2}}
        )
        self.assertEqual(candidate.description, "Updated description")
        self.assertEqual(candidate.metadata, {"v": 2})

    def test_title_duplicate_is_detected_deterministically(self):
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(
                name="  PYTHON basics  ", external_id="manual-title-duplicate"
            )
        )
        candidate.action_evaluate()
        self.assertEqual(candidate.matched_channel_id, self.channel)
        self.assertEqual(candidate.duplication_risk, 1.0)
        self.assertEqual(candidate.recommendation, "review_existing_match")

    def test_manual_candidate_has_deterministic_local_scores(self):
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(
                name="Unique Systems Course", external_id="manual-scores"
            )
        )
        candidate.action_evaluate()
        first = (
            candidate.relevance_score,
            candidate.metadata_quality_score,
            candidate.language_fit_score,
            candidate.coverage_score,
            candidate.duplication_risk,
            candidate.recommendation,
            candidate.evaluation_reasons,
        )
        candidate.action_evaluate()
        second = (
            candidate.relevance_score,
            candidate.metadata_quality_score,
            candidate.language_fit_score,
            candidate.coverage_score,
            candidate.duplication_risk,
            candidate.recommendation,
            candidate.evaluation_reasons,
        )
        self.assertEqual(first, second)
        self.assertEqual(candidate.evaluation_policy_version, "course-evaluation-v1")
        self.assertEqual(candidate.coverage_score, 1.0)
        self.assertEqual(candidate.state, "evaluated")

    def test_selection_policy_defaults_to_manual(self):
        from odoo.addons.facodi_learning.services.course_selection import (
            get_course_selection_policy,
        )

        policy = get_course_selection_policy(self.env)
        self.assertEqual(policy["mode"], "manual")
        self.assertIn("manual", policy["trusted_providers"])

    def test_auto_policy_is_fail_closed_on_duplicate_risk(self):
        from odoo.addons.facodi_learning.services.course_selection import (
            candidate_is_auto_approve_eligible,
            get_course_selection_policy,
        )

        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_learning.course_selection_mode", "auto"
        )
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(name="Python Basics", external_id="policy-dup")
        )
        candidate.action_evaluate()
        eligible, reasons = candidate_is_auto_approve_eligible(
            candidate, get_course_selection_policy(self.env)
        )
        self.assertFalse(eligible)
        self.assertTrue(any("duplicate" in reason.lower() for reason in reasons))

    def test_auto_mode_resolves_eligible_candidate_to_unpublished_course(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_learning.course_selection_mode", "auto"
        )
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(
                external_id="auto-new",
                name="Applied Cryptography Foundations",
            )
        )
        candidate.action_evaluate()
        self.assertEqual(candidate.state, "resolved")
        self.assertEqual(candidate.resolution_type, "new")
        self.assertEqual(candidate.decision_origin, "automatic")
        self.assertEqual(candidate.decision_policy_version, "course-selection-v1")
        self.assertFalse(candidate.reviewed_by_id)
        self.assertTrue(candidate.decision_snapshot)
        self.assertFalse(candidate.resolved_channel_id.website_published)

    def test_auto_mode_never_auto_links_semantic_duplicate(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_learning.course_selection_mode", "auto"
        )
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(external_id="auto-dup", name="Python Basics")
        )
        candidate.action_evaluate()
        self.assertEqual(candidate.state, "shortlisted")
        self.assertFalse(candidate.resolved_channel_id)

    def test_manual_existing_resolution_creates_no_new_course(self):
        before = self.env["slide.channel"].search_count([])
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(
                external_id="manual-existing", name="Existing Choice"
            )
        )
        candidate.action_evaluate()
        candidate.write({"matched_channel_id": self.channel.id})
        candidate.action_resolve_existing()
        self.assertEqual(candidate.state, "resolved")
        self.assertEqual(candidate.resolved_channel_id, self.channel)
        self.assertEqual(candidate.resolution_type, "existing")
        self.assertEqual(candidate.decision_origin, "manual")
        self.assertEqual(candidate.reviewed_by_id, self.env.user)
        self.assertEqual(self.env["slide.channel"].search_count([]), before)

    def test_manual_new_resolution_is_idempotent_and_unpublished(self):
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(
                external_id="idempotent-new", name="Unique Security Course"
            )
        )
        candidate.action_evaluate()
        candidate.action_resolve_new()
        channel = candidate.resolved_channel_id
        candidate.action_resolve_new()
        self.assertEqual(candidate.resolved_channel_id, channel)
        self.assertFalse(channel.website_published)

    def test_manager_can_resolve_new_candidate_without_superuser_bypass(self):
        Candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager)
        candidate = Candidate.create(
            self._candidate_values(
                external_id="manager-manual-resolution",
                name="Manager Manual Resolution",
            )
        )
        candidate.action_evaluate()
        channel = candidate.action_resolve_new()
        self.assertEqual(candidate.requested_by_id, self.manager)
        self.assertEqual(candidate.state, "resolved")
        self.assertEqual(candidate.reviewed_by_id, self.manager)
        self.assertEqual(candidate.resolved_channel_id, channel)
        self.assertFalse(channel.website_published)

    def test_manager_auto_approve_needs_no_superuser_bypass(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_learning.course_selection_mode", "auto"
        )
        Candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager)
        candidate = Candidate.create(
            self._candidate_values(
                external_id="manager-auto-resolution",
                name="Manager Automatic Resolution",
            )
        )
        candidate.action_evaluate()
        self.assertEqual(candidate.requested_by_id, self.manager)
        self.assertEqual(candidate.state, "resolved")
        self.assertEqual(candidate.decision_origin, "automatic")
        self.assertFalse(candidate.reviewed_by_id)
        self.assertFalse(candidate.resolved_channel_id.website_published)

    def test_resolution_failure_does_not_leave_partial_course(self):
        from unittest.mock import patch

        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(external_id="failure", name="Failure Course")
        )
        candidate.action_evaluate()
        before = self.env["slide.channel"].search_count([])
        ChannelModel = type(self.env["slide.channel"])
        with patch.object(
            ChannelModel, "create", side_effect=RuntimeError("secret detail")
        ):
            candidate.action_resolve_new()
        candidate.invalidate_recordset()
        self.assertNotEqual(candidate.state, "resolved")
        self.assertFalse(candidate.resolved_channel_id)
        self.assertEqual(self.env["slide.channel"].search_count([]), before)
        self.assertIn("RuntimeError: operation failed", candidate.last_error)
        self.assertNotIn("secret detail", candidate.last_error)

    def test_course_candidate_action_and_views_are_loaded(self):
        action = self.env.ref("facodi_learning.action_facodi_course_candidates")
        self.assertEqual(action.res_model, "facodi.learning.course.candidate")
        self.assertEqual(action.view_mode, "list,form")
        self.env.ref("facodi_learning.menu_facodi_learning_course_candidates")

    def test_new_candidate_identity_is_editable_only_before_first_save(self):
        view = self.env.ref("facodi_learning.view_facodi_course_candidate_form")
        arch = view.arch_db
        self.assertIn('<field name="id" invisible="1"/>', arch)
        self.assertIn('<field name="provider" readonly="id"/>', arch)
        self.assertIn('<field name="external_id" readonly="id"/>', arch)

    def test_terminal_decision_snapshot_does_not_change_with_later_settings(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("facodi_learning.course_selection_mode", "auto")
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(
                external_id="snapshot", name="Unique Snapshot Course"
            )
        )
        candidate.action_evaluate()
        snapshot = dict(candidate.decision_snapshot)
        params.set_param("facodi_learning.auto_approve_min_relevance", "0.99")
        candidate.invalidate_recordset()
        self.assertEqual(candidate.decision_snapshot, snapshot)

    def test_terminal_candidate_metadata_cannot_be_rewritten(self):
        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(external_id="terminal", name="Terminal Course")
        )
        candidate.action_evaluate()
        candidate.action_resolve_new()
        with self.assertRaises(AccessError):
            candidate.write({"description": "Retcon"})

    def test_resolution_refuses_unavailable_row_lock(self):
        from unittest.mock import patch

        candidate = self.env["facodi.learning.course.candidate"].create(
            self._candidate_values(external_id="locked", name="Locked Course")
        )
        candidate.action_evaluate()
        CandidateModel = type(candidate)
        empty = self.env["facodi.learning.course.candidate"]
        with patch.object(CandidateModel, "try_lock_for_update", return_value=empty):
            with self.assertRaisesRegex(ValidationError, "being resolved"):
                candidate.action_resolve_new()
        self.assertFalse(candidate.resolved_channel_id)
