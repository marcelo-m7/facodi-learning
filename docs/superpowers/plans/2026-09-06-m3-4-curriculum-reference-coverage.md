# M3.4 Curriculum Reference & Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic, auditable external-curriculum reference and FACODI course-coverage layer that can represent official study plans such as UAlg LESTI without turning them into Odoo courses, learner pathways, credit decisions, or progression rules.

**Architecture:** Keep `slide.channel` as the only canonical FACODI course. Store external programme versions and their curricular units in dedicated reference models, then connect canonical courses to units through a reviewed `facodi.learning.curriculum.coverage` audit model. Provide deterministic, read-only gap summaries from approved coverage only; do not infer official prerequisites, ECTS recognition, learner progress, or academic enrolment.

**Tech Stack:** Odoo 19 Community, Python ORM/services, backend XML views, PostgreSQL 16, Odoo `TransactionCase`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-learning-course-selection-mapping-design.md`

## Global Constraints

- Canonical courses remain standard `slide.channel`; curriculum references never become canonical courses.
- Curriculum references are external benchmarks only; they do not own enrolment, learner progress, semester progression, transcripts, or official credit recognition.
- No automatic ECTS recognition or academic-equivalence decision is produced by M3.4.
- No prerequisite is inferred from curricular year, semester, sequence, ECTS, title similarity, or coverage relation.
- Public/Portal users have no ACL on curriculum references, units, coverage rows, confidence, provenance, or gap-analysis internals.
- Officers may read curriculum references/units and inspect approved coverage; Officers may create/edit proposed coverage only for courses they own.
- Only eLearning Managers may create/edit curriculum references/units and terminally approve/reject coverage.
- Coverage relation types are `covers`, `partial`, `supports`, and `equivalent`; all remain manual-review-only in M3.4.
- Coverage confidence is normalized to `0..1` and is evidence only.
- Reviewed coverage and generated evidence are immutable audit history.
- The same `(channel_id, curriculum_unit_id, coverage_type)` relation is unique.
- M3.4 adds no external HTTP/provider integration, AI, embeddings, vector storage, Celery, Redis, or custom worker framework.
- The core remains fully usable when no curriculum reference is configured.
- UAlg LESTI is a validation/example case, not production seed data and not an asserted FACODI/UAlg academic-equivalence agreement.

---

### Task 1: External curriculum reference and unit models

**Files:**
- Create: `facodi_learning/models/curriculum_reference.py`
- Modify: `facodi_learning/models/__init__.py`
- Modify: `facodi_learning/security/ir.model.access.csv`
- Modify: `facodi_learning/security/facodi_learning_security.xml`
- Create: `facodi_learning/tests/test_curriculum_reference.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Produces model `facodi.learning.curriculum.reference`.
- Produces model `facodi.learning.curriculum.unit`.
- `facodi.learning.curriculum.reference` fields: `name`, `institution`, `programme_name`, `external_programme_code`, `academic_year`, `source_url`, `provider`, `external_id`, `metadata`, `imported_at`, `validated_at`, `unit_ids`.
- `facodi.learning.curriculum.unit` fields: `reference_id`, `external_unit_code`, `name`, `credits`, `curricular_year`, `period`, `classification`, `option_group`, `sequence`, `metadata`.
- Stable reference identity: unique `(provider, external_id)`.
- Stable unit identity inside one programme version: unique `(reference_id, external_unit_code)`.

- [ ] **Step 1: Write failing model/security tests**

Add tests covering the exact contracts:

```python
def test_curriculum_reference_identity_is_unique(self): ...
def test_curriculum_unit_code_is_unique_within_reference(self): ...
def test_same_unit_code_can_exist_in_different_reference_versions(self): ...
def test_reference_preserves_academic_year_and_source_facts(self): ...
def test_unit_preserves_year_period_credits_and_option_group(self): ...
def test_officer_can_read_reference_and_unit(self): ...
def test_officer_cannot_create_or_edit_reference_or_unit(self): ...
def test_public_and_portal_cannot_read_curriculum_reference_or_unit(self): ...
```

Use a LESTI-shaped fixture only as test data, for example:

```python
reference_vals = {
    "institution": "Universidade do Algarve",
    "programme_name": "Engenharia de Sistemas e Tecnologias Informáticas",
    "external_programme_code": "1941",
    "academic_year": "2026/27",
    "source_url": "https://www.ualg.pt/curso/1941/plano",
    "provider": "manual",
    "external_id": "ualg-1941-2026-27",
}
unit_vals = {
    "external_unit_code": "19411017",
    "name": "Base de Dados II",
    "credits": 5.0,
    "curricular_year": 2,
    "period": "semester_2",
}
```

The tests must not assert any prerequisite or academic-equivalence meaning from those facts.

- [ ] **Step 2: Run full addon CI equivalent and verify RED**

Run `--test-tags /facodi_learning` against Odoo 19 Community/PostgreSQL 16. Expected failure is missing curriculum models/XML IDs only; existing M3.1-M3.3 tests must still load.

- [ ] **Step 3: Implement `facodi.learning.curriculum.reference`**

Use a focused model:

```python
class FacodiLearningCurriculumReference(models.Model):
    _name = "facodi.learning.curriculum.reference"
    _description = "FACODI Curriculum Reference"
    _order = "institution, programme_name, academic_year desc, id"

    name = fields.Char(compute="_compute_name", store=True)
    institution = fields.Char(required=True, index=True)
    programme_name = fields.Char(required=True, index=True)
    external_programme_code = fields.Char(index=True)
    academic_year = fields.Char(required=True, index=True)
    source_url = fields.Char()
    provider = fields.Char(required=True, default="manual", index=True)
    external_id = fields.Char(required=True, index=True)
    metadata = fields.Json()
    imported_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    validated_at = fields.Datetime()
    unit_ids = fields.One2many(
        "facodi.learning.curriculum.unit", "reference_id", string="Curricular Units"
    )

    _identity_unique = models.Constraint(
        "unique(provider, external_id)",
        "This curriculum reference already exists.",
    )
```

Normalize `provider` and `external_id` with `.strip()` on create/write and reject empty stable identity. `name` must be deterministic, e.g. `"Universidade do Algarve — Engenharia de Sistemas e Tecnologias Informáticas (2026/27)"`.

- [ ] **Step 4: Implement `facodi.learning.curriculum.unit`**

Use fields:

```python
reference_id = fields.Many2one(
    "facodi.learning.curriculum.reference",
    required=True,
    ondelete="cascade",
    index=True,
)
external_unit_code = fields.Char(required=True, index=True)
name = fields.Char(required=True, index=True)
credits = fields.Float(digits=(8, 2))
curricular_year = fields.Integer(index=True)
period = fields.Selection(
    [
        ("semester_1", "Semester 1"),
        ("semester_2", "Semester 2"),
        ("annual", "Annual"),
        ("other", "Other / Source-defined"),
    ],
    default="other",
    index=True,
)
classification = fields.Selection(
    [("mandatory", "Mandatory"), ("optional", "Optional"), ("unspecified", "Unspecified")],
    default="unspecified",
    required=True,
    index=True,
)
option_group = fields.Char()
sequence = fields.Integer(default=10, index=True)
metadata = fields.Json()
```

Add `credits >= 0` and `curricular_year >= 0` constraints. Do not derive prerequisite, sequence, or equivalence semantics from these values.

- [ ] **Step 5: Add ACLs/record rules**

Implement:

- Public/Portal: no ACL rows.
- Officer: read-only ACL for references and units, global read rule.
- Manager: full ACL/rule for references and units.

Do not add a FACODI-specific security group.

- [ ] **Step 6: Run focused/full tests, verify GREEN, commit**

Commit:

```text
feat: add external curriculum reference models
```

---

### Task 2: Auditable course-to-curriculum coverage lifecycle

