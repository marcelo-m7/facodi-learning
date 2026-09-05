> Historical baseline. Current implementation and constraints are documented in README.md and docs/architecture.md.

# FACODI Learning Initial Odoo 19 Addon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independently installable Odoo 19 Community addon that extends standard eLearning content with auditable analysis jobs, normalized results, suggested standard tags, and human-reviewed semantic mappings.

**Architecture:** Keep `slide.slide`, `slide.channel`, and `slide.tag` as the canonical Odoo learning models. Add only the analysis/mapping records Odoo does not provide, use standard eLearning Officer/Manager groups, use `ir.config_parameter`/`res.config.settings` for provider selection, and process pending jobs in bounded batches through standard `ir.cron`.

**Tech Stack:** Odoo 19 Community, Python ORM, XML views/security/data, standard Odoo tests, GitHub Actions, PostgreSQL 16.

**Spec:** `docs/superpowers/specs/2026-09-04-facodi-learning-design.md`

## Global Constraints

- Target Odoo 19 Community.
- Prefer standard Odoo `website_slides` models, groups, views, tags, settings, actions, cron and test framework before custom abstractions.
- No dependency on FACODI theme.
- No external AI/network credential is required for the baseline implementation.
- Automated mappings remain proposals until a manager approves them.
- External-provider adapters must remain replaceable without changing domain records.

---

### Task 1: Test harness and module contract

**Files:** `.github/workflows/ci.yml`, `facodi_learning/__init__.py`, `facodi_learning/__manifest__.py`, `facodi_learning/tests/__init__.py`, `facodi_learning/tests/test_analysis.py`.

**Interfaces:** The repository exposes one module named `facodi_learning`; CI installs it on a clean Odoo 19 database and runs `/facodi_learning` tests.

- [ ] Write tests that create a standard `slide.channel` and `slide.slide`, request analysis, process it, assert one historical result, and assert the slide remains the canonical content record.
- [ ] Push the test harness and verify CI fails because the analysis API/model is not implemented yet.
- [ ] Add only the minimum manifest/package scaffolding required for Odoo to discover the module.

### Task 2: Analysis domain and local standard-first provider

**Files:** `facodi_learning/models/slide_slide.py`, `facodi_learning/models/analysis_job.py`, `facodi_learning/models/analysis_result.py`, `facodi_learning/services/analysis.py`.

**Interfaces:** `slide.slide.action_facodi_request_analysis()` creates `facodi.learning.analysis.job`; `job.action_process()` delegates to a provider selected by `_get_provider_registry()`; the built-in `local_metadata` provider uses title, description, transcript and standard `slide.tag` records without external calls.

- [ ] Add failing tests for pending→processing→completed, failure→retry, append-only historical results and standard tag suggestions.
- [ ] Implement job/result models, the extensible provider hook, deterministic local provider, sanitized errors and retry behavior.
- [ ] Implement bounded `_cron_process_pending_jobs()` using standard `ir.cron` progress reporting when executed by cron.
- [ ] Run the module tests and keep all analysis history on repeated runs.

### Task 3: Human-reviewed semantic mapping

**Files:** `facodi_learning/models/learning_mapping.py`, `facodi_learning/tests/test_mapping.py`.

**Interfaces:** `facodi.learning.mapping` relates two standard `slide.slide` records; states are `proposed`, `approved`, `rejected`; only standard eLearning Managers may approve/reject.

- [ ] Write failing tests for source≠target, unique mapping tuple, manager approval/rejection and Officer denial.
- [ ] Implement mapping constraints, provenance fields and explicit review methods.
- [ ] Verify automated origins cannot bypass the proposed state.

### Task 4: Security, settings, cron and standard UI extensions

**Files:** `facodi_learning/security/ir.model.access.csv`, `facodi_learning/security/facodi_learning_security.xml`, `facodi_learning/data/ir_cron.xml`, `facodi_learning/views/slide_slide_views.xml`, `facodi_learning/views/analysis_views.xml`, `facodi_learning/views/res_config_settings_views.xml`.

**Interfaces:** Reuse `website_slides.group_website_slides_officer` and `website_slides.group_website_slides_manager`; extend `website_slides.view_slide_slide_form` by inheritance; expose provider/batch size through `res.config.settings`.

- [ ] Add record rules that mirror standard eLearning ownership: Officers see/manage analysis for content in their own courses; Managers see all.
- [ ] Add inherited slide form tab/buttons, job/result/mapping actions and menus under the existing eLearning configuration hierarchy where stable.
- [ ] Add a standard scheduled action calling `_cron_process_pending_jobs()`.
- [ ] Verify module install and tests on a clean database.

### Task 5: Repository documentation and release hygiene

**Files:** `README.md`, `docs/architecture.md`, `.gitignore`, `LICENSE`.

**Interfaces:** Document the module contract expected by `facodi-monorepo`, configuration keys, extension hook for future providers and test command.

- [ ] Document that `slide.slide`/`slide.tag` remain canonical Odoo records.
- [ ] Document provider extension by inheriting the analysis job model and extending `_get_provider_registry()`.
- [ ] Document CI and clean-install verification.
- [ ] Run final CI and review the branch diff for unnecessary custom models or duplicated Odoo behavior.
