# M3.5a Discovery Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provider-neutral course discovery execution, audit history, candidate refresh/evaluation, scheduling, and Manager UX without adding any network dependency to `facodi_learning`.

**Architecture:** `facodi.learning.discovery.run` owns one provider execution. Providers are registry callables returning normalized course-candidate dictionaries; the run normalizes and upserts `facodi.learning.course.candidate`, evaluates unresolved candidates through the existing M3.1 selection pipeline, and records only aggregate execution evidence. The core has no external SDK/API client and no provider may create `slide.channel` directly.

**Tech Stack:** Odoo 19 Community, `website_slides`, PostgreSQL 16, Python/Odoo ORM, `ir.cron`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-learning-course-selection-mapping-design.md` sections 13–15, 17–22.

## Global Constraints

- Odoo 19 Community remains canonical: discovered external courses become `facodi.learning.course.candidate`, never direct provider-created `slide.channel` rows.
- Public/Portal cannot read discovery runs or provider metadata.
- eLearning Officers may read discovery audit; Managers own provider execution/configuration.
- Runtime secrets, auth headers, cookies, tokens and secret-bearing payload keys are never persisted/logged verbatim.
- Terminal candidate decisions (`rejected`, `resolved`) are never silently reversed/refreshed.
- `manual` candidate creation remains a complete offline workflow.
- Standard `ir.cron`, bounded batches and `_commit_progress()` are used; no Celery/Redis/private worker.
- Provider failures are isolated per run and never block another provider in the scheduled loop.

---

### Task 1: Normalized Discovery Contract and Run Audit Model

**Files:**
- Create: `facodi_learning/services/course_discovery.py`
- Create: `facodi_learning/models/discovery_run.py`
- Modify: `facodi_learning/models/__init__.py`
- Test: `facodi_learning/tests/test_course_discovery.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Produces `normalize_discovery_item(provider: str, item: dict) -> dict`.
- Produces `facodi.learning.discovery.run._get_course_discovery_registry() -> dict[str, callable]`.
- Core registry includes `manual` as an offline/no-op provider; provider addons extend with `super()`.
- Run states: `pending`, `processing`, `completed`, `failed`; fields include provider, requester, timestamps, aggregate counters and sanitized `last_error`.

- [ ] Write RED tests for model registration, allowed create fields, immutable processing/audit fields, provider registry contract, blank identity rejection and secret-key stripping from normalized metadata.
- [ ] Run `/facodi_learning` tests and verify only new discovery tests fail for missing model/service.
- [ ] Implement strict normalization of `provider`, `external_id`, `name`, URL/text fields, non-negative duration, JSON metadata and recursive removal of secret-looking keys (`token`, `authorization`, `cookie`, `password`, `secret`, `api_key`, `apikey`).
- [ ] Implement run schema/create/write/unlink guards and `manual` registry entry without network behavior.
- [ ] Re-run clean install + addon tests + same-tree upgrade and commit GREEN.

### Task 2: Idempotent Candidate Upsert, Refresh and Evaluation

**Files:**
- Modify: `facodi_learning/models/course_candidate.py`
- Modify: `facodi_learning/models/discovery_run.py`
- Test: `facodi_learning/tests/test_course_discovery.py`

**Interfaces:**
- Candidate adds readonly audit fields `discovered_at`, `last_discovered_at`, `last_discovery_run_id`.
- Produces private server method `facodi.learning.course.candidate._upsert_from_discovery(normalized, discovery_run)` returning `(candidate, outcome)` where outcome is `created`, `refreshed`, or `ignored`.
- `discovery_run.action_process()` invokes one registry provider, normalizes every item, upserts candidates, evaluates newly created/refreshed unresolved candidates with existing `action_evaluate()`, and stores aggregate counts.

