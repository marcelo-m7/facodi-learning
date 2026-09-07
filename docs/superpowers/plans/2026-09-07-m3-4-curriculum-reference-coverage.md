# M3.4 Curriculum Reference & Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an auditable external-curriculum reference and coverage layer that can benchmark FACODI `slide.channel` courses against official study-plan units and feed deterministic curriculum-gap evidence into course-candidate evaluation.

**Architecture:** Odoo `slide.channel` remains the canonical FACODI course. External curricula live in three separate audit/reference models (`curriculum.reference`, `curriculum.unit`, `curriculum.coverage`) and never own enrolment, learner progress, credits, publication or prerequisites. Coverage-driven candidate scoring is deterministic and conservative: only Manager-enabled references participate; approved coverage lowers the uncovered gap; without an enabled curriculum the M3.1 baseline remains `coverage_score=1.0`.

**Tech Stack:** Odoo 19 Community, `website_slides`, PostgreSQL 16, ORM constraints/record rules, QWeb/backend views, Python deterministic services, GitHub Actions clean-install + same-database upgrade tests.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-learning-course-selection-mapping-design.md` sections 16–22.

## Global Constraints

- `slide.channel` remains the only FACODI course model.
- Curriculum records are external benchmark facts, not learner pathways or official UAlg execution state.
- No automatic academic credit/ECTS recognition, transcripts, semester progression or university enrolment.
- Do not infer official prerequisites from curricular year/semester ordering.
- Public/Portal cannot read curriculum audit models.
- Reuse eLearning Officer/Manager roles; no FACODI-specific curator group.
- Reviewed coverage evidence is immutable history.
- No external HTTP/provider synchronization in M3.4; LESTI/UAlg is a test/validation fixture only.
- The addon must remain fully usable when no curriculum reference is enabled.

---

### Task 1: External curriculum reference and unit models

**Files:**
- Create: `facodi_learning/models/curriculum_reference.py`
- Modify: `facodi_learning/models/__init__.py`
- Modify: `facodi_learning/security/ir.model.access.csv`
- Modify: `facodi_learning/security/facodi_learning_security.xml`
- Test: `facodi_learning/tests/test_curriculum_reference.py`

**Interfaces:**
- Produces model `facodi.learning.curriculum.reference`.
- Produces model `facodi.learning.curriculum.unit`.
- `reference.selection_enabled` identifies curricula used by M3.1 coverage-gap scoring.
- Unit identity is unique within one reference by `external_unit_code` when supplied; every unit still has deterministic source order via `sequence`.

- [ ] **Step 1: Write failing model/security tests**

```python
class TestCurriculumReference(TransactionCase):
    def test_manager_can_create_reference_and_units(self):
        reference = self.env["facodi.learning.curriculum.reference"].with_user(self.manager).create({
            "institution": "Universidade do Algarve",
            "programme_name": "Engenharia de Sistemas e Tecnologias Informáticas",
            "external_programme_code": "1941",
            "academic_year": "2026/27",
            "source_url": "https://www.ualg.pt/curso/1941/plano",
            "provider": "ualg-public-plan",
            "selection_enabled": True,
        })
        unit = self.env["facodi.learning.curriculum.unit"].with_user(self.manager).create({
            "reference_id": reference.id,
            "external_unit_code": "19411017",
            "name": "Base de Dados II",
            "credits": 5.0,
            "curricular_year": 2,
            "period": "semester_2",
            "sequence": 20,
        })
        self.assertEqual(unit.reference_id, reference)
        self.assertEqual(unit.credits, 5.0)

    def test_public_and_portal_cannot_read_curriculum_models(self):
        with self.assertRaises(AccessError):
            self.env["facodi.learning.curriculum.reference"].with_user(self.public_user).search([])
        with self.assertRaises(AccessError):
            self.env["facodi.learning.curriculum.unit"].with_user(self.portal_user).search([])

    def test_officer_can_read_but_not_manage_reference_facts(self):
        self.reference.with_user(self.officer).read(["programme_name"])
        with self.assertRaises(AccessError):
            self.reference.with_user(self.officer).write({"selection_enabled": True})
