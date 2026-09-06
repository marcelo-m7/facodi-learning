# M3.5 External Discovery Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auditable provider-driven course discovery with bounded Odoo cron execution and an optional YouTube playlist provider, while keeping `slide.channel` creation exclusively behind the existing M3.1 selection/resolution workflow.

**Architecture:** `facodi.learning.discovery.run` is operational execution history. Provider adapters register callables through `_get_course_discovery_registry()` and return normalized course-candidate dictionaries. Core persists or refreshes only unresolved `facodi.learning.course.candidate` records, evaluates them through the existing M3.1 policy, ignores terminal candidates, and never creates/publishes courses directly. `facodi_learning_youtube` is a separate optional addon that discovers YouTube playlists as course candidates using the YouTube Data API; credentials stay in `FACODI_YOUTUBE_API_KEY`.

**Tech Stack:** Odoo 19 Community, PostgreSQL 16, Python stdlib HTTP for optional provider addon, Odoo ORM/cron/config parameters, TransactionCase, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-learning-course-selection-mapping-design.md`

## Global Constraints

- `slide.channel` remains the only canonical FACODI course.
- Discovery providers never create, publish, enroll into, or modify `slide.channel` directly.
- Provider output is normalized before persistence and contains only safe core fields plus safe metadata.
- Stable candidate identity remains unique `(provider, external_id)`.
- Unresolved candidates (`discovered`, `evaluated`, `shortlisted`) may refresh and reevaluate; terminal `rejected`/`resolved` records are never silently reversed.
- A materially new source revision uses a new external identity.
- Provider failures are isolated and store sanitized errors only; credentials, authorization headers, cookies and raw secret-bearing responses are never persisted or logged.
- External requests use explicit timeouts and bounded pagination.
- Core has no external SDK dependency and works with no configured provider.
- Standard `ir.cron`, bounded batches and Odoo `_commit_progress()` are used; no Celery/Redis/custom worker.
- Public/Portal cannot read discovery runs or provider execution metadata.
- Only Managers configure/schedule/process discovery runs.
- Auto Approve authority remains the existing M3.1 policy/trusted-provider mechanism; discovery itself grants no new authority.

---

### Task 1: Discovery run audit model and provider registry

**Files:**
- Create `facodi_learning/models/discovery_run.py`
- Modify `facodi_learning/models/__init__.py`
- Modify `facodi_learning/security/ir.model.access.csv`
- Modify `facodi_learning/security/facodi_learning_security.xml`
- Create `facodi_learning/tests/test_discovery_run.py`
- Modify `facodi_learning/tests/__init__.py`

**Interfaces:**
- Model `facodi.learning.discovery.run` fields: `provider`, `state`, `started_at`, `completed_at`, `items_seen`, `candidates_created`, `candidates_refreshed`, `candidates_ignored`, `last_error`.
- `_get_course_discovery_registry()` returns `{provider_name: callable}`; baseline contains `manual` returning an empty iterable.
- `action_process()` is Manager-only and terminally records completed/failed execution.
- `_normalize_discovery_item(provider, item)` returns validated candidate vals limited to the M3.1 source fields.

- [ ] Add RED tests for model existence, Public/Portal denial, Officer read-only denial, Manager processing, unknown provider failure, malformed identity failure and sanitized provider exceptions.
- [ ] Run full `/facodi_learning` suite and verify only discovery contracts fail.
- [ ] Implement the model with states `pending/processing/completed/failed`, counters defaulting to zero, row locking, no direct write of terminal evidence, and a registry containing `manual`.
- [ ] Implement normalization requiring non-empty `external_id` and `name`, forcing `provider` from the run, stripping text identity, validating non-negative duration, and keeping only `source_url/name/description/institution/language/level/duration_minutes/license_name/metadata`.
- [ ] Add Manager ACL/rule only; no Public/Portal/Officer ACL.
- [ ] Run clean install + upgrade and commit `feat: add provider-neutral discovery runs`.

### Task 2: Idempotent candidate refresh and evaluation pipeline

**Files:**
- Modify `facodi_learning/models/discovery_run.py`
- Modify `facodi_learning/models/course_candidate.py`
- Create `facodi_learning/tests/test_discovery_pipeline.py`

**Interfaces:**
- `course_candidate._facodi_refresh_from_discovery(vals)` is private/server-owned, allows only normalized metadata fields, preserves identity/requester, rejects terminal records, clears stale evaluation evidence, returns the candidate.
- `discovery_run._upsert_candidate(vals)` creates or refreshes by `(provider, external_id)` and returns `(candidate, status)` where status is `created`, `refreshed`, or `ignored`.
- Processing evaluates every created/refreshed candidate through `action_evaluate()` in the current Manager/superuser context; terminal candidates are ignored.

- [ ] RED tests: duplicate provider output creates one candidate; second run refreshes metadata and reevaluates; terminal rejected/resolved candidate is ignored; refresh cannot alter identity; Auto Approve still depends on existing trusted-provider policy; provider cannot directly resolve/create course.
- [ ] Implement private refresh using controlled `super(...).write()` after validating state and allowed fields; reset evaluation scores/recommendation/timestamps to baseline before reevaluation.
- [ ] Implement per-item savepoints so one malformed item increments ignored/fails safely without losing earlier valid candidates; provider-level exception still marks run failed.
- [ ] Run clean install + upgrade and commit `feat: add idempotent discovery candidate pipeline`.

### Task 3: Discovery configuration, cron and backend workspace

**Files:**
- Modify `facodi_learning/models/res_config_settings.py`
- Modify `facodi_learning/views/res_config_settings_views.xml`
- Modify `facodi_learning/data/ir_cron.xml`
- Create `facodi_learning/views/discovery_views.xml`
- Modify `facodi_learning/__manifest__.py`
- Create `facodi_learning/tests/test_discovery_cron_ui.py`

**Interfaces:**
- Config parameters: `facodi_learning.discovery_enabled` boolean, `facodi_learning.discovery_providers` comma-separated provider names, `facodi_learning.discovery_batch_size` integer clamped `1..100`.
- `facodi.learning.discovery.run._cron_discover_courses()` creates/processes at most configured batch providers in deterministic order when enabled; unknown configured providers are represented as failed runs rather than crashing the cron.
- Menu `eLearning → FACODI Learning → Course Discovery → Discovery Runs`.

- [ ] RED tests for defaults, bounds, disabled cron no-op, enabled bounded provider processing, provider failure isolation, XML action/menu loading.
- [ ] Implement config parameters using existing `res.config.settings` pattern.
- [ ] Add cron with default disabled and daily interval; in real cron context call `_commit_progress()` after each run, otherwise remain transaction-neutral in tests/manual calls.
- [ ] Add search/list/form views with Manager `Process` action and counters/errors; do not expose credentials/provider raw payloads.
- [ ] Run clean install + upgrade and commit `feat: add scheduled discovery workspace`.

### Task 4: Optional YouTube playlist discovery addon

**Files:**
- Create `facodi_learning_youtube/__init__.py`
- Create `facodi_learning_youtube/__manifest__.py`
- Create `facodi_learning_youtube/models/__init__.py`
- Create `facodi_learning_youtube/models/discovery_run.py`
- Create `facodi_learning_youtube/models/res_config_settings.py`
- Create `facodi_learning_youtube/views/res_config_settings_views.xml`
- Create `facodi_learning_youtube/tests/__init__.py`
- Create `facodi_learning_youtube/tests/test_youtube_discovery.py`
- Modify `.github/workflows/ci.yml`

**Interfaces:**
- Extends `_get_course_discovery_registry()` with key `youtube` using `super()`.
- API key from `os.environ['FACODI_YOUTUBE_API_KEY']`; never stored in Odoo.
- Safe config parameter `facodi_learning.youtube_channel_ids` stores comma/newline-separated YouTube channel IDs only.
- `_discover_youtube(run)` calls YouTube Data API v3 `playlists.list` with `part=snippet,contentDetails`, `channelId`, `maxResults=50`, explicit timeout `10`, pagination cap 5 pages/channel.
- Normalized playlist candidate: external ID=playlist ID, source URL=`https://www.youtube.com/playlist?list=<id>`, title/description, institution=`channelTitle`, metadata containing only `channel_id`, `playlist_id`, `item_count`.

