# FACODI Learning M3.1 Course Selection Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an auditable deterministic course-candidate selection pipeline with Manual, Assisted and fail-closed Auto Approve modes that resolves candidates into canonical unpublished/existing Odoo `slide.channel` records.

**Architecture:** Add one domain model, `facodi.learning.course.candidate`, and one focused selection service. Candidate evaluation produces independent normalized signals and a recommendation; policy application may shortlist or resolve only through guarded candidate model methods. Manual and automatic resolution converge on `_resolve()`, use row locking, never auto-publish, and never create a parallel course model.

**Tech Stack:** Odoo 19 Community, `website_slides`, Python/Odoo ORM, XML backend views, `ir.config_parameter`, PostgreSQL 16, existing Docker-based GitHub Actions.

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
- Heuristic duplicate matching MUST never auto-link an existing course in M3.1; high duplicate risk routes to review.
- Public and Portal users MUST NOT read candidate/evaluation records.
- Officers may create/reevaluate their own manual candidates; only eLearning Managers or trusted automation may perform terminal resolution.
- Existing content analysis, content mappings and ingestion behavior MUST remain unchanged.
- Install/upgrade gates continue against Odoo 19 + PostgreSQL 16 with `--test-tags /facodi_learning`.

---

## File Structure

### New files

- `facodi_learning/models/course_candidate.py` — candidate lifecycle, guarded transitions, evaluation orchestration and canonical resolution.
- `facodi_learning/services/course_selection.py` — deterministic title similarity, candidate scoring, policy parsing and Auto Approve eligibility.
- `facodi_learning/views/course_candidate_views.xml` — candidate search/list/form actions and Course Discovery menus.
- `facodi_learning/tests/test_course_selection.py` — identity, evaluation, modes, resolution, concurrency/idempotency and unpublished-course regressions.

### Modified files

- `facodi_learning/models/__init__.py`
- `facodi_learning/services/__init__.py`
- `facodi_learning/models/res_config_settings.py`
- `facodi_learning/views/res_config_settings_views.xml`
- `facodi_learning/views/analysis_views.xml`
- `facodi_learning/security/ir.model.access.csv`
- `facodi_learning/security/facodi_learning_security.xml`
- `facodi_learning/tests/__init__.py`
- `facodi_learning/tests/test_security.py`
- `facodi_learning/__manifest__.py`
- `README.md`
- `docs/architecture.md`

---

### Task 1: Candidate model, identity and lifecycle guards

**Files:**
- Create: `facodi_learning/models/course_candidate.py`
- Modify: `facodi_learning/models/__init__.py`
- Create: `facodi_learning/tests/test_course_selection.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Produces model `facodi.learning.course.candidate`.
- Public actions reserved for later tasks: `action_evaluate()`, `action_shortlist()`, `action_reject()`, `action_resolve_new()`, `action_resolve_existing()`.
- Private transition primitive reserved for later tasks: `_resolve(resolution_type, channel=None, decision_origin="manual", policy_version=None, decision_snapshot=None)`.

- [ ] **Step 1: Register the test module and write RED identity/lifecycle tests**

Append to `facodi_learning/tests/__init__.py`:

```python
from . import test_course_selection
```

Create `facodi_learning/tests/test_course_selection.py`:

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
        candidate.write({"description": "Updated description", "metadata": {"v": 2}})
        self.assertEqual(candidate.description, "Updated description")
        self.assertEqual(candidate.metadata, {"v": 2})
```

- [ ] **Step 2: Run the focused test and verify RED**

```bash
odoo -d facodi_learning_test \
  --addons-path=/usr/lib/python3/dist-packages/odoo/addons,$PWD \
  --workers=0 --without-demo=True \
  -i facodi_learning \
  --test-tags /facodi_learning:TestCourseSelection \
  --stop-after-init
```

Expected: test setup fails because `facodi.learning.course.candidate` does not exist.

- [ ] **Step 3: Implement the model schema and direct-write guards**