```

- [ ] **Step 2: Run CI and verify RED**

Expected: only the new tests fail because the two models do not exist.

- [ ] **Step 3: Implement reference/unit schema**

Reference fields:

```python
institution = fields.Char(required=True, index=True)
programme_name = fields.Char(required=True, index=True)
external_programme_code = fields.Char(index=True)
academic_year = fields.Char(required=True, index=True)
source_url = fields.Char(required=True)
provider = fields.Char(required=True, default="manual", index=True)
metadata = fields.Json()
selection_enabled = fields.Boolean(default=False, index=True)
imported_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
validated_at = fields.Datetime()
unit_ids = fields.One2many("facodi.learning.curriculum.unit", "reference_id")
```

Reference uniqueness:

```python
models.Constraint(
    "unique(provider, external_programme_code, academic_year)",
    "This curriculum version is already registered for this provider.",
)
```

Unit fields:

```python
reference_id = fields.Many2one("facodi.learning.curriculum.reference", required=True, ondelete="cascade", index=True)
external_unit_code = fields.Char(index=True)
name = fields.Char(required=True, index=True)
credits = fields.Float()
curricular_year = fields.Integer(index=True)
period = fields.Selection([
    ("semester_1", "Semester 1"),
    ("semester_2", "Semester 2"),
    ("annual", "Annual"),
    ("other", "Other"),
])
classification = fields.Selection([
    ("mandatory", "Mandatory"),
    ("optional", "Optional"),
    ("unknown", "Not specified"),
], default="unknown")
option_group = fields.Char()
sequence = fields.Integer(default=10, index=True)
metadata = fields.Json()
```

Reject negative credits/year and blank institution/programme/unit names. Do not invent prerequisites from order fields.

- [ ] **Step 4: Add ACLs/rules**

Officer: read-only reference/unit. Manager: full CRUD. Public/Portal: no ACL.

- [ ] **Step 5: Run clean-install + upgrade tests and commit GREEN**

Commit message: `feat: add external curriculum reference models`.

---

### Task 2: Auditable FACODI course-to-curriculum coverage

**Files:**
- Create: `facodi_learning/models/curriculum_coverage.py`
- Modify: `facodi_learning/models/__init__.py`
- Modify: `facodi_learning/security/ir.model.access.csv`
- Modify: `facodi_learning/security/facodi_learning_security.xml`
- Test: `facodi_learning/tests/test_curriculum_coverage.py`

**Interfaces:**
- Produces model `facodi.learning.curriculum.coverage`.
- Directed identity: `(channel_id, curriculum_unit_id, coverage_type)`.
- Coverage types: `covers`, `partial`, `supports`, `equivalent`.
- Only `approved` coverage influences curriculum-gap scoring.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_manual_coverage_is_proposed_then_manager_reviews(self):
    coverage = self.Coverage.with_user(self.officer).create({
        "channel_id": self.owned_channel.id,
        "curriculum_unit_id": self.database_ii.id,
        "coverage_type": "partial",
        "confidence": 0.7,
        "evidence": {"reason": "Covers SQL normalization and transactions"},
    })
    self.assertEqual(coverage.state, "proposed")
    coverage.with_user(self.manager).action_approve()
    self.assertEqual(coverage.state, "approved")
    self.assertEqual(coverage.reviewed_by_id, self.manager)


def test_reviewed_coverage_is_immutable(self):
    self.coverage.with_user(self.manager).action_approve()
    with self.assertRaises(AccessError):
        self.coverage.with_user(self.manager).write({"confidence": 0.9})


def test_duplicate_and_invalid_coverage_rejected(self):
    with self.assertRaises(ValidationError):
        self.Coverage.create({"channel_id": self.channel.id, "curriculum_unit_id": self.unit.id, "coverage_type": "covers", "confidence": 1.2})
```

- [ ] **Step 2: Run CI and verify RED**

- [ ] **Step 3: Implement schema/lifecycle**

```python
channel_id = fields.Many2one("slide.channel", required=True, ondelete="restrict", index=True)
curriculum_unit_id = fields.Many2one("facodi.learning.curriculum.unit", required=True, ondelete="restrict", index=True)
coverage_type = fields.Selection([
    ("covers", "Covers"),
    ("partial", "Partial"),
    ("supports", "Supports"),
    ("equivalent", "Equivalent"),
], required=True, default="covers", index=True)
confidence = fields.Float(digits=(5, 4))
origin = fields.Selection([("manual", "Manual"), ("analysis", "Analysis")], required=True, default="manual", index=True)
state = fields.Selection([("proposed", "Proposed"), ("approved", "Approved"), ("rejected", "Rejected")], required=True, default="proposed", index=True)
evidence = fields.Json()
reviewed_by_id = fields.Many2one("res.users", readonly=True)
reviewed_at = fields.Datetime(readonly=True)
policy_version = fields.Char(readonly=True)
decision_snapshot = fields.Json(readonly=True)
```

