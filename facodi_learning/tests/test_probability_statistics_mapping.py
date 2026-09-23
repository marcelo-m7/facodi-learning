from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

from ..services.probability_statistics_mapping import (
    COURSE_NAMES,
    MODULES,
    REFERENCE_IDENTITY,
    apply_probability_statistics_mapping,
)


class TestProbabilityStatisticsMapping(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reference_external_id = "test-ualg-19411018-probability-statistics"
        cls.original_external_id = REFERENCE_IDENTITY["external_id"]
        REFERENCE_IDENTITY["external_id"] = cls.reference_external_id
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Probability Mapping Manager",
                "login": "probability-mapping-manager",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("website_slides.group_website_slides_manager").id,
                        ]
                    )
                ],
            }
        )
        cls.reference = cls.env["facodi.learning.curriculum.reference"].create(
            {
                "institution": "Universidade do Algarve",
                "programme_name": "Engenharia de Sistemas e Tecnologias Informáticas",
                "academic_year": "2026/27",
                "provider": "ualg",
                "external_id": cls.reference_external_id,
            }
        )
        cls.unit = cls.env["facodi.learning.curriculum.unit"].create(
            {
                "reference_id": cls.reference.id,
                "external_unit_code": "19411018",
                "name": "PROBABILIDADES E ESTATÍSTICA",
                "credits": 5.0,
                "curricular_year": 2,
                "classification": "mandatory",
            }
        )
        cls.reference.with_user(cls.manager).action_validate()
        cls.reference.with_user(cls.manager).action_publish()
        cls.courses = {
            name: cls.env["slide.channel"].create(
                {
                    "name": name,
                    "is_published": True,
                    "website_published": True,
                    "visibility": "public",
                }
            )
            for name in COURSE_NAMES
        }

    @classmethod
    def tearDownClass(cls):
        REFERENCE_IDENTITY["external_id"] = cls.original_external_id
        super().tearDownClass()

    def test_creates_reviewed_modules_course_items_and_partial_coverage(self):
        unit = apply_probability_statistics_mapping(self.env(user=self.manager.id))

        assignments = self.env["facodi.learning.curriculum.module.assignment"].search(
            [("curriculum_unit_id", "=", unit.id)], order="sequence, id"
        )
        self.assertEqual(assignments.mapped("module_id.name"), [item[1] for item in MODULES])
        self.assertEqual(assignments.mapped("sequence"), [item[0] for item in MODULES])
        for assignment, (_, _, course_names) in zip(assignments, MODULES):
            self.assertEqual(
                assignment.module_id.item_ids.mapped("channel_id"),
                self.env["slide.channel"].browse([self.courses[name].id for name in course_names]),
            )

        coverage = self.env["facodi.learning.curriculum.coverage"].search(
            [("curriculum_unit_id", "=", unit.id)], order="channel_id"
        )
        self.assertEqual(len(coverage), len(COURSE_NAMES))
        self.assertEqual(set(coverage.mapped("coverage_type")), {"partial"})
        self.assertEqual(set(coverage.mapped("state")), {"approved"})

    def test_is_idempotent_and_requires_all_published_courses(self):
        apply_probability_statistics_mapping(self.env(user=self.manager.id))
        apply_probability_statistics_mapping(self.env(user=self.manager.id))
        self.assertEqual(
            self.env["facodi.learning.curriculum.module.assignment"].search_count(
                [("curriculum_unit_id", "=", self.unit.id)]
            ),
            len(MODULES),
        )

    def test_requires_published_course_identities_before_creating_mapping(self):
        self.courses[COURSE_NAMES[0]].write({"website_published": False})

        with self.assertRaises(ValidationError):
            apply_probability_statistics_mapping(self.env(user=self.manager.id))

        self.assertFalse(
            self.env["facodi.learning.curriculum.module.assignment"].search_count(
                [("curriculum_unit_id", "=", self.unit.id)]
            )
        )

    def test_requires_review_of_rejected_coverage_before_creating_mapping(self):
        coverage = self.env["facodi.learning.curriculum.coverage"].create(
            {
                "channel_id": self.courses[COURSE_NAMES[0]].id,
                "curriculum_unit_id": self.unit.id,
                "coverage_type": "partial",
                "confidence": 1.0,
            }
        )
        coverage.with_user(self.manager).action_reject()

        with self.assertRaises(ValidationError):
            apply_probability_statistics_mapping(self.env(user=self.manager.id))

        self.assertFalse(
            self.env["facodi.learning.curriculum.module.assignment"].search_count(
                [("curriculum_unit_id", "=", self.unit.id)]
            )
        )