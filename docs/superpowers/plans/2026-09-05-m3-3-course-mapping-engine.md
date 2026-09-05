# M3.3 Course Mapping Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an auditable, deterministic course-to-course mapping engine on top of canonical Odoo `slide.channel`, with human review, low-risk optional Auto Approve, native prerequisite application, and learner-safe approved output.

**Architecture:** Keep standard `slide.channel` as the only canonical course entity and reuse `course-profile-v1` from M3.2 as deterministic input. Introduce one audit model, `facodi.learning.course.mapping`, for proposed/reviewed course relationships; semantic relationships remain represented there, while `prerequisite` records are proposal/evidence only and approval writes the actual relationship exclusively to Odoo's native `slide.channel.prerequisite_channel_ids`. Retrieval/ranking is a pure deterministic service with no network, embeddings, or learner data.

**Tech Stack:** Odoo 19 Community, Python ORM/services, QWeb/backend XML views, PostgreSQL 16, Odoo `TransactionCase`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-learning-course-selection-mapping-design.md`

## Global Constraints

- Canonical courses remain standard `slide.channel`; canonical content remains `slide.slide`.
- Existing content-level `facodi.learning.mapping` remains content-only.
- Odoo-native `prerequisite_channel_ids` is the only final prerequisite truth.
- No learner progress, member email, or other learner-private data enters course mapping evidence.
- No external AI, embeddings, vector database, network discovery, Celery, Redis, or private worker framework in M3.3.
- Course mapping confidence is normalized to `0..1` and is evidence, not learner progress.
- Public/Portal cannot read proposed/rejected mappings, confidence, evidence, or policy snapshots.
- Officers may propose/inspect according to existing eLearning ownership rules; only Managers may terminally approve/reject or apply prerequisites.
- `related` and `complements` are the only relation types eligible for optional Auto Approve in this milestone.
- `alternative`, `equivalent`, `continuation`, and `prerequisite` remain manual-review-only.
- New learner-facing outputs must re-check native course publication, website, visibility, and access before returning canonical channels.

---

### Task 1: Course mapping audit model and review lifecycle

**Files:**
- Create: `facodi_learning/models/course_mapping.py`
- Modify: `facodi_learning/models/__init__.py`
- Modify: `facodi_learning/security/ir.model.access.csv`
- Modify: `facodi_learning/security/facodi_learning_security.xml`
- Test: `facodi_learning/tests/test_course_mapping.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Produces model `facodi.learning.course.mapping`.
- Produces `action_approve()` / `action_reject()` and private `_review(state)`.
- Fields: `source_channel_id`, `target_channel_id`, `mapping_type`, `confidence`, `origin`, `state`, `evidence`, `ranking_version`, `reviewed_by_id`, `reviewed_at`, `policy_version`, `decision_snapshot`, `native_applied_by_id`, `native_applied_at`.

- [ ] **Step 1: Write failing lifecycle tests**

Cover:

```python
def test_course_mapping_rejects_self_relation(self): ...
def test_course_mapping_rejects_confidence_outside_zero_one(self): ...
def test_course_mapping_unique_directed_triple(self): ...
def test_course_mapping_officer_cannot_review(self): ...
def test_course_mapping_manager_can_approve_semantic_relation(self): ...
def test_reviewed_course_mapping_is_immutable(self): ...
def test_public_and_portal_cannot_read_course_mapping(self): ...
```

Use two ordinary `slide.channel` records. For Manager review, run as a real internal user in `website_slides.group_website_slides_manager`, not superuser.

- [ ] **Step 2: Run the focused tests and verify RED**

Run the repository CI equivalent with `--test-tags /facodi_learning` on the branch. Expected failure: model `facodi.learning.course.mapping` is missing; pre-existing tests remain loadable.

- [ ] **Step 3: Implement the minimal model**

Use:

```python
class FacodiLearningCourseMapping(models.Model):
    _name = "facodi.learning.course.mapping"
    _description = "FACODI Course Mapping"
    _order = "create_date desc, id desc"
```

Mapping types:

```python
[
    ("related", "Related"),
    ("alternative", "Alternative"),
    ("continuation", "Continuation"),
    ("complements", "Complements"),
    ("equivalent", "Equivalent"),
    ("prerequisite", "Prerequisite"),
]
```

Required invariants:

```python
_mapping_unique = models.Constraint(
    "unique(source_channel_id, target_channel_id, mapping_type)",
    "This course mapping already exists.",
)
```