- [ ] Write RED tests for new candidate creation, replay refresh, reevaluation after refresh, terminal candidate ignore, duplicate provider/external identity, malformed item ignore, and no direct `slide.channel` creation by the provider boundary.
- [ ] Verify RED failures are isolated to missing upsert/process behavior.
- [ ] Implement server-owned discovery audit fields and `_upsert_from_discovery()` using existing candidate identity/metadata semantics without RPC-forgeable context flags.
- [ ] Process the provider inside a savepoint: provider-level exception rolls back that run’s candidate mutations, then records a sanitized failed run; invalid individual items increment `candidates_ignored` without persisting unsafe payloads.
- [ ] Evaluate each created/refreshed candidate through M3.1 after successful upsert; terminal candidates are counted ignored and never reevaluated.
- [ ] Re-run full gates and commit GREEN.

### Task 3: Security, Backend Workspace, Settings and Cron

**Files:**
- Modify: `facodi_learning/security/ir.model.access.csv`
- Modify: `facodi_learning/security/facodi_learning_security.xml`
- Create: `facodi_learning/views/discovery_run_views.xml`
- Modify: `facodi_learning/views/course_candidate_views.xml`
- Modify: `facodi_learning/models/res_config_settings.py`
- Modify: `facodi_learning/views/res_config_settings_views.xml`
- Modify: `facodi_learning/data/ir_cron.xml`
- Modify: `facodi_learning/__manifest__.py`
- Test: `facodi_learning/tests/test_course_discovery.py`

**Interfaces:**
- Settings: `facodi_learning.discovery_enabled`, `facodi_learning.discovery_enabled_providers`, `facodi_learning.discovery_batch_size`.
- Menu: `eLearning → FACODI Learning → Course Discovery → Discovery Runs`.
- Cron calls `facodi.learning.discovery.run._cron_discover_courses()`.

- [ ] Write RED tests for Public/Portal denial, Officer read-only, Manager create/process, XML IDs/menu action, settings defaults and cron disabled-by-default behavior.
- [ ] Implement ACL/rules: Officers read, Managers operate, no Public/Portal ACL.
- [ ] Implement list/form/search views with aggregate counters and sanitized errors only.
- [ ] Add settings with conservative defaults: discovery disabled, enabled provider list empty, batch size 20 (clamped 1..100).
- [ ] Add scheduled action; when enabled, iterate enabled providers independently, create/process one run each, call `_commit_progress()` in real cron context, and continue after provider failure.
- [ ] Load new XML in manifest and re-run gates.

### Task 4: Concurrency, Provider Isolation and Retry Semantics

**Files:**
- Modify: `facodi_learning/models/discovery_run.py`
- Test: `facodi_learning/tests/test_course_discovery.py`

**Interfaces:**
- `action_process()` uses `try_lock_for_update()` on the run and fails/returns safely if another worker owns it.
- A completed/failed run is immutable execution history; retry means a new run, not rewriting old history.

- [ ] Write RED tests for unavailable run lock, two enabled providers where one raises, bounded cron behavior, unknown provider fail-safe, and completed run replay idempotency.
- [ ] Implement fail-closed locking and per-provider isolation without `sudo()` around candidate/course operations.
- [ ] Verify one provider failure does not prevent the next provider run from completing.
- [ ] Re-run full clean-install + upgrade gates and commit GREEN.

### Task 5: Release Documentation and Upgrade Gate

**Files:**
- Modify: `facodi_learning/__manifest__.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/validation.md`
- Modify: `.github/workflows/ci.yml` only if required to preserve real pre-M3.5 sentinels.

**Interfaces:**
- Bump core addon from `19.0.1.5.0` to `19.0.1.6.0`.
- Document provider registry and discovery-run boundaries.

- [ ] Document M3.5a behavior, security, provider extension contract and no-network core guarantee.
- [ ] Extend real-upgrade validation so M3.1–M3.4 sentinels survive and zero discovery runs/candidates are fabricated by upgrade.
- [ ] Run exact-head clean install + full tests + real merge-base upgrade + same-tree re-upgrade.
- [ ] Review branch diff against `main`, verify no network dependency entered `facodi_learning`, and commit release evidence.