Create `facodi_learning/models/course_candidate.py` beginning with:

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
    resolved_channel_id = fields.Many2one(
        "slide.channel", readonly=True, ondelete="restrict"
    )
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

Add constraints:

```python
@api.constrains("provider", "external_id", "name")
def _check_required_text(self):
    if any(
        not (record.provider or "").strip()
        or not (record.external_id or "").strip()
        or not (record.name or "").strip()
        for record in self
    ):
        raise ValidationError("Provider, external identity and name must not be blank.")

@api.constrains("duration_minutes")
def _check_duration(self):
    if any(record.duration_minutes < 0 for record in self):
        raise ValidationError("Course duration cannot be negative.")

@api.constrains(
    "relevance_score",
    "metadata_quality_score",
    "language_fit_score",
    "coverage_score",
    "duplication_risk",
)
def _check_scores(self):
    for record in self:
        for value in (
            record.relevance_score,
            record.metadata_quality_score,
            record.language_fit_score,
            record.coverage_score,
            record.duplication_risk,
        ):
            if not 0 <= value <= 1:
                raise ValidationError("Course-selection scores must be between zero and one.")
```

Implement `create()` with an allowlist of normalized-source fields. `requested_by_id`, when supplied, must equal `self.env.uid`. Reject any client-supplied state/evaluation/decision evidence and explicitly initialize lifecycle/evidence fields.

Implement `write()` so `provider`, `external_id`, `requested_by_id`, evaluation evidence and terminal decision fields are never direct-writable. Permit `matched_channel_id` direct write only for an eLearning Manager while unresolved. Permit normalized metadata refresh only in `discovered`, `evaluated`, `shortlisted`.

Implement `unlink()` so only Managers can remove unresolved records; terminal records are audit history.

For the five future action methods, use explicit bodies that raise:

```python
raise ValidationError("Evaluate the candidate before this action.")
```

Do not use context bypass flags, `pass`, or `NotImplementedError`.

Register:

```python
from . import course_candidate
```

in `models/__init__.py`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Expected: Task 1 tests pass.

- [ ] **Step 5: Commit**

```bash
git add facodi_learning/models/course_candidate.py \
        facodi_learning/models/__init__.py \
        facodi_learning/tests/test_course_selection.py \
        facodi_learning/tests/__init__.py
git commit -m "feat: add auditable course candidates"
```

---

### Task 2: Deterministic evaluation and duplicate matching

**Files:**
- Create: `facodi_learning/services/course_selection.py`
- Modify: `facodi_learning/services/__init__.py`
- Modify: `facodi_learning/models/course_candidate.py`
- Modify: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- `normalize_course_title(value: str) -> str`
- `course_title_similarity(left: str, right: str) -> float`
- `evaluate_course_candidate(candidate, existing_channels, accepted_languages) -> dict`
- Candidate `action_evaluate()` persists the returned evidence.

- [ ] **Step 1: Add RED deterministic evaluation tests**

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
        self._candidate_values(external_id="scores", name="Unique Python Foundations")
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

- [ ] **Step 2: Run and verify RED**

Expected: `action_evaluate()` still raises the Task 1 validation error.

- [ ] **Step 3: Implement deterministic helpers**

Create `services/course_selection.py`:

```python
import re
import unicodedata

EVALUATION_POLICY_VERSION = "course-evaluation-v1"
SELECTION_POLICY_VERSION = "course-selection-v1"


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

Implement `evaluate_course_candidate()` with exactly these baseline semantics:

- metadata quality = fraction present among `name`, `description`, `institution`, `language`, `level`, `duration_minutes`;
- relevance = `1.0` for provider `manual`; for other providers `0.5 * metadata_quality + 0.5 * bool(description)`;
- language fit = `1.0` when supplied language is accepted, `0.5` when absent, `0.0` otherwise;
- coverage = `1.0` in M3.1 and means “no curriculum coverage constraint active”; M3.4 will replace/extend it;
- duplication risk = maximum title similarity to existing channels;
- `matched_channel_id` = best match only when risk `>= 0.50`;
- recommendation = `review_existing_match` when duplicate risk `>= 0.80`; `ignore` when relevance `< 0.40`; `shortlist` when relevance `>= 0.70` and language fit `>= 0.70`; otherwise `review`;
- reasons = stable ordered safe strings explaining source relevance, metadata completeness, language fit and duplicate result;
- policy version = `course-evaluation-v1`.

Export the three service helpers from `services/__init__.py`.

- [ ] **Step 4: Implement `action_evaluate()`**

For each unresolved candidate:

```python
accepted_languages = {
    value.strip().lower()
    for value in (
        self.env["ir.config_parameter"]
        .sudo()
        .get_param("facodi_learning.course_selection_languages", "pt,en")
    ).split(",")
    if value.strip()
}
result = evaluate_course_candidate(
    candidate,
    self.env["slide.channel"].search([]),
    accepted_languages,
)
```

Persist result evidence through `super(FacodiLearningCourseCandidate, candidate).write(...)`, set `state="evaluated"` and `evaluated_at=fields.Datetime.now()`. Do not apply selection mode yet.

- [ ] **Step 5: Run and verify GREEN**

Expected: deterministic score/duplicate tests pass and Task 1 remains green.

- [ ] **Step 6: Commit**

```bash
git add facodi_learning/services/course_selection.py \
        facodi_learning/services/__init__.py \
        facodi_learning/models/course_candidate.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "feat: evaluate course candidates deterministically"
```

---

### Task 3: Selection configuration and fail-closed policy

**Files:**
- Modify: `facodi_learning/models/res_config_settings.py`
- Modify: `facodi_learning/views/res_config_settings_views.xml`
- Modify: `facodi_learning/services/course_selection.py`
- Modify: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- `get_course_selection_policy(env) -> dict`
- `candidate_is_auto_approve_eligible(candidate, policy) -> tuple[bool, list[str]]`

- [ ] **Step 1: Add RED policy tests**

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

- [ ] **Step 2: Run and verify RED**

Expected: policy helper imports fail.

- [ ] **Step 3: Add settings fields**

Add to `res_config_settings.py`:

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

- [ ] **Step 4: Add the exact settings UI block**

Inside the existing Website/eLearning settings block, after the FACODI Analysis setting, add:

```xml
<setting id="facodi_learning_course_selection_settings"
         string="FACODI Course Selection"
         help="Configure deterministic course candidate review and Auto Approve guardrails.">
    <div class="content-group">
        <div class="row mt16">
            <label for="facodi_learning_course_selection_mode" class="col-lg-4 o_light_label"/>
            <field name="facodi_learning_course_selection_mode" class="oe_inline"/>
        </div>
        <div class="row mt16">
            <label for="facodi_learning_course_selection_languages" class="col-lg-4 o_light_label"/>
            <field name="facodi_learning_course_selection_languages" class="oe_inline"/>
        </div>
        <div class="row mt16">
            <label for="facodi_learning_auto_approve_trusted_providers" class="col-lg-4 o_light_label"/>
            <field name="facodi_learning_auto_approve_trusted_providers" class="oe_inline"/>
        </div>
        <div invisible="facodi_learning_course_selection_mode == 'manual'">
            <field name="facodi_learning_auto_approve_min_relevance"/>
            <field name="facodi_learning_auto_approve_min_metadata_quality"/>
            <field name="facodi_learning_auto_approve_min_language_fit"/>
            <field name="facodi_learning_auto_approve_min_coverage"/>
            <field name="facodi_learning_auto_approve_max_duplication_risk"/>
        </div>
    </div>
