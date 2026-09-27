# Contextual Submission Forms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing FACODI resource-submission flow into a contextual, type-aware submission and contact intake that pre-fills from CTA context.

**Architecture:** Reuse the existing `facodi.learning.submission` model, controller, templates and metadata JavaScript. Add nullable context/type fields, route aliases for `/submissions/new`, type-specific validation, richer form sections, and contextual CTA links from curriculum pages.

**Tech Stack:** Odoo 19 Community, Python Odoo ORM/controllers, QWeb XML templates, website/eLearning, existing FACODI frontend JavaScript.

**Spec:** `docs/superpowers/specs/2026-09-27-contextual-submissions-design.md`

## Global Constraints

- Preserve `/contribuir/recurso` compatibility for existing links.
- Do not auto-publish accepted submissions.
- Do not implement Supabase analysis in this change.
- Do not require authentication for public submission.
- Do not store passwords, private links, credentials or private URLs.
- Keep editorial decisions human-reviewed.
- Preserve standard-first Odoo Website/eLearning behavior.

## Review Focus

- Malicious resource URLs: private/loopback/credentialed URLs must still be rejected by `_is_valid_source_url` tests in Task 1.
- Unsupported `type`: must safely fall back to `resource`, tested in Task 2.
- Legacy links: `/contribuir/recurso?curriculum_unit_id=<id>` must still render the resource form, tested in Task 2.
- Contact/correction/question submissions without URL: must not run resource duplicate checks, tested in Task 3.
- Context spoofing: invalid unit/roadmap/course IDs must not create trusted relations, tested in Task 2 and Task 3.

---

## File Structure

- Modify `facodi_learning/models/submission.py`: add type/context/contact/resource metadata fields, field helpers and type validation helpers.
- Modify `facodi_learning/controllers/submission.py`: normalize query parameters, add route aliases, type-specific GET/POST handling and safe context extraction.
- Modify `facodi_learning/views/website_submission.xml`: replace the one-purpose form body with a context-aware form that adapts by type while preserving existing metadata discovery hooks.
- Modify `facodi_learning/views/submission_views.xml`: expose type/context fields in backend editorial views.
- Modify `facodi_learning/views/website_curriculum.xml`: update contribution CTAs to pass `type`, `unit_id`, `roadmap_id`, `source` and `section` where context exists.
- Modify `facodi_learning/security/ir.model.access.csv` only if new helper model is introduced; expected no change because this plan reuses the existing model.
- Modify or add tests under `facodi_learning/tests/`: controller/model/template contract tests for the new flow.
- Optionally modify `facodi_learning/static/src/js/resource_submission.js`: keep discovery scoped to resource forms only.

---

### Task 1: Extend Submission Model Fields and Helpers

**Files:**
- Modify: `facodi_learning/models/submission.py`
- Test: `facodi_learning/tests/test_submission_context_model.py`

**Interfaces:**
- Produces: `submission_type`, `source_cta`, `source_section`, `source_page_url`, `roadmap_id`, `course_id`, `suggested_slide_id`, `contact_name`, `contact_email`, `organization`, `resource_type`, `resource_level`, `permission_to_contact` fields.
- Produces: `_normalize_submission_type(value: str) -> str` returning one of `resource`, `contact`, `correction`, `question`.
- Produces: `_is_valid_context_slug(value: str) -> bool` for CTA/section slugs.
- Consumes: existing `_is_valid_source_url(value)` and `_normalize_source_url(value)`.

- [ ] **Step 1: Write failing model tests**

Add tests proving:

```python
def test_normalize_submission_type_falls_back_to_resource(self): ...
def test_context_slug_rejects_long_or_unsafe_values(self): ...
def test_resource_url_validation_still_rejects_private_urls(self): ...
def test_new_fields_exist_on_submission_model(self): ...
```

