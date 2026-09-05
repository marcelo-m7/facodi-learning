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