</setting>
```

Add field help strings explaining that thresholds are normalized `0..1` and trusted providers/languages are comma-separated identifiers.

- [ ] **Step 5: Implement robust policy parsing**

`get_course_selection_policy(env)` must read `ir.config_parameter` with `sudo()`, accept only `manual|assisted|auto`, parse/clamp each threshold to `0..1`, fall back to the defaults above on invalid input, parse languages/trusted providers into lower-case non-empty sets, and return `policy_version="course-selection-v1"`.

`candidate_is_auto_approve_eligible()` returns false unless mode is auto, provider is trusted, every positive score meets minimum, duplicate risk is at/below maximum, candidate is unresolved, and recommendation is neither `review_existing_match` nor `ignore`. Return a stable reason for every failed guardrail.

- [ ] **Step 6: Run and verify GREEN**

Expected: defaults, invalid values and duplicate-risk tests are green.

- [ ] **Step 7: Commit**

```bash
git add facodi_learning/models/res_config_settings.py \
        facodi_learning/views/res_config_settings_views.xml \
        facodi_learning/services/course_selection.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "feat: configure course selection policies"
```

---

### Task 4: Manual, Assisted and Auto Approve resolution

**Files:**
- Modify: `facodi_learning/models/course_candidate.py`
- Modify: `facodi_learning/services/course_selection.py`
- Modify: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- `action_evaluate()` evaluates then calls `_apply_selection_policy()`.
- `_apply_selection_policy()` applies Manual/Assisted/Auto behavior without privilege escalation.
- `_resolve()` is the only path that sets approval/resolution evidence.

- [ ] **Step 1: Add RED mode tests**

```python
def test_manual_mode_never_auto_shortlists_or_resolves(self):
    candidate = self.env["facodi.learning.course.candidate"].create(
        self._candidate_values(external_id="manual-mode", name="Unique Manual Course")
    )
    candidate.action_evaluate()
    self.assertEqual(candidate.state, "evaluated")
    self.assertFalse(candidate.resolved_channel_id)


def test_assisted_mode_shortlists_without_resolution(self):
    self.env["ir.config_parameter"].sudo().set_param(
        "facodi_learning.course_selection_mode", "assisted"
    )
    candidate = self.env["facodi.learning.course.candidate"].create(
        self._candidate_values(external_id="assisted", name="Unique Assisted Course")
    )
    candidate.action_evaluate()
    self.assertEqual(candidate.state, "shortlisted")
    self.assertFalse(candidate.resolved_channel_id)


def test_auto_mode_creates_exactly_one_unpublished_course(self):
    self.env["ir.config_parameter"].sudo().set_param(
        "facodi_learning.course_selection_mode", "auto"
    )
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

- [ ] **Step 2: Add RED manual resolution tests**

```python
def test_manager_can_resolve_existing_without_creating_course(self):
    before = self.env["slide.channel"].search_count([])
    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="manual-existing", name="Existing Choice")
    )
    candidate.action_evaluate()
    candidate.with_user(self.manager).write({"matched_channel_id": self.channel.id})
    candidate.with_user(self.manager).action_resolve_existing()
    self.assertEqual(candidate.resolved_channel_id, self.channel)
    self.assertEqual(candidate.decision_origin, "manual")
    self.assertEqual(candidate.reviewed_by_id, self.manager)
    self.assertEqual(self.env["slide.channel"].search_count([]), before)


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
```

- [ ] **Step 3: Run and verify RED**

Expected: mode application/resolution actions are not implemented.

- [ ] **Step 4: Implement `_apply_selection_policy()`**

Exact behavior:

- manual: state remains `evaluated`;
- assisted: recommendations `shortlist` and `review_existing_match` become `shortlisted`; other results remain `evaluated`;
- auto: call `candidate_is_auto_approve_eligible()`; failures that need review become `shortlisted`, otherwise remain `evaluated`;
- auto eligibility may call `_resolve("new", decision_origin="automatic", policy_version=...)` only when current user is superuser or eLearning Manager; an Officer action never escalates and instead leaves the candidate shortlisted;
- M3.1 never auto-links `matched_channel_id`.

- [ ] **Step 5: Implement `_resolve()` as the single guarded path**

For one candidate, `_resolve()` must:

1. validate manual resolution requires eLearning Manager;
2. validate automatic resolution requires superuser or Manager and re-check current policy eligibility;
3. call `try_lock_for_update()` and raise `ValidationError("This candidate is being resolved; retry shortly.")` if the lock is unavailable;
4. invalidate and re-check state after locking;
5. return the already resolved channel on an idempotent same-resolution replay;
6. reject conflicting second resolution;
7. require current evaluation evidence;
8. use a savepoint for canonical create/link;
9. for existing resolution, require a real writable `slide.channel` selected by the Manager;
10. for new resolution, create exactly one standard channel:

```python
channel = self.env["slide.channel"].create({
    "name": candidate.name,
    "description": candidate.description or False,
    "description_short": candidate.description or False,
    "user_id": candidate.requested_by_id.id or self.env.uid,
    "website_published": False,
})
```

11. persist state/resolution/decision evidence through `super(...).write()` only;
12. manual decision: `reviewed_by_id=self.env.uid`, no policy version;
13. automatic decision: `reviewed_by_id=False`, `decision_policy_version="course-selection-v1"`;
14. `decision_snapshot` contains all five scores, recommendation, evaluation policy version and the selection thresholds/trusted-provider evidence used;
15. clear `last_error` on success;
16. on exception, roll back the savepoint, keep candidate unresolved and persist only safe text: `<ExceptionType>: operation failed; inspect course selection configuration.`.

- [ ] **Step 6: Implement action wrappers**

- `action_shortlist()`: Officer/Manager, evaluated unresolved candidate only.
- `action_reject()`: Manager only, lock, terminal manual decision + snapshot.
- `action_resolve_new()`: Manager wrapper for `_resolve("new", decision_origin="manual")`.
- `action_resolve_existing()`: Manager wrapper for `_resolve("existing", channel=matched_channel_id, decision_origin="manual")`.

- [ ] **Step 7: Add rollback test**

```python
def test_resolution_failure_does_not_leave_partial_course(self):
    from unittest.mock import patch

    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="failure", name="Failure Course")
    )
    candidate.action_evaluate()
    before = self.env["slide.channel"].search_count([])
    ChannelModel = type(self.env["slide.channel"])
    with patch.object(ChannelModel, "create", side_effect=RuntimeError("secret detail")):
        candidate.with_user(self.manager).action_resolve_new()
    candidate.invalidate_recordset()
    self.assertNotEqual(candidate.state, "resolved")
    self.assertFalse(candidate.resolved_channel_id)
    self.assertEqual(self.env["slide.channel"].search_count([]), before)
    self.assertIn("RuntimeError: operation failed", candidate.last_error)
    self.assertNotIn("secret detail", candidate.last_error)
```

- [ ] **Step 8: Run and verify GREEN**

Expected: all mode/resolution/idempotency/rollback tests pass.

- [ ] **Step 9: Commit**

```bash
git add facodi_learning/models/course_candidate.py \
        facodi_learning/services/course_selection.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "feat: resolve course candidates with auto approve"
```

---

### Task 5: Security boundaries

**Files:**
- Modify: `facodi_learning/security/ir.model.access.csv`
- Modify: `facodi_learning/security/facodi_learning_security.xml`
- Modify: `facodi_learning/tests/test_security.py`

**Interfaces:**
- Officer: read all candidate audit records, create/write only own requested candidates, no unlink.
- Manager: model ACL full; Python guards still protect terminal evidence/unlink semantics.
- Public/Portal: no candidate ACL.

- [ ] **Step 1: Add RED security tests**

```python
def test_course_candidate_public_and_portal_denied(self):
    Candidate = self.env["facodi.learning.course.candidate"]
    portal = self.env["res.users"].create({
        "name": "Course Candidate Portal",
        "login": "course-candidate-portal",
        "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
    })
    for user in (self.env.ref("base.public_user"), portal):
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
```

Add a second Officer and prove that Officer cannot edit a candidate whose `requested_by_id` belongs to the first Officer.

- [ ] **Step 2: Run and verify RED**

Expected: Officer access is missing until ACL/rules are added.

- [ ] **Step 3: Add ACLs**

```csv
access_facodi_course_candidate_officer,FACODI course candidates - Officer,model_facodi_learning_course_candidate,website_slides.group_website_slides_officer,1,1,1,0
access_facodi_course_candidate_manager,FACODI course candidates - Manager,model_facodi_learning_course_candidate,website_slides.group_website_slides_manager,1,1,1,1
```