- [ ] **Step 2: Run tests to verify failure**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i facodi_learning --test-tags /facodi_learning:post_install`

Expected: FAIL because fields/helpers do not exist yet.

- [ ] **Step 3: Implement fields and helpers in `facodi_learning/models/submission.py`**

Add nullable fields and helpers. Keep defaults safe: `submission_type` defaults to `resource`, `permission_to_contact` defaults to `False`, all relations use `ondelete="set null"` and should be optional.

- [ ] **Step 4: Run model tests to verify pass**

Run the same Odoo test command.

Expected: PASS for Task 1 tests.

- [ ] **Step 5: Commit**

```bash
git add facodi_learning/models/submission.py facodi_learning/tests/test_submission_context_model.py
git commit -m "feat: add contextual submission fields"
```

---

### Task 2: Add Context-Aware GET Routes

**Files:**
- Modify: `facodi_learning/controllers/submission.py`
- Test: `facodi_learning/tests/test_website_submission_context.py`

**Interfaces:**
- Consumes Task 1 helpers.
- Produces: `_submission_context_from_kwargs(kwargs: dict) -> dict` with sanitized `form_values`, `curriculum_unit`, optional `roadmap`, optional `course`, optional `suggested_slide`, `submission_type`, `source_cta`, `source_section`, and `source_page_url`.
- Extends existing `resource_submission_form` to serve `/contribuir/recurso`, `/submissions/new`, `/pt/submissions/new`, `/en/submissions/new`.

- [ ] **Step 1: Write failing controller tests**

Add tests proving:

```python
def test_new_submissions_route_prefills_unit_context(self): ...
def test_legacy_resource_route_still_prefills_curriculum_unit(self): ...
def test_unit_id_alias_matches_curriculum_unit_id(self): ...
def test_unsupported_type_falls_back_to_resource(self): ...
def test_invalid_unit_id_is_not_trusted(self): ...
```

- [ ] **Step 2: Run tests to verify failure**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i facodi_learning --test-tags /facodi_learning:post_install`

Expected: FAIL because new routes/context helper do not exist.

- [ ] **Step 3: Implement route aliases and context extraction**

Update the GET route decorator to include the new URLs. Use `_public_curriculum_unit` for `unit_id` and `curriculum_unit_id`. Resolve `roadmap_id`, `course_id`, and `slide_id` only if the record exists and is safe to expose publicly; otherwise leave relation values empty.

- [ ] **Step 4: Run controller tests to verify pass**

Run the same Odoo test command.

Expected: PASS for Task 2 tests.

- [ ] **Step 5: Commit**

```bash
git add facodi_learning/controllers/submission.py facodi_learning/tests/test_website_submission_context.py
git commit -m "feat: add contextual submission routes"
```

---

### Task 3: Implement Type-Specific POST Validation and Creation

**Files:**
- Modify: `facodi_learning/controllers/submission.py`
- Test: `facodi_learning/tests/test_website_submission_create.py`

**Interfaces:**
- Consumes Task 1 helpers and Task 2 context extraction.
- Produces: POST handling for `resource`, `contact`, `correction`, `question`.
- Keeps existing status redirect `/contribuir/recurso/status/<token>`.

- [ ] **Step 1: Write failing create tests**

Add tests proving:

```python
def test_resource_submission_requires_public_url(self): ...
def test_contact_submission_requires_email_and_message_not_url(self): ...
def test_correction_submission_requires_message_not_url(self): ...
def test_question_submission_requires_message_not_url(self): ...
def test_resource_duplicate_detection_does_not_block_contact(self): ...
def test_context_fields_are_stored_on_created_submission(self): ...
```

- [ ] **Step 2: Run tests to verify failure**

Run the Odoo test command.

Expected: FAIL because POST logic is resource-only.

- [ ] **Step 3: Implement type-specific validation**

Branch validation by `submission_type`. Only resource submissions require and normalize `source_url`, run YouTube enrichment and duplicate detection. Contact/correction/question submissions must accept empty `source_url` and store user message in `context`.

- [ ] **Step 4: Run create tests to verify pass**

Run the Odoo test command.

Expected: PASS for Task 3 tests.

- [ ] **Step 5: Commit**

```bash
git add facodi_learning/controllers/submission.py facodi_learning/tests/test_website_submission_create.py
git commit -m "feat: support typed public submissions"
```

---

### Task 4: Redesign Public Submission Template

**Files:**
- Modify: `facodi_learning/views/website_submission.xml`
- Optionally modify: `facodi_learning/static/src/js/resource_submission.js`
- Test: `facodi_learning/tests/test_website_submission_template_contract.py`

**Interfaces:**
- Consumes `form_values`, `submission_type`, `curriculum_unit`, `roadmap`, `course`, `suggested_slide`, `source_cta`, `source_section`, `errors`, `duplicate` from controller context.
- Produces visible context card, hidden context fields, type-aware field groups and resource-only metadata discovery hooks.

- [ ] **Step 1: Write failing template contract tests**

Add tests proving rendered HTML contains:

```python
assert 'data-facodi-submission-form="1"' in html
assert 'name="submission_type"' in html
assert 'name="source_cta"' in html
assert 'name="source_section"' in html
assert 'You are contributing in this context' in html
assert 'data-facodi-resource-submission="1"' in html  # only when type=resource
```

- [ ] **Step 2: Run tests to verify failure**

Run the Odoo test command.

Expected: FAIL because current template is resource-only.

- [ ] **Step 3: Update `website_submission.xml`**

Refactor the form into three visual sections: context, submission details, follow-up. Keep current YouTube metadata UI inside a resource-only block. Add type-specific headings and explanatory copy.

- [ ] **Step 4: Guard metadata JavaScript**

If current JS assumes resource fields always exist, update it to return early unless `data-facodi-resource-submission="1"` and the URL field exist.