Reject self-links and confidence outside `0..1`. `create()` must force `state='proposed'` and clear all review/native-apply fields. `write()` must prevent direct changes to lifecycle/audit identity and forbid changing reviewed rows. `unlink()` may delete only unreviewed manual proposals. `_review()` must use `try_lock_for_update()`, re-read the row, require Manager group, and timestamp terminal review.

For `mapping_type != 'prerequisite'`, `action_approve()` only marks the FACODI semantic relation approved. Task 3 replaces the prerequisite branch with native application.

- [ ] **Step 4: Add ACLs and record rules**

Mirror the proven content-mapping policy:

- Public/Portal: no ACL.
- Officer: read all; create/write only when `source_channel_id.user_id == user.id`; no terminal review because Python method requires Manager.
- Manager: full model access, still constrained by Python lifecycle guards.

- [ ] **Step 5: Run focused and full tests, verify GREEN, then commit**

Commit message:

```text
feat: add auditable course mapping lifecycle
```

---

### Task 2: Deterministic retrieval and ranking engine

**Files:**
- Create: `facodi_learning/services/course_mapping.py`
- Modify: `facodi_learning/services/__init__.py`
- Modify: `facodi_learning/models/slide_channel.py`
- Test: `facodi_learning/tests/test_course_mapping_engine.py`

**Interfaces:**
- Consumes: `channel._facodi_course_profile()` from M3.2.
- Produces: `retrieve_course_candidates(source_channel, limit=20)`.
- Produces: `rank_course_pair(source_profile, target_profile)` returning `{signals, confidence, mapping_type, ranking_version, reasons}`.
- Produces: `channel._facodi_course_mapping_candidates(limit=20)` returning ordered ranked dictionaries.
- Produces: `channel._facodi_propose_course_mappings(limit=20)` returning `facodi.learning.course.mapping` records.

- [ ] **Step 1: Write failing engine tests**

Cover deterministic behavior:

```python
def test_retrieval_excludes_source_and_inactive_courses(self): ...
def test_retrieval_respects_website_compatibility(self): ...
def test_rank_prefers_shared_course_tags(self): ...
def test_rank_uses_language_compatibility_from_course_profile(self): ...
def test_rank_output_is_deterministic(self): ...
def test_generate_proposals_is_idempotent(self): ...
def test_engine_does_not_use_learner_membership(self): ...
```

Website compatibility baseline:

- source with a specific `website_id`: target is eligible when target has the same website or no website restriction;
- source with no website restriction: do not exclude targets merely because they have a website, but normal ORM access still applies.

- [ ] **Step 2: Run and verify RED**

Expected failures: missing service/methods only.

- [ ] **Step 3: Implement cheap retrieval**

Use ordinary ORM `search()` with no `sudo()`:

```python
domain = [
    ("id", "!=", source_channel.id),
    ("active", "=", True),
]
```

When `source_channel.website_id` is set, add an OR condition accepting same website or `website_id=False`. Order candidates deterministically by `sequence, id`. Cap the candidate set before ranking.

- [ ] **Step 4: Implement deterministic ranking**

Ranking version:

```python
COURSE_MAPPING_RANKING_VERSION = "course-mapping-v1"
```

Signals in `0..1`:

- `title_overlap`: Jaccard overlap of normalized title tokens;
- `tag_overlap`: Jaccard overlap of standard course tag IDs;
- `language_compatibility`: 1.0 if either side has no detected-language evidence, 1.0 if language sets overlap, else 0.0;
- `duration_similarity`: `1 - min(abs(a-b)/max(a,b), 1)` when both durations are positive, else neutral `0.5`.

Confidence:

```python
confidence = round(
    0.30 * title_overlap
    + 0.40 * tag_overlap
    + 0.20 * language_compatibility
    + 0.10 * duration_similarity,
    4,
)
```

The baseline deterministic engine proposes only `related`. Other semantic types and `prerequisite` are available for manual proposal/review in M3.3 but are not inferred without stronger evidence.

- [ ] **Step 5: Implement proposal generation**

`_facodi_propose_course_mappings(limit=20)` requires Officer read/write access to the source course and calls the service. For each ranked candidate with confidence >= `0.50`, search the unique triple first; reuse an existing row rather than duplicating it. New generated proposals use:

```python
origin="analysis"
evidence={"signals": ..., "reasons": ..., "source_profile_version": "course-profile-v1"}
ranking_version="course-mapping-v1"
```