**Files:**
- Create: `facodi_learning/models/curriculum_coverage.py`
- Modify: `facodi_learning/models/__init__.py`
- Modify: `facodi_learning/security/ir.model.access.csv`
- Modify: `facodi_learning/security/facodi_learning_security.xml`
- Create: `facodi_learning/tests/test_curriculum_coverage.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Produces model `facodi.learning.curriculum.coverage`.
- Fields: `channel_id`, `curriculum_unit_id`, `coverage_type`, `confidence`, `origin`, `state`, `evidence`, `evaluation_version`, `reviewed_by_id`, `reviewed_at`.
- Produces `action_approve()`, `action_reject()`, private `_review(state)`, and private server boundary `_create_generated(vals)`.
- Coverage approval changes only the audit row state; it must not mutate the course, curricular unit, ECTS, enrolment, publication, prerequisites, or learner data.

- [ ] **Step 1: Write failing lifecycle tests**

Cover:

```python
def test_curriculum_coverage_unique_course_unit_type(self): ...
def test_curriculum_coverage_rejects_confidence_outside_zero_one(self): ...
def test_manual_proposal_starts_proposed(self): ...
def test_direct_terminal_state_is_rejected_on_create(self): ...
def test_direct_generated_provenance_is_rejected_on_create(self): ...
def test_officer_can_propose_coverage_for_owned_course(self): ...
def test_officer_cannot_propose_coverage_for_another_course(self): ...
def test_officer_cannot_review_coverage(self): ...
def test_manager_can_approve_coverage(self): ...
def test_reviewed_coverage_is_immutable(self): ...
def test_generated_coverage_evidence_is_immutable(self): ...
def test_public_and_portal_cannot_read_curriculum_coverage(self): ...
def test_coverage_review_does_not_write_course_or_curriculum_unit(self): ...
```

- [ ] **Step 2: Run and verify RED**

Expected failures: missing coverage model/security only.

- [ ] **Step 3: Implement the audit model**

Use:

```python
class FacodiLearningCurriculumCoverage(models.Model):
    _name = "facodi.learning.curriculum.coverage"
    _description = "FACODI Curriculum Coverage"
    _order = "create_date desc, id desc"
```

Coverage types:

```python
[
    ("covers", "Covers"),
    ("partial", "Partial"),
    ("supports", "Supports"),
    ("equivalent", "Equivalent"),
]
```

Identity constraint:

```python
_coverage_unique = models.Constraint(
    "unique(channel_id, curriculum_unit_id, coverage_type)",
    "This curriculum coverage relation already exists.",
)
```

`channel_id` and `curriculum_unit_id` use `ondelete="restrict"` because reviewed audit history must not disappear silently when canonical/reference records are deleted. Confidence must remain inside `0..1`.

- [ ] **Step 4: Implement provenance and review guards**

Ordinary `create()` accepts manual `state='proposed'` only and clears reviewer fields. `_create_generated(vals)` is private/server-owned and forces `origin='analysis'`; ordinary RPC/ORM callers cannot forge `origin='analysis'` or `evaluation_version`.

`write()` rules:

- identity, lifecycle, origin, evaluation version, reviewer fields are protected;
- any generated proposal (`origin='analysis'`) is immutable through ordinary writes;
- any reviewed row is immutable through ordinary writes;
- manual proposed rows may edit `confidence` and `evidence` only.

`unlink()` may delete only manual proposed rows.

`_review(state)` must:

```python
self._check_manager()
self.check_access("write")
records = self.try_lock_for_update()
records.invalidate_recordset()
```

Require every row still `proposed`, then write `approved`/`rejected`, `reviewed_by_id`, `reviewed_at` through a controlled `super(...).write()` path. M3.4 has no Auto Approve.

- [ ] **Step 5: Add ACLs/record rules**

- Officer ACL: read/write/create, no unlink.
- Officer global read rule.
- Officer create/write rule: `channel_id.user_id == user.id`.
- Manager full ACL/global rule.
- Public/Portal: no ACL.

Python lifecycle methods remain the terminal-review authority even for Managers.

- [ ] **Step 6: Run tests, verify GREEN, commit**

Commit:

```text
feat: add reviewed curriculum coverage lifecycle
```

---

### Task 3: Deterministic curriculum gap summary

**Files:**
- Create: `facodi_learning/services/curriculum_coverage.py`
- Modify: `facodi_learning/services/__init__.py`
- Modify: `facodi_learning/models/curriculum_reference.py`
- Create: `facodi_learning/tests/test_curriculum_gap_analysis.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Produces `build_curriculum_unit_coverage(unit)` returning a plain deterministic dictionary.
- Produces `build_curriculum_reference_coverage(reference)` returning a deterministic programme-version summary.
- Produces `unit._facodi_coverage_summary()` and `reference._facodi_coverage_summary()`.
- Approved coverage only influences summaries; proposed/rejected rows are ignored.

- [ ] **Step 1: Write failing deterministic summary tests**

Cover:

```python
def test_unit_without_approved_coverage_is_gap(self): ...
def test_proposed_and_rejected_coverage_do_not_close_gap(self): ...
def test_partial_or_supports_only_is_partial(self): ...
def test_covers_marks_unit_covered(self): ...
def test_equivalent_marks_unit_covered_without_credit_claim(self): ...
def test_multiple_courses_are_returned_in_stable_order(self): ...
def test_reference_summary_counts_gap_partial_and_covered_units(self): ...
def test_summary_is_deterministic(self): ...
def test_summary_contains_no_learner_membership_or_progress(self): ...
```

- [ ] **Step 2: Run and verify RED**

Expected failures: missing service/model methods only.

- [ ] **Step 3: Implement unit summary**

Return schema:

```python
{
    "schema_version": "curriculum-coverage-v1",
    "unit_id": unit.id,
    "reference_id": unit.reference_id.id,
    "status": "gap" | "partial" | "covered",
    "approved_relations": [
        {
            "channel_id": relation.channel_id.id,
            "coverage_type": relation.coverage_type,
            "confidence": relation.confidence,
            "origin": relation.origin,
        },
    ],
}
```

Classification:

```text
no approved relation                         -> gap
approved covers/equivalent exists            -> covered
otherwise approved partial/supports exists   -> partial
```

Order relations by `(channel_id, coverage_type, id)`. Use ordinary ORM access only; no `sudo()`, no network, no learner records.

- [ ] **Step 4: Implement reference summary**

Return:

```python
{
    "schema_version": "curriculum-coverage-v1",
    "reference_id": reference.id,
    "unit_count": N,
    "gap_count": G,
    "partial_count": P,
    "covered_count": C,
    "units": [...unit summaries in sequence,id order...],
}
```

This is the M3.4 boundary later candidate-selection work can consume. Do not mutate `facodi.learning.course.candidate.coverage_score` in M3.4.

- [ ] **Step 5: Run tests, verify GREEN, commit**

Commit:

```text
feat: add deterministic curriculum gap analysis
```

---

### Task 4: Odoo-native backend curriculum workspace

**Files:**
- Create: `facodi_learning/views/curriculum_views.xml`
- Modify: `facodi_learning/views/course_mapping_views.xml` only if menu sequencing needs adjustment; do not merge curriculum records into the course-mapping action.
- Modify: `facodi_learning/models/slide_channel.py`
- Modify: `facodi_learning/__manifest__.py`
- Create: `facodi_learning/tests/test_curriculum_ui.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Adds `eLearning → FACODI Learning → Curriculum Coverage`.
- Child menu/actions: `References`, `Curricular Units`, `Coverage`.
- Adds `slide.channel.action_facodi_view_curriculum_coverage()` and a stat button on the standard course form.
- No new public website route or learner widget in M3.4.

- [ ] **Step 1: Write failing UI/action tests**

Cover:

```python
def test_curriculum_backend_actions_and_views_are_loaded(self): ...
def test_curriculum_menu_hierarchy_is_distinct_from_course_mapping(self): ...
def test_reference_form_exposes_units_without_parallel_course_editor(self): ...
def test_coverage_form_has_manager_review_buttons(self): ...
def test_course_can_open_curriculum_coverage_workspace(self): ...
def test_no_public_curriculum_qweb_route_is_added(self): ...
```

- [ ] **Step 2: Run and verify RED**

Expected: missing XML IDs/action method.

- [ ] **Step 3: Create reference/unit backend views**

Reference list/search/form must expose institution, programme, code, academic year, provider/external identity, source URL, timestamps and units. Reference/unit create/edit UI is Manager-only through ACLs and menu/action groups.

Unit list/search/form must expose reference, code, name, credits, curricular year, period, classification, option group and sequence. Include group-by filters for reference/year/period/classification.

- [ ] **Step 4: Create coverage backend views**

Coverage search/list/form must expose course, curricular unit/reference, type, confidence, origin and state. Default action context filters to `state='proposed'`. Manager-only Approve/Reject buttons appear only while proposed.

The form must include explanatory copy that coverage is FACODI evidence only and does not grant university credit, enrolment, transcript status, or official prerequisite meaning.

- [ ] **Step 5: Add standard course stat action**

Implement on `slide.channel`:

```python
def action_facodi_view_curriculum_coverage(self):
    self.ensure_one()
    self.check_access("read")
    action = self.env["ir.actions.actions"]._for_xml_id(
        "facodi_learning.action_facodi_curriculum_coverage"
    )
    action["domain"] = [("channel_id", "=", self.id)]
    action["context"] = {"default_channel_id": self.id}
    return action