- [ ] **Step 5: Run template tests to verify pass**

Run the Odoo test command.

Expected: PASS for Task 4 tests.

- [ ] **Step 6: Commit**

```bash
git add facodi_learning/views/website_submission.xml facodi_learning/static/src/js/resource_submission.js facodi_learning/tests/test_website_submission_template_contract.py
git commit -m "feat: redesign contextual submission form"
```

---

### Task 5: Update Curriculum CTAs

**Files:**
- Modify: `facodi_learning/views/website_curriculum.xml`
- Test: `facodi_learning/tests/test_website_curriculum_cta_contract.py`

**Interfaces:**
- Consumes the route/query contract from Tasks 2-4.
- Produces contextual CTA URLs from roadmap/unit templates.

- [ ] **Step 1: Write failing CTA contract tests**

Add tests proving relevant templates contain:

```python
assert '/submissions/new?type=resource' in template or '/pt/submissions/new?type=resource' in template
assert 'unit_id=' in template
assert 'source=unit_resource_cta' in template
assert 'section=resources' in template
assert 'source=community_margin' in template
```

- [ ] **Step 2: Run tests to verify failure**

Run the Odoo test command.

Expected: FAIL because current CTAs still use `/contribuir/recurso?curriculum_unit_id=...` or generic `/contribuir/recurso`.

- [ ] **Step 3: Update QWeb CTA URLs**

Replace generic contribution links with contextual submission URLs wherever template context has unit/roadmap data. Keep generic contribution URLs where no context exists.

- [ ] **Step 4: Run CTA tests to verify pass**

Run the Odoo test command.

Expected: PASS for Task 5 tests.

- [ ] **Step 5: Commit**

```bash
git add facodi_learning/views/website_curriculum.xml facodi_learning/tests/test_website_curriculum_cta_contract.py
git commit -m "feat: pass context from curriculum CTAs"
```

---

### Task 6: Expose Context in Backend Editorial Views

**Files:**
- Modify: `facodi_learning/views/submission_views.xml`
- Test: `facodi_learning/tests/test_submission_admin_views.py`

**Interfaces:**
- Consumes Task 1 fields.
- Produces backend list/form/search visibility for type and context fields.

- [ ] **Step 1: Write failing admin-view test**

Add tests proving the view architecture includes:

```python
assert 'submission_type' in arch
assert 'source_cta' in arch
assert 'source_section' in arch
assert 'contact_email' in arch
```

- [ ] **Step 2: Run tests to verify failure**

Run the Odoo test command.

Expected: FAIL until views expose fields.

- [ ] **Step 3: Update backend views**

Add the fields to list/form/search views without changing existing menu/action IDs.

- [ ] **Step 4: Run admin-view tests to verify pass**

Run the Odoo test command.

Expected: PASS for Task 6 tests.

- [ ] **Step 5: Commit**

```bash
git add facodi_learning/views/submission_views.xml facodi_learning/tests/test_submission_admin_views.py
git commit -m "feat: show submission context in editorial views"
```

---

### Task 7: Full Verification and Deployment Notes

**Files:**
- Modify: `README.md` or `docs/` only if existing project docs have a contribution-flow section.

**Interfaces:**
- Consumes all previous tasks.
- Produces final verification evidence and deployment instructions.

- [ ] **Step 1: Run full module tests**

Run:

```bash
odoo-bin -d <test_db> --test-enable --stop-after-init -i facodi_learning --test-tags /facodi_learning:post_install
```

Expected: PASS.

- [ ] **Step 2: Run static contract checks if present**

Run any repository scripts under `scripts/` or CI commands already documented in the repo.

Expected: PASS.

- [ ] **Step 3: Manually verify public pages in a local/dev Odoo**

Verify:

- `/contribuir/recurso` still works.
- `/pt/submissions/new?type=resource&unit_id=<public_unit_id>&source=unit_resource_cta&section=resources` shows context.
- `/pt/submissions/new?type=contact&source=footer_contact&section=footer` does not require URL.
- Resource submission status link still works.

- [ ] **Step 4: Commit documentation if needed**

```bash
git add README.md docs/
git commit -m "docs: document contextual submissions" || true
```

---

## Self-Review

- Spec coverage: all spec goals map to Tasks 1-7. Supabase and auto-publication are explicitly excluded.
- Step scan: each task has a failing test, implementation step, verification step and commit step.
- Type consistency: `submission_type`, `source_cta`, `source_section`, `source_page_url`, `roadmap_id`, `course_id`, `suggested_slide_id`, `contact_*`, `resource_*` are consistent across tasks.
- Review Focus: the five listed risks are assigned to Tasks 1-3.
- Proportion: the plan is longer than the spec because it documents tests and exact file ownership, but avoids implementation bodies.