Do not rewrite an existing proposal/reviewed mapping on rerun.

- [ ] **Step 6: Run tests, verify GREEN, commit**

Commit:

```text
feat: add deterministic course mapping engine
```

---

### Task 3: Native prerequisite proposal application and cycle protection

**Files:**
- Modify: `facodi_learning/models/course_mapping.py`
- Test: `facodi_learning/tests/test_course_mapping_prerequisite.py`

**Interfaces:**
- Produces `_would_create_prerequisite_cycle()`.
- `action_approve()` for `mapping_type='prerequisite'` writes only `source_channel_id.prerequisite_channel_ids` and audit fields.

- [ ] **Step 1: Write failing prerequisite tests**

Cover:

```python
def test_prerequisite_approval_writes_native_odoo_field(self): ...
def test_prerequisite_mapping_record_is_audit_not_second_truth(self): ...
def test_prerequisite_cycle_is_rejected(self): ...
def test_prerequisite_three_node_cycle_is_rejected(self): ...
def test_prerequisite_approval_is_idempotent_when_native_link_exists(self): ...
def test_officer_cannot_apply_native_prerequisite(self): ...
```

Semantic direction: source requires target.

- [ ] **Step 2: Run and verify RED**

Expected: semantic review exists but native prerequisite application/cycle guard is absent.

- [ ] **Step 3: Implement graph cycle detection**

Before adding `source -> target`, traverse `target.prerequisite_channel_ids` breadth-first/depth-first using ordinary non-sudo records. If `source.id` is reachable, raise `ValidationError` before any write.

Do not infer cycles from semesters, sequence, tags, or content order.

- [ ] **Step 4: Implement native application in the same transaction**

Inside the locked Manager review path:

```python
source.prerequisite_channel_ids = [(4, target.id)]
```

Then mark the proposal `approved`, set reviewer/time, and set `native_applied_by_id` / `native_applied_at`. If the native relation already exists, do not duplicate it; terminal review can still complete idempotently.

No `sudo()` and no custom prerequisite relation table.

- [ ] **Step 5: Run tests, verify GREEN, commit**

Commit:

```text
feat: apply reviewed prerequisites through Odoo native field
```

---

### Task 4: Independent course-mapping Auto Approve policy

**Files:**
- Create: `facodi_learning/services/course_mapping_policy.py`
- Modify: `facodi_learning/services/__init__.py`
- Modify: `facodi_learning/models/course_mapping.py`
- Modify: `facodi_learning/models/res_config_settings.py`
- Modify: `facodi_learning/views/res_config_settings_views.xml`
- Test: `facodi_learning/tests/test_course_mapping_policy.py`

**Interfaces:**
- Produces policy version `course-mapping-policy-v1`.
- Produces `get_course_mapping_policy(env)`.
- Produces `is_course_mapping_auto_eligible(mapping, policy)`.
- Produces `mapping._maybe_auto_approve()`.

- [ ] **Step 1: Write failing policy tests**

Cover:

```python
def test_mapping_policy_defaults_to_manual(self): ...
def test_related_can_auto_approve_above_threshold_for_manager(self): ...
def test_complements_can_auto_approve_when_configured(self): ...
def test_alternative_equivalent_continuation_never_auto_approve(self): ...
def test_prerequisite_never_auto_approves(self): ...
def test_officer_context_never_escalates_to_auto_approve(self): ...
def test_auto_decision_snapshot_is_immutable(self): ...
```

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Add conservative settings**

Fields:

```python
facodi_learning_course_mapping_mode = fields.Selection(
    [("manual", "Manual"), ("assisted", "Assisted"), ("auto", "Auto Approve")],
    default="manual",
    config_parameter="facodi_learning.course_mapping_mode",
)
facodi_learning_course_mapping_auto_types = fields.Char(
    default="related",
    config_parameter="facodi_learning.course_mapping_auto_types",
)
facodi_learning_course_mapping_min_confidence = fields.Float(
    default=0.85,
    config_parameter="facodi_learning.course_mapping_min_confidence",
)
```

Parse config fail-closed. Clamp confidence threshold to `0..1`. Allowed automatic types are intersected with `{related, complements}`.

- [ ] **Step 4: Implement policy and immutable snapshot**

Auto approve only when:

- mode is `auto`;
- current execution user is actual eLearning Manager/superuser;
- mapping is still proposed;
- mapping type is low-risk and configured;
- confidence meets threshold;
- mapping type is not prerequisite.