- [ ] **Step 4: Add record rules**

Add three rules following the existing audit pattern:

```xml
<record id="rule_facodi_course_candidate_officer_read" model="ir.rule">
    <field name="name">FACODI course candidate: officer read all</field>
    <field name="model_id" ref="model_facodi_learning_course_candidate"/>
    <field name="groups" eval="[(4, ref('website_slides.group_website_slides_officer'))]"/>
    <field name="domain_force">[(1, '=', 1)]</field>
    <field name="perm_read" eval="1"/>
    <field name="perm_write" eval="0"/>
    <field name="perm_create" eval="0"/>
    <field name="perm_unlink" eval="0"/>
</record>
<record id="rule_facodi_course_candidate_officer_write_own" model="ir.rule">
    <field name="name">FACODI course candidate: officer create/write own</field>
    <field name="model_id" ref="model_facodi_learning_course_candidate"/>
    <field name="groups" eval="[(4, ref('website_slides.group_website_slides_officer'))]"/>
    <field name="domain_force">[('requested_by_id', '=', user.id)]</field>
    <field name="perm_read" eval="0"/>
    <field name="perm_write" eval="1"/>
    <field name="perm_create" eval="1"/>
    <field name="perm_unlink" eval="0"/>
</record>
<record id="rule_facodi_course_candidate_manager" model="ir.rule">
    <field name="name">FACODI course candidate: manager all</field>
    <field name="model_id" ref="model_facodi_learning_course_candidate"/>
    <field name="groups" eval="[(4, ref('website_slides.group_website_slides_manager'))]"/>
    <field name="domain_force">[(1, '=', 1)]</field>
</record>
```

- [ ] **Step 5: Run and verify GREEN**

Expected: Public/Portal denied; Officer own create/reevaluate works; cross-Officer mutation and terminal resolution denied; Manager resolution works.

- [ ] **Step 6: Commit**

```bash
git add facodi_learning/security/ir.model.access.csv \
        facodi_learning/security/facodi_learning_security.xml \
        facodi_learning/tests/test_security.py
git commit -m "security: protect course selection workflow"
```

---

### Task 6: Course Discovery backend UX and menu structure

**Files:**
- Create: `facodi_learning/views/course_candidate_views.xml`
- Modify: `facodi_learning/views/analysis_views.xml`
- Modify: `facodi_learning/__manifest__.py`
- Modify: `facodi_learning/tests/test_course_selection.py`

**Interfaces:**
- `action_facodi_course_candidates`
- `menu_facodi_learning_root`
- `menu_facodi_learning_course_discovery`
- `menu_facodi_learning_course_candidates`
- Existing Jobs/Results/Mappings remain under `Content Analysis` with the same action XML IDs.

- [ ] **Step 1: Add RED XML-ID smoke test**

```python
def test_course_candidate_action_and_views_are_loaded(self):
    action = self.env.ref("facodi_learning.action_facodi_course_candidates")
    self.assertEqual(action.res_model, "facodi.learning.course.candidate")
    self.assertEqual(action.view_mode, "list,form")
    self.env.ref("facodi_learning.menu_facodi_learning_course_candidates")
```

- [ ] **Step 2: Run and verify RED**

Expected: XML IDs do not exist.

- [ ] **Step 3: Create search/list/form/action XML**

The search view must expose `name`, `provider`, `institution`, `language`, `state`, `recommendation`, `matched_channel_id`, `resolved_channel_id`, filters for discovered/needs-review/resolved/rejected/automatic decisions, and group-by state/provider/language/decision origin.

The list view columns must be:

```xml
<field name="name"/>
<field name="provider"/>
<field name="institution" optional="show"/>
<field name="language"/>
<field name="state"/>
<field name="recommendation"/>
<field name="relevance_score" optional="hide"/>
<field name="duplication_risk" optional="show"/>
<field name="matched_channel_id" optional="show"/>
<field name="resolved_channel_id" optional="show"/>
<field name="decision_origin" optional="hide"/>
```