Use ORM pre-validation plus SQL unique constraint. Public `create()` only creates manual proposed evidence. Generated provenance, if used later, must use a private server-owned method. Manager-only terminal review uses `try_lock_for_update()`; reviewed/generated history is immutable.

- [ ] **Step 4: Add security**

Officer: read all; create/write manual proposed coverage only where `channel_id.user_id == user.id`; no unlink. Manager: full model ACL but lifecycle guards still protect reviewed evidence. Public/Portal: no ACL.

- [ ] **Step 5: Run clean-install + upgrade tests and commit GREEN**

Commit message: `feat: add reviewed curriculum coverage`.

---

### Task 3: Deterministic curriculum coverage/gap service with LESTI validation fixture

**Files:**
- Create: `facodi_learning/services/curriculum_coverage.py`
- Modify: `facodi_learning/services/__init__.py` if present/required
- Test: `facodi_learning/tests/test_curriculum_gap.py`

**Interfaces:**
- `coverage_strength_for_unit(unit) -> float` uses approved coverage only.
- `build_curriculum_selection_context(env) -> dict` returns enabled references and normalized units.
- `score_candidate_curriculum_gap(candidate_name, context) -> {score, evidence}`.

Coverage strength baseline:

```python
COVERAGE_STRENGTH = {
    "equivalent": 1.0,
    "covers": 1.0,
    "partial": 0.5,
    "supports": 0.25,
}
```

For a unit, use `max(confidence * type_strength)` across approved coverage rows. Proposed/rejected rows contribute zero.

Candidate gap score:

```python
match = course_title_similarity(candidate_name, unit.name)
gap = 1.0 - approved_coverage_strength
need = match * gap
score = max(need across enabled curriculum units)
```

If no reference is `selection_enabled`, return score `1.0` and baseline evidence indicating no active curriculum. This preserves M3.1 behavior exactly.

- [ ] **Step 1: Write RED tests using a LESTI fixture**

Create test-only reference:
- institution: `Universidade do Algarve`
- programme: `Engenharia de Sistemas e Tecnologias Informáticas`
- code: `1941`
- academic year: `2026/27`
- source: `https://www.ualg.pt/curso/1941/plano`

Create test units including:
- `19411017` — `Base de Dados II` — 5 ECTS;
- `19411016` — `Engenharia de Software` — 5 ECTS;
- `19411022` — `Inteligência Artificial` — 5 ECTS.

Tests:

```python
def test_uncovered_matching_unit_has_high_need(self):
    result = score_candidate_curriculum_gap("Base de Dados II", self.context)
    self.assertEqual(result["score"], 1.0)
    self.assertEqual(result["evidence"]["best_unit_code"], "19411017")


def test_approved_full_coverage_removes_gap_priority(self):
    self._approved_coverage(self.database_ii, "covers", confidence=1.0)
    result = score_candidate_curriculum_gap("Base de Dados II", build_curriculum_selection_context(self.env))
    self.assertEqual(result["score"], 0.0)


def test_proposed_coverage_does_not_reduce_gap(self):
    self._coverage(self.database_ii, state="proposed", coverage_type="covers", confidence=1.0)
    self.assertEqual(score_candidate_curriculum_gap("Base de Dados II", build_curriculum_selection_context(self.env))["score"], 1.0)
```

- [ ] **Step 2: Run RED**

- [ ] **Step 3: Implement deterministic service**

Evidence must include only safe audit identifiers/facts:

```python
{
    "mode": "curriculum-gap",
    "reference_ids": [...],
    "best_reference_id": id,
    "best_programme": "...",
    "best_academic_year": "2026/27",
    "best_unit_id": id,
    "best_unit_code": "19411017",
    "best_unit_name": "Base de Dados II",
    "title_similarity": 1.0,
    "approved_coverage_strength": 0.0,
    "uncovered_gap": 1.0,
}
```

Do not infer or expose prerequisites, credits recognition or learner data.

- [ ] **Step 4: Run clean-install + upgrade tests and commit GREEN**

