# Contextual Submission Forms Design

## Purpose

Improve FACODI contribution and contact flows so users who click a CTA from a roadmap, curricular unit, related-course card, footer, or community block arrive at a richer form that is already contextualized by the page and CTA that sent them there.

## Current State

`facodi_learning` already contains a public resource-submission flow at `/contribuir/recurso`, a `facodi.learning.submission` model, a public controller, templates, dashboard pages, and a frontend metadata asset. The module manifest already loads `views/website_submission.xml` and `static/src/js/resource_submission.js`.

The existing model is resource-focused. It stores title, source URL, context, language, curricular-unit context, contributor, editorial state, token, review audit fields, and downstream source/candidate/analysis links.

The visible problem is not absence of a submission mechanism; it is that the form and CTA contract are too narrow. CTAs do not consistently pass source context, the form does not expose the context clearly enough, and the same public entry point does not yet support contact/correction/question variants.

## Goals

1. Keep the current standard-first Odoo implementation and extend it instead of replacing it.
2. Preserve `/contribuir/recurso` compatibility for existing links.
3. Add canonical multilingual contextual entry points:
   - `/pt/submissions/new`
   - `/en/submissions/new`
   - `/submissions/new`
4. Support submission types:
   - `resource`
   - `contact`
   - `correction`
   - `question`
5. Pre-fill form context from safe query parameters:
   - `type`
   - `curriculum_unit_id` and legacy `unit_id`
   - `roadmap_id`
   - `course_id`
   - `slide_id`
   - `source`
   - `section`
   - `source_url`
6. Show a visible context card so the user understands where the suggestion will be attached.
7. Keep questions directed to the forum when appropriate, but allow the form to capture a question-style submission when the CTA needs a structured intake.
8. Do not grant academic credits, equivalences, enrolment, or institutional recognition from a submission.
9. Keep all editorial decisions human-reviewed.

## Non-goals

1. Do not implement Supabase analysis in this change.
2. Do not auto-publish accepted submissions.
3. Do not replace Odoo Website forms globally.
4. Do not require authentication for public submission.
5. Do not store passwords, private links, or credentials.

## Data Model

Extend `facodi.learning.submission` instead of introducing a parallel model.

New or widened fields:

- `submission_type`: selection with values `resource`, `contact`, `correction`, `question`; default `resource`.
- `source_cta`: char, sanitized technical source of the CTA, e.g. `unit_resource_cta`, `community_margin`, `footer_contact`.
- `source_section`: char, sanitized section label, e.g. `resources`, `community_margin`, `footer`.
- `source_page_url`: char, HTTP path or URL of the origin page when available.
- `roadmap_id`: optional `facodi.learning.curriculum.reference` relation.
- `course_id`: optional `slide.channel` relation.
- `slide_id`: existing related field already points to canonical source slide; do not reuse it for raw user context. If raw context is needed, add `suggested_slide_id` instead.
- `contact_name`: char.
- `contact_email`: char.
- `organization`: char.
- `resource_type`: selection or char with `video`, `article`, `book`, `tool`, `repository`, `course`, `other`.
- `resource_level`: selection or char with `introductory`, `intermediate`, `advanced`, `unknown`.
- `permission_to_contact`: boolean.

Existing `name`, `source_url`, `context`, `language`, and `curriculum_unit_id` remain valid.

## Controller Contract

The controller must normalize both old and new parameters:

- `type` becomes `submission_type`; unsupported values fallback to `resource`.
- `unit_id` and `curriculum_unit_id` both resolve through the existing `_public_curriculum_unit` guard.
- `source` becomes `source_cta`, restricted to short slug-like values.
- `section` becomes `source_section`, restricted to short slug-like values.
- `source_page_url` should default to HTTP referrer only when it is internal/public-safe; explicit submitted values must be trimmed and not trusted for redirects.

GET should render the same template with contextual values.

POST should validate by type:

- `resource`: source URL required and must be public HTTP/HTTPS.
- `contact`: email and message/context required; source URL optional.
- `correction`: message/context required; source URL optional.
- `question`: message/context required; source URL optional.

Duplicate URL checks apply only to `resource` submissions.

## UX Contract

The public form should use three sections:

1. Context
   - Shows type label.
   - Shows curricular unit if available.
   - Shows roadmap/course/source section when available.
   - Shows CTA/source chip when available.
2. Submission details
   - Fields adapt to the selected `submission_type`.
   - Resource submissions keep title, URL, language, type, level and usefulness/context.
   - Contact/correction/question submissions emphasize subject/message and contact data.
3. Follow-up
   - Name, email, organization, permission to contact.
   - A short explanation of human review and non-credit provenance.

## CTA Contract

All FACODI CTAs that invite contribution should use query parameters instead of generic links.

Examples:

- Unit resource CTA:
  `/pt/submissions/new?type=resource&unit_id=<id>&roadmap_id=<id>&source=unit_resource_cta&section=resources`
- Community margin resource CTA:
  `/pt/submissions/new?type=resource&unit_id=<id>&source=community_margin&section=community_margin`
- Correction CTA:
  `/pt/submissions/new?type=correction&unit_id=<id>&source=unit_correction_cta&section=provenance`
- Footer contact CTA:
  `/pt/submissions/new?type=contact&source=footer_contact&section=footer`

## Admin Contract

Admin/list/form views should expose the new context fields so editorial reviewers can triage submissions by type, source CTA, section, and associated curricular context.

## Testing Contract

Tests must prove:

1. New route renders a resource form with context for `unit_id`.
2. Legacy `/contribuir/recurso?curriculum_unit_id=<id>` still works.
3. Unsupported `type` safely falls back to `resource`.
4. Contact submissions can be created without `source_url` but require contact/message fields.
5. Resource duplicate detection still applies only to resource submissions.
6. Malicious or private URLs remain rejected for resource submissions.
7. Template contains hidden context fields and visible context card copy.
8. Curriculum CTA templates include contextual parameters.

## Deployment Notes

This change is code-only in `facodi-learning`. After deploy, update the Odoo module and clear website/assets cache if necessary. Existing submissions must remain readable; new fields should be nullable and default-safe.