```

Add only a stat button to the inherited standard course form. Do not create a second course editor.

- [ ] **Step 6: Load XML in manifest, run tests, verify GREEN, commit**

Commit:

```text
feat: add curriculum coverage workspace
```

---

### Task 5: LESTI validation case and architectural documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/validation.md`
- Create: `facodi_learning/tests/test_curriculum_lesti_case.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Documents UAlg LESTI as an external reference example only.
- Validates that a 2026/27 LESTI-shaped reference can represent year/semester/ECTS/option-group facts and course coverage without inferring official prerequisite or credit decisions.

- [ ] **Step 1: Add the LESTI-shaped regression test**

Create a reference with:

```text
institution: Universidade do Algarve
programme: Engenharia de Sistemas e Tecnologias Informáticas
programme code: 1941
academic year: 2026/27
source: https://www.ualg.pt/curso/1941/plano
```

Create representative units such as `Programação`, `Base de Dados II`, and a final-stage `Estágio`/`Projeto` option-group pair using source-shaped codes/ECTS. Assert:

- both option units can share one `option_group` label without becoming prerequisite/equivalence relations;
- year/semester/sequence does not write `slide.channel.prerequisite_channel_ids`;
- one FACODI course can cover multiple units and one unit can have multiple approved courses;
- coverage summaries distinguish gap/partial/covered from approved evidence only;
- no model field/action claims official ECTS recognition.

- [ ] **Step 2: Run and verify GREEN**

This is a regression/acceptance test over already implemented M3.4 behavior and must pass without new special-case code for UAlg.

- [ ] **Step 3: Update README and architecture**

Document:

```text
External curriculum reference -> versioned units -> reviewed FACODI coverage -> deterministic gap summary
```

State explicitly:

- external curriculum is not a FACODI pathway;
- `equivalent` coverage is an internal evidence label, not an official university equivalence/credit award;
- no prerequisites are inferred from year/semester/order;
- no learner/public route is introduced;
- M3.5 provider addons may later populate references/candidates, but M3.4 itself has no external fetcher.

- [ ] **Step 4: Update validation evidence and commit**

Record exact RED/GREEN CI SHAs/runs from Tasks 1-4 and the LESTI acceptance run. Do not claim a source fact beyond what the approved design/research supports.

Commit:

```text
docs: validate M3.4 curriculum coverage design
```

---

### Task 6: Release version, clean-install/upgrade gate, review, and PR

**Files:**
- Modify: `facodi_learning/__manifest__.py`
- Modify: `docs/validation.md`

**Interfaces:**
- Bumps addon version from `19.0.1.4.1` to `19.0.1.5.0` because M3.4 adds new persistent models, ACLs, views, and additive schema.
- No data migration rewrites historical M3.1-M3.3 records.

- [ ] **Step 1: Bump manifest version**

Set:

```python
"version": "19.0.1.5.0",
```

- [ ] **Step 2: Run the release-head clean-install gate**

GitHub Actions must install `facodi_learning` from a clean PostgreSQL 16 database with all `/facodi_learning` tests. Required result: zero failures and zero errors.

- [ ] **Step 3: Run the same-database upgrade/regression gate**

GitHub Actions must run `-u facodi_learning` on the same database/filestore and rerun the addon regression suite. Required result: zero failures and zero errors.

- [ ] **Step 4: Verify additive-upgrade invariants**

Confirm through tests/ORM that existing course candidates, analysis history, content mappings, M3.3 course mappings, standard courses/content and native prerequisites remain intact. M3.4 adds tables/metadata only; it must not fabricate historical curriculum coverage.

- [ ] **Step 5: Request code review and fix all Critical/Important findings**

Review exact base/head SHAs. Re-run both CI gates after any functional or documentation change that moves the release head.

- [ ] **Step 6: Open a PR without merging**

PR summary must state:

- three new generic curriculum models;
- reviewed manual-only coverage lifecycle;
- deterministic approved-only gap analysis;
- backend-only Odoo-native workspace;
- UAlg LESTI as validation example, not bundled production data;
- no learner pathway, credit recognition, official equivalence, prerequisite inference, AI, or external provider integration;
- clean-install and upgrade evidence on the exact release head.

Do not merge without explicit user authorization.