Decision snapshot records confidence, mapping type, ranking version, effective threshold/types, and `course-mapping-policy-v1`. Auto approval leaves `reviewed_by_id=False` and stores `policy_version`; human review records reviewer and no fake human identity for automated decisions.

- [ ] **Step 5: Run tests, verify GREEN, commit**

Commit:

```text
feat: add fail-closed course mapping auto approve policy
```

---

### Task 5: Learner-safe approved course relations

**Files:**
- Modify: `facodi_learning/models/slide_channel.py`
- Test: `facodi_learning/tests/test_course_mapping_visibility.py`

**Interfaces:**
- Produces `channel._facodi_related_channels(website=None)` returning ordinary `slide.channel` records only.

- [ ] **Step 1: Write failing visibility tests**

Cover:

```python
def test_only_approved_semantic_relations_are_returned(self): ...
def test_rejected_and_proposed_relations_are_hidden(self): ...
def test_prerequisite_audit_row_is_not_returned_as_semantic_relation(self): ...
def test_unpublished_target_course_is_hidden(self): ...
def test_other_website_target_is_hidden(self): ...
def test_native_visibility_access_is_respected(self): ...
def test_public_user_cannot_read_course_mapping_audit_model(self): ...
```

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Implement limited-elevation lookup**

Follow the existing `_facodi_related_slides()` pattern: use limited elevation only to fetch IDs from approved mapping audit rows; browse returned targets with the caller's ordinary environment and filter by native `website_published`, website compatibility and `is_visible`/access behavior. Do not return confidence/evidence to learners.

Exclude `mapping_type='prerequisite'`; the learner-facing prerequisite behavior stays Odoo-native.

- [ ] **Step 4: Run tests, verify GREEN, commit**

Commit:

```text
feat: expose learner-safe approved course relations
```

---

### Task 6: Manager UX, course action, docs and release boundary

**Files:**
- Create: `facodi_learning/views/course_mapping_views.xml`
- Create: `facodi_learning/views/slide_channel_views.xml`
- Modify: `facodi_learning/views/analysis_views.xml`
- Modify: `facodi_learning/__manifest__.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Test: `facodi_learning/tests/test_course_mapping_views.py`

**Interfaces:**
- Adds `eLearning → FACODI Learning → Course Mapping → Relations`.
- Adds course-form action/button `Find FACODI Relations` for Officers.
- Bumps addon version from `19.0.1.3.0` to `19.0.1.4.0`.

- [ ] **Step 1: Write failing view/action tests**

Assert XML IDs exist and point to the new model/action/menu. Assert inherited `website_slides.view_slide_channel_form` contains a button calling the mapping proposal action.

- [ ] **Step 2: Run and verify RED**

- [ ] **Step 3: Add backend relation views**

List/form fields show source, target, mapping type, confidence, origin, ranking version, state and review/native-apply audit. Form buttons Approve/Reject are Manager-only and visible only while proposed.

Reorganize current menu label `Mappings` to `Content Mappings` under `Content Analysis`; add `Course Mapping` branch with `Relations`.

- [ ] **Step 4: Add course form integration**

Inherit `website_slides.view_slide_channel_form`. Insert a stat/action button in `div[name='button_box']` for Officers that invokes `action_facodi_propose_course_mappings` and opens the relation action filtered to `source_channel_id = active course` after proposal generation.

- [ ] **Step 5: Document and bump version**

README/architecture must state:

- deterministic `course-mapping-v1` baseline;
- semantic relations vs native prerequisites;
- Auto Approve risk restrictions;
- no embeddings/AI/discovery/curriculum coverage in M3.3;
- learner-facing approved/access-filtered behavior;
- additive upgrade, no migration rewrite.

- [ ] **Step 6: Run exact-head clean install + upgrade gate**

Required evidence:

```text
Odoo 19.0 + PostgreSQL 16
clean install: 0 failures / 0 errors
upgrade: 0 failures / 0 errors
```

Run the full `/facodi_learning` suite, not only M3.3 tests.

- [ ] **Step 7: Review stacked diff and create draft PR**

Compare `feat/m3-2-course-profile` → `feat/m3-3-course-mapping-engine`. Confirm no M3.4+ curriculum models, discovery providers, embeddings or learner progression logic entered the diff. Create a draft PR based on `feat/m3-2-course-profile`; do not merge without explicit user authorization.