- [ ] RED tests mock `urllib.request.urlopen`: registry extension, missing key sanitized failure, pagination, timeout argument, duplicate playlist idempotency, secret not persisted/logged, malformed API response failure.
- [ ] Implement stdlib JSON HTTP adapter with bounded pages and generic sanitized exceptions; no google SDK dependency.
- [ ] Update CI to install/test `facodi_learning_youtube` after core while preserving real core upgrade gate.
- [ ] Run optional addon clean install/tests and core regression; commit `feat: add optional YouTube playlist discovery provider`.

### Task 5: Release hardening and documentation

**Files:**
- Modify `README.md`
- Modify `docs/architecture.md`
- Modify `docs/validation.md`
- Modify `facodi_learning/__manifest__.py`
- Create `facodi_learning/tests/test_discovery_release_invariants.py`

**Interfaces:**
- Core version becomes `19.0.1.6.0`.
- Release invariants prove provider cannot directly create/publish canonical courses, terminal decisions remain unchanged by rediscovery, Public/Portal denial, and core install works without optional provider addon/API key.

- [ ] Add release invariant tests and run them before docs/version changes.
- [ ] Document provider contract, candidate refresh semantics, cron boundaries, YouTube playlist mapping rationale, credentials boundary, and explicit non-goals.
- [ ] Bump version to `19.0.1.6.0`.
- [ ] Run full strengthened CI on exact head: real merge-base upgrade, core clean install/tests, core re-upgrade, optional YouTube addon install/tests.
- [ ] Review diff against M3.4 head; verify no curriculum execution/AI/embeddings/learner personalization entered M3.5.
- [ ] Open PR based on `feat/m3-4-curriculum-reference-coverage` while PR #8 is unmerged; retarget to `main` after M3.4 merges. Do not merge without explicit authorization.