The form header must use object buttons for `action_evaluate`, `action_shortlist`, `action_reject`, `action_resolve_existing`, `action_resolve_new`, with Manager group restrictions on terminal actions and state-based `invisible` expressions. Form body separates source metadata, evaluation evidence, match choice and terminal resolution evidence; evaluation/decision fields are readonly.

Create the window action with `view_mode="list,form"`.

- [ ] **Step 4: Reorganize existing menus**

In `analysis_views.xml` create:

```xml
<menuitem id="menu_facodi_learning_root"
          name="FACODI Learning"
          parent="website_slides.website_slides_menu_root"
          groups="website_slides.group_website_slides_officer"
          sequence="8"/>
```

Change the existing `menu_facodi_learning_analysis` to `name="Content Analysis"` and `parent="menu_facodi_learning_root"`. Preserve its existing child menu/action XML IDs.

In `course_candidate_views.xml` add Course Discovery/Candidates menus beneath `menu_facodi_learning_root`.

- [ ] **Step 5: Update manifest/version**

Change:

```python
"version": "19.0.1.2.0",
```

and add `views/course_candidate_views.xml` after `views/analysis_views.xml` in `data`.

- [ ] **Step 6: Run clean-install tests and verify GREEN**

Expected: views load, candidate action exists, old analysis actions still resolve.

- [ ] **Step 7: Commit**

```bash
git add facodi_learning/views/course_candidate_views.xml \
        facodi_learning/views/analysis_views.xml \
        facodi_learning/__manifest__.py \
        facodi_learning/tests/test_course_selection.py
git commit -m "feat: add course discovery manager workflow"
```

---

### Task 7: Locking, snapshots and terminal audit hardening

**Files:**
- Modify: `facodi_learning/tests/test_course_selection.py`
- Modify: `facodi_learning/models/course_candidate.py`

**Interfaces:**
- No new public API.
- `_resolve()` must explicitly handle unavailable row locks and preserve terminal snapshot evidence.

- [ ] **Step 1: Add RED snapshot tests**

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

- [ ] **Step 2: Add one deterministic lock-unavailable test**

Use the exact existing Odoo locking primitive and mock only lock availability:

```python
def test_resolution_refuses_unavailable_row_lock(self):
    from unittest.mock import patch

    candidate = self.env["facodi.learning.course.candidate"].with_user(self.manager).create(
        self._candidate_values(external_id="locked", name="Locked Course")
    )
    candidate.action_evaluate()
    CandidateModel = type(candidate)
    empty = self.env["facodi.learning.course.candidate"]
    with patch.object(CandidateModel, "try_lock_for_update", return_value=empty):
        with self.assertRaisesRegex(ValidationError, "being resolved"):
            candidate.with_user(self.manager).action_resolve_new()
    self.assertFalse(candidate.resolved_channel_id)
```

Do not replace this with a second ad-hoc concurrency mechanism; production behavior remains Odoo `try_lock_for_update()`.

- [ ] **Step 3: Run and verify RED where needed**

Expected: any missing lock-unavailable or snapshot immutability handling fails.

- [ ] **Step 4: Tighten `_resolve()`**

Ensure it captures a copied JSON snapshot before the canonical write, never recomputes/overwrites a terminal snapshot, raises the exact retryable validation on unavailable lock, invalidates and rechecks state after locking, and returns the same canonical channel on idempotent same-resolution replay.

- [ ] **Step 5: Run the full M3.1 test class and verify GREEN**

Expected: identity, evaluation, modes, security, rollback, snapshot and locking cases pass.

- [ ] **Step 6: Commit**

```bash
git add facodi_learning/tests/test_course_selection.py \
        facodi_learning/models/course_candidate.py
git commit -m "test: harden course selection concurrency and audit"
```

---

### Task 8: Documentation and release gates

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Verify: `.github/workflows/ci.yml` (no change expected unless a genuine M3.1 gate failure requires it)