Commit message: `feat: compute curriculum coverage gaps`.

---

### Task 4: Feed curriculum-gap evidence into M3.1 candidate evaluation

**Files:**
- Modify: `facodi_learning/services/course_selection.py`
- Modify: `facodi_learning/models/course_candidate.py`
- Modify: `facodi_learning/views/course_candidate_views.xml`
- Test: `facodi_learning/tests/test_course_selection.py`
- Test: `facodi_learning/tests/test_curriculum_candidate_selection.py`

**Interfaces:**
- `evaluate_course_candidate(candidate, existing_channels, accepted_languages, curriculum_context=None)`.
- Candidate gains readonly `coverage_evidence = fields.Json()`.
- Candidate decision snapshots include `coverage_evidence` so later curriculum changes do not rewrite historical rationale.

- [ ] **Step 1: Write RED integration tests**

```python
def test_candidate_uses_enabled_curriculum_gap(self):
    candidate = self._candidate("Base de Dados II")
    candidate.action_evaluate()
    self.assertEqual(candidate.coverage_score, 1.0)
    self.assertEqual(candidate.coverage_evidence["best_unit_code"], "19411017")


def test_existing_approved_coverage_lowers_candidate_coverage_score(self):
    self._approved_full_coverage(self.database_ii)
    candidate = self._candidate("Base de Dados II")
    candidate.action_evaluate()
    self.assertEqual(candidate.coverage_score, 0.0)


def test_no_enabled_curriculum_preserves_m31_baseline(self):
    self.reference.selection_enabled = False
    candidate = self._candidate("Anything")
    candidate.action_evaluate()
    self.assertEqual(candidate.coverage_score, 1.0)
    self.assertEqual(candidate.coverage_evidence["mode"], "baseline")
```

- [ ] **Step 2: Run RED**

- [ ] **Step 3: Update evaluator/model**

`action_evaluate()` builds curriculum context once per action, passes it into the pure evaluator, and persists `coverage_evidence`. Extend `_evaluation_fields` and `_decision_snapshot_for_policy()` accordingly. Terminal evidence remains immutable.

- [ ] **Step 4: Verify Auto Approve remains fail-closed**

Add a regression proving that an otherwise eligible candidate below `min_coverage` because its target curriculum unit is already fully covered does not Auto Approve.

- [ ] **Step 5: Run clean-install + upgrade tests and commit GREEN**

Commit message: `feat: use curriculum gaps in course selection`.

---

### Task 5: Backend curriculum workspace, docs, release gate and PR

**Files:**
- Create: `facodi_learning/views/curriculum_views.xml`
- Modify: `facodi_learning/__manifest__.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/validation.md`
- Test: `facodi_learning/tests/test_curriculum_views.py`

**Interfaces:**
- Menu:

```text
eLearning
└── FACODI Learning
    └── Curriculum Coverage
        ├── References
        ├── Units
        └── Coverage
```

- References/Units are editable by Managers; Officers have read-only access.
- Coverage list/form exposes proposed/approved/rejected state and Manager approve/reject actions.
- `selection_enabled` is visible as an explicit Manager editorial switch.

- [ ] **Step 1: Add RED XML-ID/menu/action smoke tests**

Require actions/views/menu IDs for references, units and coverage.

- [ ] **Step 2: Implement backend views/menu**

Use standard list/form/search views. Do not expose curriculum audit data on Public/Portal pages in M3.4.

- [ ] **Step 3: Bump addon version**

From `19.0.1.4.1` to `19.0.1.5.0` because M3.4 adds persistent schema/models.

- [ ] **Step 4: Update documentation and validation evidence**

Explicitly document that LESTI/UAlg values are test/validation examples and are not automatically installed, synchronized, asserted as partnership data or used for official credit/prerequisite claims.

- [ ] **Step 5: Run exact-head release gate**

Required:
- clean install of `facodi_learning` on Odoo 19/PostgreSQL 16;
- same-database `-u facodi_learning` regression run;
- all M3.1–M3.4 tests green;
- compare branch against fresh `main`;
- review patch for Public/Portal ACL leakage, `sudo()` expansion, curriculum-to-prerequisite coupling and learner-personal data.

- [ ] **Step 6: Open PR to `main`**

Open only after exact-head CI is GREEN. Do not merge without explicit user authorization.
