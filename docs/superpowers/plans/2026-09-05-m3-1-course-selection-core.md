# FACODI Learning M3.1 Course Selection Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an auditable, deterministic course-candidate selection pipeline with Manual, Assisted and fail-closed Auto Approve modes that resolves external candidates into canonical unpublished/existing Odoo `slide.channel` records.

**Architecture:** Add one domain model, `facodi.learning.course.candidate`, and one focused pure/deterministic selection service. Candidate evaluation produces independent signals and a recommendation; policy application may shortlist or resolve only through the candidate model’s guarded methods. Manual and automatic resolution converge on `_resolve()`, use row locking, never auto-publish, and never create a parallel course model.

**Tech Stack:** Odoo 19 Community, `website_slides`, Python/Odoo ORM, QWeb/XML backend views, `ir.config_parameter`, PostgreSQL 16, existing Docker-based GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-learning-course-selection-mapping-design.md`

## Global Constraints

- Odoo 19 Community `slide.channel` remains the canonical course model.
- Do not introduce `facodi.course`, learner-pathway, enrolment, progress, publication or credit-recognition models.
- New courses created by this slice MUST remain unpublished (`website_published=False`).
- Auto Approve MUST be fail-closed and MUST NOT imply Auto Publish or learner enrolment.
- Default selection mode MUST remain `manual`.
- Automatic decisions MUST store `decision_origin="automatic"`, a policy version and an immutable decision snapshot; they MUST NOT fake a human `reviewed_by_id`.
- Manual and automatic candidate resolution MUST use the same `_resolve()` domain path.
- Core MUST have no external provider SDK, AI, embedding or network dependency.
- Candidate identity MUST be unique on `(provider, external_id)`.
- Semantic/heuristic duplicate matching MUST never auto-link an existing course in M3.1; high duplicate risk routes to review.
- Public and Portal users MUST NOT read candidate/evaluation records.
- Officers may create/reevaluate their own manual candidates; only eLearning Managers or trusted automation may perform terminal resolution.
- Existing content analysis, content mappings and ingestion behavior MUST remain unchanged.
- Install/upgrade gates continue against Odoo 19 + PostgreSQL 16 with `--test-tags /facodi_learning`.

---

## File Structure

### New files

- `facodi_learning/models/course_candidate.py` — candidate lifecycle, guarded state transitions, evaluation orchestration and canonical resolution.
- `facodi_learning/services/course_selection.py` — deterministic title normalization/similarity, candidate scoring, policy parsing and Auto Approve eligibility.
- `facodi_learning/views/course_candidate_views.xml` — candidate search/list/form actions and Course Discovery menus.
- `facodi_learning/tests/test_course_selection.py` — candidate identity, evaluation, modes, resolution, concurrency/idempotency and unpublished-course regressions.

### Modified files

- `facodi_learning/models/__init__.py` — import the candidate model.
- `facodi_learning/services/__init__.py` — export selection helpers used by the model/tests.
- `facodi_learning/models/res_config_settings.py` — selection mode, thresholds, accepted languages and trusted-provider configuration.
- `facodi_learning/views/res_config_settings_views.xml` — Manager-facing Course Selection settings.
- `facodi_learning/views/analysis_views.xml` — move the existing technical analysis menu beneath `FACODI Learning > Content Analysis` without changing its actions.
- `facodi_learning/security/ir.model.access.csv` — Officer/Manager candidate ACLs.
- `facodi_learning/security/facodi_learning_security.xml` — Officer-own mutation and Manager-all candidate record rules.
- `facodi_learning/tests/__init__.py` — load course-selection tests.
- `facodi_learning/tests/test_security.py` — Public/Portal denial and Officer/Manager boundary regressions.
- `facodi_learning/__manifest__.py` — load the new views and bump the additive addon version from `19.0.1.1.0` to `19.0.1.2.0`.
- `README.md` — document Course Discovery and Manual/Assisted/Auto modes.
- `docs/architecture.md` — document M3.1 identity, evaluation, policy and resolution invariants.

---

### Task 1: Add the candidate model and immutable identity/lifecycle guards

**Files:**
- Create: `facodi_learning/models/course_candidate.py`
- Modify: `facodi_learning/models/__init__.py`
- Test: `facodi_learning/tests/test_course_selection.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Produces model: `facodi.learning.course.candidate`.
- Produces public actions used later: `action_evaluate()`, `action_shortlist()`, `action_reject()`, `action_resolve_new()`, `action_resolve_existing()`.
- Produces private transition primitive used later: `_resolve(resolution_type, channel=None, decision_origin="manual", policy_version=None, decision_snapshot=None)`.
- Does not yet implement evaluation or resolution internals beyond explicit `NotImplementedError`-free guarded state behavior required by the tests in this task.

- [ ] **Step 1: Register the new test module and write failing identity/lifecycle tests**

Add to `facodi_learning/tests/__init__.py`:

```python
from . import test_course_selection
```

Create `facodi_learning/tests/test_course_selection.py` with a `TransactionCase` fixture containing one Manager, one Officer and two standard channels. Start with these tests:

```python
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestCourseSelection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create({
            "name": "Course Selection Manager",
            "login": "course-selection-manager",
            "group_ids": [(6, 0, [
                cls.env.ref("website_slides.group_website_slides_manager").id,
            ])],
        })
        cls.officer = cls.env["res.users"].create({
            "name": "Course Selection Officer",
            "login": "course-selection-officer",
            "group_ids": [(6, 0, [
                cls.env.ref("website_slides.group_website_slides_officer").id,
            ])],
        })
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
        with self.assertRaises(Exception), self.env.cr.savepoint():
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
        candidate.write({"description": "Updated description", "metadata": {"v": 2}})
        self.assertEqual(candidate.description, "Updated description")
        self.assertEqual(candidate.metadata, {"v": 2})
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run using the repository’s Odoo 19/PostgreSQL 16 test harness equivalent:

```bash
odoo -d facodi_learning_test \
  --addons-path=/usr/lib/python3/dist-packages/odoo/addons,$PWD \
  --workers=0 --without-demo=True \
  -i facodi_learning \
  --test-tags /facodi_learning:TestCourseSelection \
  --stop-after-init
```

Expected: module/test import fails because `facodi.learning.course.candidate` does not exist.

- [ ] **Step 3: Implement the minimal candidate schema and guards**

Create `facodi_learning/models/course_candidate.py` with these fields and exact selections:

```python
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FacodiLearningCourseCandidate(models.Model):
    _name = "facodi.learning.course.candidate"
    _description = "FACODI Course Candidate"
    _order = "create_date desc, id desc"

    provider = fields.Char(required=True, default="manual", index=True)
    external_id = fields.Char(required=True, index=True)
    source_url = fields.Char()
    name = fields.Char(required=True)
    description = fields.Text()
    institution = fields.Char()
    language = fields.Char(index=True)
    level = fields.Char()
    duration_minutes = fields.Integer()
    license_name = fields.Char()
    metadata = fields.Json()

    requested_by_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, readonly=True
    )
    state = fields.Selection([
        ("discovered", "Discovered"),
        ("evaluated", "Evaluated"),
        ("shortlisted", "Shortlisted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("resolved", "Resolved"),
    ], required=True, default="discovered", readonly=True, index=True)

    relevance_score = fields.Float(digits=(5, 4), readonly=True)
    metadata_quality_score = fields.Float(digits=(5, 4), readonly=True)
    language_fit_score = fields.Float(digits=(5, 4), readonly=True)
    coverage_score = fields.Float(digits=(5, 4), readonly=True)
    duplication_risk = fields.Float(digits=(5, 4), readonly=True)
    recommendation = fields.Selection([
        ("ignore", "Ignore"),
        ("review", "Review"),
        ("shortlist", "Shortlist"),
        ("review_existing_match", "Review Existing Match"),
    ], readonly=True)
    evaluation_reasons = fields.Json(readonly=True)
    evaluation_policy_version = fields.Char(readonly=True)
    evaluated_at = fields.Datetime(readonly=True)

    matched_channel_id = fields.Many2one("slide.channel", ondelete="set null")
    resolved_channel_id = fields.Many2one("slide.channel", readonly=True, ondelete="restrict")
    resolution_type = fields.Selection([
        ("existing", "Existing Course"),
        ("new", "New Draft Course"),
    ], readonly=True)
    decision_origin = fields.Selection([
        ("manual", "Manual"),
        ("automatic", "Automatic"),
    ], readonly=True)
    decision_policy_version = fields.Char(readonly=True)
    decision_at = fields.Datetime(readonly=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    decision_snapshot = fields.Json(readonly=True)
    last_error = fields.Text(readonly=True)

    _identity_unique = models.Constraint(
        "unique(provider, external_id)",
        "This external course candidate is already registered.",
    )
```

Add constraints requiring non-blank `provider`, `external_id`, `name`, non-negative `duration_minutes`, and all persisted scores to be in `0..1`.

Override `create()` so clients may only supply source/normalized metadata fields plus `requested_by_id=self.env.uid`; reject forged state/evaluation/decision fields and always initialize the lifecycle/evidence fields explicitly.

Override `write()` so:

- `provider`, `external_id`, `requested_by_id`, all evaluation evidence and all terminal decision fields cannot be directly written;
- `matched_channel_id` can be manually changed only by an eLearning Manager while the candidate is unresolved;
- normalized metadata may be refreshed only while state is `discovered`, `evaluated` or `shortlisted`;
- terminal candidates permit no editorial metadata rewrite.

Override `unlink()` so only Managers may remove unresolved candidates; `rejected`, `approved` or `resolved` records are audit history and cannot be deleted.

Add placeholder-free action method bodies that raise a clear `ValidationError("Evaluate the candidate before this action.")` where later behavior is not implemented yet; do not use `pass` or `NotImplementedError`.

Register the model in `facodi_learning/models/__init__.py`:

```python
from . import course_candidate
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same `TestCourseSelection` command. Expected: the four tests pass.

- [ ] **Step 5: Commit**

```bash
git add facodi_learning/models/course_candidate.py \
        facodi_learning/models/__init__.py \
        facodi_learning/tests/test_course_selection.py \
        facodi_learning/tests/__init__.py
git commit -m "feat: add auditable course candidates"
```

---

### Task 2: Implement deterministic candidate evaluation and duplicate matching

**Files:**
- Create: `facodi_learning/services/course_selection.py`
- Modify: `facodi_learning/services/__init__.py`
- Modify: `facodi_learning/models/course_candidate.py`
- Test: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- Produces `normalize_course_title(value: str) -> str`.
- Produces `course_title_similarity(left: str, right: str) -> float` in `0..1`.
- Produces `evaluate_course_candidate(candidate, existing_channels, accepted_languages) -> dict` with keys `relevance_score`, `metadata_quality_score`, `language_fit_score`, `coverage_score`, `duplication_risk`, `matched_channel_id`, `recommendation`, `reasons`, `policy_version`.
- Candidate `action_evaluate()` consumes this service and persists evidence through `super().write()`, never direct client-writable fields.

- [ ] **Step 1: Add failing deterministic evaluation tests**

Append tests covering exact-title duplicates, non-overlapping titles, language fit and deterministic output:

```python
def test_title_duplicate_is_detected_deterministically(self):
    candidate = self.env["facodi.learning.course.candidate"].create(
        self._candidate_values(name="  PYTHON basics  ", external_id="dup")
    )
    candidate.action_evaluate()
    self.assertEqual(candidate.matched_channel_id, self.channel)
    self.assertEqual(candidate.duplication_risk, 1.0)
    self.assertEqual(candidate.recommendation, "review_existing_match")


def test_manual_candidate_has_deterministic_local_scores(self):
    candidate = self.env["facodi.learning.course.candidate"].create(
        self._candidate_values(external_id="scores")
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
```

- [ ] **Step 2: Run focused tests and verify RED**

Expected: `action_evaluate()` still raises the Task 1 validation error.

- [ ] **Step 3: Implement the selection service**

Create `facodi_learning/services/course_selection.py` with these rules:

```python
import re
import unicodedata

EVALUATION_POLICY_VERSION = "course-evaluation-v1"


def normalize_course_title(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def course_title_similarity(left, right):
    left_tokens = set(normalize_course_title(left).split())
    right_tokens = set(normalize_course_title(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    if left_tokens == right_tokens:
        return 1.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
```

Implement `evaluate_course_candidate()` using this exact baseline semantics:

- `metadata_quality_score`: fraction of present values among `name`, `description`, `institution`, `language`, `level`, `duration_minutes` (six equally weighted checks).
- `relevance_score`: `1.0` for provider `manual`; otherwise `0.5 * metadata_quality_score + 0.5 * bool(description)` until later curriculum/semantic evaluators replace the baseline.
- `language_fit_score`: `1.0` when `candidate.language.lower()` is in accepted languages; `0.5` when language is missing; `0.0` otherwise.
- `coverage_score`: `1.0` in M3.1, explicitly meaning “no curriculum coverage constraint is active yet”; M3.4 will replace/extend this signal.
- `duplication_risk`: highest `course_title_similarity(candidate.name, channel.name)` across existing `slide.channel` records; set `matched_channel_id` to the best channel when risk is at least `0.50`, else false.
- Recommendation: `review_existing_match` for duplication risk `>= 0.80`; `ignore` for relevance `< 0.40`; `shortlist` for relevance `>= 0.70` and language fit `>= 0.70`; otherwise `review`.
- Reasons: stable ordered strings describing manual relevance, metadata completeness, language compatibility and duplicate-match result. Do not interpolate private learner data.

Export the helpers in `facodi_learning/services/__init__.py`.

- [ ] **Step 4: Wire `action_evaluate()` to the service**

In `course_candidate.py`, `action_evaluate()` must:

1. check read/write access;
2. refuse terminal `rejected`, `approved`, `resolved` candidates;
3. parse accepted languages from `facodi_learning.course_selection_languages`, defaulting to `pt,en`;
4. call `evaluate_course_candidate(self, self.env["slide.channel"].search([]), accepted_languages)`;
5. persist evidence with `super(FacodiLearningCourseCandidate, candidate).write(...)`;
6. set `state="evaluated"`, `evaluated_at=fields.Datetime.now()`;
7. remain deterministic on repeated calls with unchanged inputs.

Do not apply Manual/Assisted/Auto policy in this task.

- [ ] **Step 5: Run focused tests and verify GREEN**

Expected: evaluation and duplicate tests pass, existing Task 1 tests remain green.

- [ ] **Step 6: Commit**

```bash
git add facodi_learning/services/course_selection.py \
        facodi_learning/services/__init__.py \
        facodi_learning/models/course_candidate.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "feat: evaluate course candidates deterministically"
```

---

### Task 3: Add selection settings and fail-closed policy parsing

**Files:**
- Modify: `facodi_learning/models/res_config_settings.py`
- Modify: `facodi_learning/views/res_config_settings_views.xml`
- Modify: `facodi_learning/services/course_selection.py`
- Test: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- Produces `get_course_selection_policy(env) -> dict`.
- Produces `candidate_is_auto_approve_eligible(candidate, policy) -> (bool, list[str])`.
- Configuration parameters are the sole runtime source for mode/thresholds; historical decisions later store their own snapshot/version.

- [ ] **Step 1: Write failing policy parsing and eligibility tests**

Add tests that set `ir.config_parameter` values and assert exact behavior:

```python
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
```

- [ ] **Step 2: Run tests and verify RED**

Expected: policy helper imports fail.

- [ ] **Step 3: Add exact `res.config.settings` fields**

Append these fields to `res_config_settings.py`:

```python
facodi_learning_course_selection_mode = fields.Selection(
    [("manual", "Manual"), ("assisted", "Assisted"), ("auto", "Auto Approve")],
    string="FACODI course selection mode",
    required=True,
    default="manual",
    config_parameter="facodi_learning.course_selection_mode",
)
facodi_learning_auto_approve_min_relevance = fields.Float(
    default=0.80,
    config_parameter="facodi_learning.auto_approve_min_relevance",
)
facodi_learning_auto_approve_min_metadata_quality = fields.Float(
    default=0.70,
    config_parameter="facodi_learning.auto_approve_min_metadata_quality",
)
facodi_learning_auto_approve_min_language_fit = fields.Float(
    default=0.90,
    config_parameter="facodi_learning.auto_approve_min_language_fit",
)
facodi_learning_auto_approve_min_coverage = fields.Float(
    default=0.65,
    config_parameter="facodi_learning.auto_approve_min_coverage",
)
facodi_learning_auto_approve_max_duplication_risk = fields.Float(
    default=0.30,
    config_parameter="facodi_learning.auto_approve_max_duplication_risk",
)
facodi_learning_course_selection_languages = fields.Char(
    default="pt,en",
    config_parameter="facodi_learning.course_selection_languages",
)
facodi_learning_auto_approve_trusted_providers = fields.Char(
    default="manual",
    config_parameter="facodi_learning.auto_approve_trusted_providers",
)
```

All threshold help text must state values are normalized `0..1`.

- [ ] **Step 4: Render settings beneath the existing FACODI Analysis setting**

In `res_config_settings_views.xml`, add a separate setting named `FACODI Course Selection` containing the mode, accepted-language CSV, trusted-provider CSV and five thresholds. Hide threshold rows only when the mode is `manual`; keep languages/trusted providers visible so configuration can be prepared before changing mode.

- [ ] **Step 5: Implement robust policy parsing**

In `course_selection.py` add:

```python
SELECTION_POLICY_VERSION = "course-selection-v1"
```

`get_course_selection_policy(env)` must:

- read `ir.config_parameter` with `sudo()`;
- accept only modes `manual`, `assisted`, `auto`; invalid values become `manual`;
- parse every numeric threshold, clamp to `0..1`, and fall back to the defaults above on invalid input;
- parse languages/trusted providers as lower-case stripped comma-separated sets, removing blanks;
- always return `policy_version="course-selection-v1"`.

`candidate_is_auto_approve_eligible(candidate, policy)` returns false unless:

- policy mode is `auto`;
- candidate provider is trusted;
- every positive score meets its minimum;
- duplication risk is at or below its maximum;
- candidate has no terminal state;
- candidate recommendation is not `review_existing_match` or `ignore`.

Return stable human-readable guardrail reasons for each failure.

- [ ] **Step 6: Run focused tests and verify GREEN**

Expected: default mode is manual, invalid configuration fails closed, duplicate candidate is not eligible.

- [ ] **Step 7: Commit**

```bash
git add facodi_learning/models/res_config_settings.py \
        facodi_learning/views/res_config_settings_views.xml \
        facodi_learning/services/course_selection.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "feat: configure course selection policies"
```

---

### Task 4: Implement Manual, Assisted and Auto Approve resolution

**Files:**
- Modify: `facodi_learning/models/course_candidate.py`
- Modify: `facodi_learning/services/course_selection.py`
- Test: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- Candidate `action_evaluate()` now evaluates then applies the configured selection mode.
- `_apply_selection_policy()` returns `True` after applying mode-specific state/resolution behavior.
- `_resolve()` is the only method allowed to set approved/resolved decision fields.
- `action_resolve_new()` and `action_resolve_existing()` are Manager-only wrappers around `_resolve()`.

- [ ] **Step 1: Add failing mode/resolution tests**

Add these exact behavioral cases:

```python
def test_manual_mode_never_auto_shortlists_or_resolves(self):
    candidate = self.env["facodi.learning.course.candidate"].create(
        self._candidate_values(external_id="manual-mode")
    )
    candidate.action_evaluate()
    self.assertEqual(candidate.state, "evaluated")
    self.assertFalse(candidate.resolved_channel_id)


def test_assisted_mode_shortlists_without_resolution(self):
    self.env["ir.config_parameter"].sudo().set_param(
        "facodi_learning.course_selection_mode", "assisted"
    )
    candidate = self.env["facodi.learning.course.candidate"].create(
        self._candidate_values(external_id="assisted")
    )
    candidate.action_evaluate()
    self.assertEqual(candidate.state, "shortlisted")
    self.assertFalse(candidate.resolved_channel_id)


def test_auto_mode_creates_exactly_one_unpublished_course(self):
    params = self.env["ir.config_parameter"].sudo()
    params.set_param("facodi_learning.course_selection_mode", "auto")
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="auto-new", name="Unique Cloud Course")
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
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="auto-dup", name="Python Basics")
    )
    candidate.action_evaluate()
    self.assertEqual(candidate.state, "shortlisted")
    self.assertFalse(candidate.resolved_channel_id)
```

Add manual action tests:

```python
def test_manager_can_resolve_existing_without_creating_course(self):
    before = self.env["slide.channel"].search_count([])
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="manual-existing")
    )
    candidate.with_user(self.manager).write({"matched_channel_id": self.channel.id})
    candidate.with_user(self.manager).action_evaluate()
    candidate.with_user(self.manager).action_resolve_existing()
    self.assertEqual(candidate.resolved_channel_id, self.channel)
    self.assertEqual(candidate.decision_origin, "manual")
    self.assertEqual(candidate.reviewed_by_id, self.manager)
    self.assertEqual(self.env["slide.channel"].search_count([]), before)
```

- [ ] **Step 2: Run tests and verify RED**

Expected: evaluation does not yet apply modes and resolution actions are not implemented.

- [ ] **Step 3: Implement mode application**

In `action_evaluate()`, after persisting the evaluation, call `_apply_selection_policy()`.

Implement `_apply_selection_policy()` with exact behavior:

- `manual`: leave state `evaluated`;
- `assisted`: if recommendation is `shortlist` or `review_existing_match`, set state `shortlisted`; otherwise remain `evaluated`;
- `auto`: call `candidate_is_auto_approve_eligible()`; if false, set `shortlisted` for review-worthy/review-existing results and otherwise leave `evaluated`; if true, automatic resolution may proceed only if current user is superuser or eLearning Manager, otherwise set `shortlisted` instead of elevating privileges;
- M3.1 automatic resolution always uses `resolution_type="new"`; never automatically link `matched_channel_id`.

- [ ] **Step 4: Implement the single guarded `_resolve()` path**

`_resolve()` must:

1. require exactly one candidate;
2. permit manual resolution only for `website_slides.group_website_slides_manager`;
3. permit automatic resolution only for superuser or Manager and only after `candidate_is_auto_approve_eligible()` rechecks current persisted evidence/configuration;
4. lock using `try_lock_for_update()`, invalidate and return idempotently when already `resolved` with the same resolution;
5. reject conflicting second resolutions;
6. require evaluation before resolution;
7. run canonical creation/linking inside the current ORM transaction/savepoint;
8. for `existing`, require `channel`/`matched_channel_id` to exist and be writable by the resolving Manager;
9. for `new`, create exactly one `slide.channel` with:

```python
{
    "name": candidate.name,
    "description": candidate.description or False,
    "description_short": candidate.description or False,
    "user_id": candidate.requested_by_id.id or self.env.uid,
    "website_published": False,
}
```

10. set `state="approved"` only within the same transaction immediately before canonical resolution and finish with `state="resolved"`;
11. write `resolution_type`, `resolved_channel_id`, `decision_origin`, `decision_at`, `reviewed_by_id` only for manual decisions, `decision_policy_version` only for automatic decisions, and a JSON `decision_snapshot` containing all five scores, recommendation, evaluation policy version and selection policy thresholds used;
12. clear `last_error` on success;
13. on failure, roll back partial canonical creation via savepoint and preserve the unresolved candidate with a safe `last_error`, without marking it approved/resolved.

Use `super(FacodiLearningCourseCandidate, candidate).write()` for protected internal fields; do not add context flags that clients could forge.

- [ ] **Step 5: Implement action wrappers**

- `action_shortlist()`: Officer or Manager, only unresolved evaluated candidate, writes `shortlisted` internally.
- `action_reject()`: Manager only, locks candidate, requires unresolved, sets `rejected`, `decision_origin="manual"`, `reviewed_by_id`, `decision_at`, snapshot of current evaluation.
- `action_resolve_new()`: Manager-only `_resolve("new", decision_origin="manual")`.
- `action_resolve_existing()`: Manager-only `_resolve("existing", channel=matched_channel_id, decision_origin="manual")`.

- [ ] **Step 6: Add idempotency/failure tests**

Add:

```python
def test_manual_new_resolution_is_idempotent(self):
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="idempotent-new", name="Unique Security Course")
    )
    candidate.action_evaluate()
    candidate.with_user(self.manager).action_resolve_new()
    channel = candidate.resolved_channel_id
    candidate.with_user(self.manager).action_resolve_new()
    self.assertEqual(candidate.resolved_channel_id, channel)
    self.assertFalse(channel.website_published)


def test_resolution_failure_does_not_leave_partial_course(self):
    from unittest.mock import patch
    CandidateModel = type(self.env["facodi.learning.course.candidate"])
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="failure", name="Failure Course")
    )
    candidate.action_evaluate()
    before = self.env["slide.channel"].search_count([])
    with patch.object(type(self.env["slide.channel"]), "create", side_effect=RuntimeError("boom")):
        candidate.with_user(self.manager).action_resolve_new()
    self.assertNotEqual(candidate.state, "resolved")
    self.assertFalse(candidate.resolved_channel_id)
    self.assertEqual(self.env["slide.channel"].search_count([]), before)
    self.assertTrue(candidate.last_error)
```

Persist only safe error text such as `RuntimeError: operation failed; inspect course selection configuration.`; never persist raw exception messages.

- [ ] **Step 7: Run focused tests and verify GREEN**

Expected: Manual, Assisted, Auto Approve, manual existing/new resolution, idempotency and rollback tests pass.

- [ ] **Step 8: Commit**

```bash
git add facodi_learning/models/course_candidate.py \
        facodi_learning/services/course_selection.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "feat: resolve course candidates with auto approve"
```

---

### Task 5: Enforce Officer/Manager/Public security boundaries

**Files:**
- Modify: `facodi_learning/security/ir.model.access.csv`
- Modify: `facodi_learning/security/facodi_learning_security.xml`
- Modify: `facodi_learning/tests/test_security.py`
- Test: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- Officers: read candidates globally following the existing FACODI audit pattern, create/write only records where `requested_by_id=user.id`, no unlink.
- Managers: full candidate read/write/create; model methods still protect terminal history and unlink semantics.
- Public/Portal: no model access.

- [ ] **Step 1: Write failing security tests**

Add to `test_security.py`:

```python
def test_course_candidate_public_and_portal_denied(self):
    Candidate = self.env["facodi.learning.course.candidate"]
    for user in (
        self.env.ref("base.public_user"),
        self.env["res.users"].create({
            "name": "Course Candidate Portal",
            "login": "course-candidate-portal",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        }),
    ):
        with self.assertRaises(AccessError):
            Candidate.with_user(user).create({
                "provider": "manual",
                "external_id": f"denied-{user.id}",
                "name": "Denied",
            })


def test_officer_cannot_terminally_resolve_course_candidate(self):
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.officer).create({
        "provider": "manual",
        "external_id": "officer-candidate",
        "name": "Officer Candidate",
        "description": "Safe description",
        "language": "pt",
    })
    candidate.with_user(self.officer).action_evaluate()
    with self.assertRaises(AccessError):
        candidate.with_user(self.officer).action_resolve_new()


def test_officer_cannot_edit_another_officers_candidate(self):
    other = self.env["res.users"].create({
        "name": "Other Officer",
        "login": "other-course-officer",
        "group_ids": [(6, 0, [
            self.env.ref("website_slides.group_website_slides_officer").id,
        ])],
    })
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.officer).create({
        "provider": "manual",
        "external_id": "owned-candidate",
        "name": "Owned Candidate",
    })
    with self.assertRaises(AccessError):
        candidate.with_user(other).write({"description": "Forged"})
```

- [ ] **Step 2: Run focused security tests and verify RED**

Expected: Officer candidate create/read is denied because ACL/rules do not exist yet.

- [ ] **Step 3: Add ACL rows**

Append exactly:

```csv
access_facodi_course_candidate_officer,FACODI course candidates - Officer,model_facodi_learning_course_candidate,website_slides.group_website_slides_officer,1,1,1,0
access_facodi_course_candidate_manager,FACODI course candidates - Manager,model_facodi_learning_course_candidate,website_slides.group_website_slides_manager,1,1,1,1
```

Do not add Public/Portal ACLs.

- [ ] **Step 4: Add record rules matching the existing audit pattern**

In `facodi_learning_security.xml` add:

- Officer read-all rule: domain `[(1, '=', 1)]`, read only.
- Officer create/write-own rule: domain `[('requested_by_id', '=', user.id)]`, write/create only.
- Manager all rule: domain `[(1, '=', 1)]`.

Keep terminal-state and resolution protection in Python methods in addition to ACL/rules.

- [ ] **Step 5: Run security + course-selection tests and verify GREEN**

Expected: Officers can create/reevaluate their own records, cannot edit another Officer’s record or terminally resolve; Managers can resolve; Public/Portal have no access.

- [ ] **Step 6: Commit**

```bash
git add facodi_learning/security/ir.model.access.csv \
        facodi_learning/security/facodi_learning_security.xml \
        facodi_learning/tests/test_security.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "security: protect course selection workflow"
```

---

### Task 6: Add Manager-facing Course Discovery UX and reorganize FACODI menus

**Files:**
- Create: `facodi_learning/views/course_candidate_views.xml`
- Modify: `facodi_learning/views/analysis_views.xml`
- Modify: `facodi_learning/__manifest__.py`
- Test: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- Adds backend action `action_facodi_course_candidates`.
- Adds menu hierarchy `eLearning > FACODI Learning > Course Discovery > Candidates`.
- Existing Jobs/Results/Content Mappings remain available under `FACODI Learning > Content Analysis`.

- [ ] **Step 1: Add a failing view/action smoke test**

Add:

```python
def test_course_candidate_action_and_views_are_loaded(self):
    action = self.env.ref("facodi_learning.action_facodi_course_candidates")
    self.assertEqual(action.res_model, "facodi.learning.course.candidate")
    self.assertEqual(action.view_mode, "list,form")
    self.env.ref("facodi_learning.menu_facodi_learning_course_candidates")
```

- [ ] **Step 2: Run test and verify RED**

Expected: XML IDs do not exist.

- [ ] **Step 3: Create candidate search/list/form views**

`course_candidate_views.xml` must include:

Search fields: `name`, `provider`, `institution`, `language`, `state`, `recommendation`, `matched_channel_id`, `resolved_channel_id`.

Filters: Discovered, Needs Review (`evaluated`/`shortlisted`), Resolved, Rejected, Automatic Decisions; group by state/provider/language/decision origin.

List columns: `name`, `provider`, `institution`, `language`, `state`, `recommendation`, `relevance_score`, `duplication_risk`, `matched_channel_id`, `resolved_channel_id`, `decision_origin`.

Form header actions:

- `action_evaluate` visible for unresolved states;
- `action_shortlist` visible for evaluated state to Officer/Manager;
- `action_reject` Manager-only unresolved;
- `action_resolve_existing` Manager-only when `matched_channel_id` exists and unresolved;
- `action_resolve_new` Manager-only after evaluation and unresolved;
- state statusbar.

Form body groups normalized source metadata, evaluation evidence, possible match, and terminal resolution/audit evidence. Evaluation and decision fields are readonly. Do not expose provider secrets because they do not exist on this model.

- [ ] **Step 4: Reorganize the existing menu without changing current actions**

In `analysis_views.xml`:

- create `menu_facodi_learning_root` under `website_slides.website_slides_menu_root` named `FACODI Learning`;
- change the current `menu_facodi_learning_analysis` name to `Content Analysis` and parent it to `menu_facodi_learning_root`;
- preserve existing Jobs/Results/Mappings child actions and XML IDs.

In `course_candidate_views.xml` add `menu_facodi_learning_course_discovery` and `menu_facodi_learning_course_candidates` under the new root.

- [ ] **Step 5: Update manifest/version**

Bump:

```python
"version": "19.0.1.2.0",
```

Load `views/course_candidate_views.xml` after `analysis_views.xml` so the root menu XML ID already exists.

- [ ] **Step 6: Run install tests and verify GREEN**

Run the full addon test tag on a clean database. Expected: all XML views load and the previous analysis menus/actions still resolve.

- [ ] **Step 7: Commit**

```bash
git add facodi_learning/views/course_candidate_views.xml \
        facodi_learning/views/analysis_views.xml \
        facodi_learning/__manifest__.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "feat: add course discovery manager workflow"
```

---

### Task 7: Add concurrency, snapshot and regression coverage

**Files:**
- Modify: `facodi_learning/tests/test_course_selection.py`
- Modify: `facodi_learning/models/course_candidate.py`
- Modify: `facodi_learning/services/course_selection.py`

**Interfaces:**
- No new public API.
- Strengthens `_resolve()` and `decision_snapshot` guarantees before documentation/release.

- [ ] **Step 1: Add exact terminal-evidence tests**

Add tests proving:

```python
def test_terminal_decision_snapshot_does_not_change_with_later_settings(self):
    params = self.env["ir.config_parameter"].sudo()
    params.set_param("facodi_learning.course_selection_mode", "auto")
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="snapshot", name="Unique Snapshot Course")
    )
    candidate.action_evaluate()
    snapshot = dict(candidate.decision_snapshot)
    params.set_param("facodi_learning.auto_approve_min_relevance", "0.99")
    candidate.invalidate_recordset()
    self.assertEqual(candidate.decision_snapshot, snapshot)


def test_terminal_candidate_metadata_cannot_be_rewritten(self):
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="terminal", name="Terminal Course")
    )
    candidate.action_evaluate()
    candidate.with_user(self.manager).action_resolve_new()
    with self.assertRaises(AccessError):
        candidate.with_user(self.manager).write({"description": "Retcon"})
```

Add a row-lock regression using two cursors/environments if supported by the existing Odoo `TransactionCase` harness; otherwise create a deterministic lock-conflict unit around `try_lock_for_update()` with `unittest.mock` that proves a second unavailable lock raises `ValidationError("This candidate is being resolved; retry shortly.")` rather than creating a second channel.

- [ ] **Step 2: Run and verify RED where protection is incomplete**

Expected: any missing decision-snapshot immutability or lock-unavailable handling fails.

- [ ] **Step 3: Tighten `_resolve()` without broad refactors**

Required exact behavior:

- capture the policy/evaluation snapshot before canonical write and persist the copied JSON structure;
- treat `try_lock_for_update()` returning an unavailable record as a retryable `ValidationError`;
- after lock, invalidate and re-check terminal state;
- never recompute or overwrite a terminal snapshot;
- return the existing resolved channel on same-resolution idempotent replay.

- [ ] **Step 4: Run full M3.1 test module and verify GREEN**

Expected: candidate identity, policy, modes, security, rollback, snapshot and concurrency cases all pass.

- [ ] **Step 5: Commit**

```bash
git add facodi_learning/tests/test_course_selection.py \
        facodi_learning/models/course_candidate.py \
        facodi_learning/services/course_selection.py
git commit -m "test: harden course selection concurrency and audit"
```

---

### Task 8: Document M3.1 and pass clean-install/upgrade release gates

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Verify: `.github/workflows/ci.yml` (no change expected unless the existing gate fails for a real M3.1 reason)

**Interfaces:**
- No runtime API changes.
- Documentation becomes the operator/developer contract for M3.1.

- [ ] **Step 1: Update README with the actual Manager workflow**

Document:

- `Course Discovery > Candidates`;
- manual candidate identity (`provider + external_id`);
- deterministic local evaluation;
- Manual/Assisted/Auto modes;
- trusted provider rule;
- Auto Approve fail-closed behavior;
- high duplicate risk routing to manual review;
- link-existing versus create-new-draft resolution;
- explicit statement that Auto Approve never publishes a course.

Do not document M3.2/M3.3/M3.4 features as implemented.

- [ ] **Step 2: Update architecture invariants**

Add an M3.1 section to `docs/architecture.md` describing exact model/service responsibilities, state machine, selection policy version, snapshot evidence, locking/idempotency and why `slide.channel` remains canonical.

- [ ] **Step 3: Run clean install with the repository CI command**

Use the exact clean-install command from `.github/workflows/ci.yml` against PostgreSQL 16:

```bash
docker run --rm \
  --network facodi-learning-ci \
  -e HOST=facodi-learning-db -e PORT=5432 \
  -e USER=odoo -e PASSWORD=odoo \
  -v "$PWD:/mnt/extra-addons:ro" \
  -v facodi-learning-data:/var/lib/odoo \
  odoo:19.0 \
  --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
  --workers=0 --without-demo=True \
  -d facodi_learning_ci -i facodi_learning \
  --test-tags /facodi_learning --stop-after-init
```

Expected: exit 0 and all pre-M3 + M3.1 tests pass.

- [ ] **Step 4: Run upgrade regression gate**

```bash
docker run --rm \
  --network facodi-learning-ci \
  -e HOST=facodi-learning-db -e USER=odoo -e PASSWORD=odoo \
  -v "$PWD:/mnt/extra-addons:ro" \
  -v facodi-learning-data:/var/lib/odoo \
  odoo:19.0 \
  --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
  --workers=0 --without-demo=True \
  -d facodi_learning_ci -u facodi_learning \
  --test-tags /facodi_learning --stop-after-init
```

Expected: exit 0; existing `facodi.learning.source`, analysis jobs/results/attempts and content mappings remain valid; no data migration is required because M3.1 is additive.

- [ ] **Step 5: Verify no automatic publication regression**

Run a focused database assertion or Odoo shell check that every channel created from a candidate in tests has `website_published=False`. Any Auto Approve-created public channel is a release blocker.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md docs/architecture.md
git commit -m "docs: document M3.1 course selection"
```

- [ ] **Step 7: Push branch and require GitHub Actions success before review**

Push the implementation branch and confirm the exact-head GitHub Actions run passes both install and upgrade steps. Do not merge on a stale green SHA.

---

## M3.1 Completion Checklist

M3.1 is complete only when all of the following are demonstrated on the exact implementation head:

- one `(provider, external_id)` produces one candidate;
- unresolved metadata refresh is permitted and terminal evidence is immutable;
- deterministic local evaluation works with no network access;
- Manual mode never auto-resolves;
- Assisted mode shortlists without resolution;
- Auto Approve resolves only a trusted, fully eligible, low-duplicate candidate;
- high duplicate risk never auto-links/auto-creates silently;
- manual Manager link-existing and create-new workflows both work;
- automatic and manual resolution use the same `_resolve()` path;
- a new canonical course is exactly one standard `slide.channel` and remains unpublished;
- concurrent/replayed resolution is safe and idempotent;
- Public/Portal cannot access candidate records;
- Officers cannot terminally resolve candidates;
- historical policy/evaluation snapshots survive later configuration changes;
- existing content-analysis/ingestion/mapping tests remain green;
- clean install and upgrade on Odoo 19/PostgreSQL 16 are green.

## Follow-on Plan Boundaries

Do not implement these inside the M3.1 branch. Each receives its own plan after M3.1 interfaces are merged and re-read from `main`:

1. `M3.2 Course Profile` — deterministic `slide.channel` profile aggregation only.
2. `M3.3 Course Mapping Engine` — retrieval/ranking, semantic `course.mapping`, native Odoo prerequisite application and learner-safe relations.
3. `M3.4 Curriculum Reference & Coverage` — versioned programme/unit/coverage models with LESTI-shaped fixtures and no learner progression/credit recognition.
4. `M3.5 External Discovery Providers` — `discovery.run`, provider registry/cron and optional YouTube/OER/institutional addons.
5. `M3.6 Semantic/AI Ranking` — optional semantic evaluators/rankers after deterministic boundaries and audit policies are proven.