**Interfaces:**
- No runtime API changes.

- [ ] **Step 1: Document only implemented M3.1 behavior in README**

Document Course Discovery > Candidates, manual identity, deterministic local evaluation, all three selection modes, trusted providers, duplicate review, link-existing/create-new-draft resolution, and the explicit invariant “Auto Approve never publishes a course”. Do not describe M3.2+ as implemented.

- [ ] **Step 2: Document architecture invariants**

Add an M3.1 section to `docs/architecture.md` covering candidate identity, evaluation service, policy parsing/versioning, state transitions, shared `_resolve()`, locking/idempotency, decision snapshots and canonical `slide.channel` ownership.

- [ ] **Step 3: Run clean install using the CI-equivalent environment**

```bash
docker network create facodi-learning-ci || true
docker run -d --name facodi-learning-db --network facodi-learning-ci \
  -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo \
  -e POSTGRES_DB=facodi_learning_ci postgres:16 || true
until docker exec facodi-learning-db pg_isready -U odoo -d facodi_learning_ci; do sleep 2; done

docker run --rm --network facodi-learning-ci \
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
docker run --rm --network facodi-learning-ci \
  -e HOST=facodi-learning-db -e USER=odoo -e PASSWORD=odoo \
  -v "$PWD:/mnt/extra-addons:ro" \
  -v facodi-learning-data:/var/lib/odoo \
  odoo:19.0 \
  --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
  --workers=0 --without-demo=True \
  -d facodi_learning_ci -u facodi_learning \
  --test-tags /facodi_learning --stop-after-init
```

Expected: exit 0. Existing sources/jobs/attempts/results/content mappings remain intact; M3.1 requires no data rewrite because its schema is additive.

- [ ] **Step 5: Verify unpublished invariant explicitly**

Run Odoo shell/database assertion over candidates with `resolution_type="new"` and fail release if any `resolved_channel_id.website_published` is true.

- [ ] **Step 6: Commit docs**

```bash
git add README.md docs/architecture.md
git commit -m "docs: document M3.1 course selection"
```

- [ ] **Step 7: Push and verify exact-head GitHub Actions**

Require successful clean-install and upgrade checks on the exact implementation SHA. Never accept a stale green run.

---

## M3.1 Completion Checklist

M3.1 is complete only when the exact implementation head proves all of the following:

- one `(provider, external_id)` produces one candidate;
- unresolved metadata refresh is allowed and terminal evidence is immutable;
- deterministic local evaluation works without network access;
- Manual mode never auto-resolves;
- Assisted mode shortlists without resolution;
- Auto Approve resolves only a trusted, fully eligible, low-duplicate candidate;
- high duplicate risk never auto-links/auto-creates silently;
- manual Manager link-existing and create-new workflows both work;
- automatic and manual resolution use the same `_resolve()` path;
- a new canonical course is exactly one standard `slide.channel` and remains unpublished;
- locking/replay is safe and idempotent;
- Public/Portal cannot access candidates;
- Officers cannot terminally resolve candidates;
- historical snapshots survive later configuration changes;
- existing content-analysis/ingestion/mapping regressions remain green;
- clean install and upgrade on Odoo 19/PostgreSQL 16 are green.

## Follow-on Plan Boundaries

Do not implement these inside the M3.1 branch. Each receives its own implementation plan after M3.1 is merged and its interfaces are re-read from `main`:

1. **M3.2 Course Profile** — deterministic `slide.channel` profile aggregation only.
2. **M3.3 Course Mapping Engine** — retrieval/ranking, semantic `course.mapping`, native Odoo prerequisite application and learner-safe relations.
3. **M3.4 Curriculum Reference & Coverage** — versioned programme/unit/coverage models with LESTI-shaped fixtures and no learner progression/credit recognition.
4. **M3.5 External Discovery Providers** — `discovery.run`, provider registry/cron and optional YouTube/OER/institutional addons.
5. **M3.6 Semantic/AI Ranking** — optional semantic evaluators/rankers after deterministic audit/policy boundaries are proven.
