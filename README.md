# FACODI Learning

`facodi_learning` extends Odoo 19 Community `website_slides` with auditable
course discovery, content ingestion and educational enrichment. It works
independently of any theme.

## Standard Odoo remains authoritative

Courses (`slide.channel`), content (`slide.slide`), tags (`slide.tag`), membership,
publication, progress, quizzes, comments, Portal and eLearning Officer/Manager
roles are reused. There is no FACODI LMS, parallel course model or pathway model.
FACODI course candidates are temporary/audit records; every approved new course
becomes one standard `slide.channel`.

## Course Discovery — M3.1

In **eLearning → FACODI Learning → Course Discovery → Candidates**, Officers and
Managers can register course candidates using a stable `(provider, external_id)`
identity. Unresolved source metadata can be refreshed, while identity and terminal
decision evidence are immutable. Public and Portal users have no access to these
records; Officers can work only on candidates they requested, while terminal
resolution is Manager-only.

`action_evaluate()` uses the deterministic local evaluator. It requires no network
or external AI provider and stores relevance, metadata quality, language fit,
coverage baseline, duplicate risk, recommendation, reasons and evaluator version.
Title matching is normalized and deterministic. A likely existing-course match is
a review signal only: M3.1 never silently auto-links a semantic duplicate.

Course selection is configured in eLearning settings with three modes:

- **Manual** evaluates candidates but never shortlists or resolves automatically.
- **Assisted** can shortlist review-worthy candidates but never resolves them.
- **Auto Approve** is fail-closed: the provider must be trusted, all configured
  score thresholds must pass, duplicate risk must stay below its maximum and the
  recommendation must be eligible. Automatic resolution runs only in an authorized
  eLearning Manager/superuser context and always creates a new draft course.

Managers can also resolve a candidate manually by linking a selected existing
`slide.channel` or by creating exactly one new draft `slide.channel`. Both manual
and automatic decisions share the same locked, idempotent `_resolve()` path and
store a decision snapshot with the scores, evaluator version and selection policy
that were effective at decision time. Later setting changes do not rewrite that
history.

**Auto Approve never publishes a course.** Every new course created by M3.1 is
explicitly `website_published=False`; normal Odoo editorial review/publication
remains authoritative.

M3.1 intentionally does not implement external discovery providers, semantic/AI
ranking, curriculum coverage models or learner progression/credit recognition.
Those remain separate follow-on milestones.

## Course Profile — M3.2

Every canonical `slide.channel` can expose a deterministic internal profile through
`channel._facodi_course_profile()`. The profile is computed on demand as
`course-profile-v1`; M3.2 creates no profile table and persists no duplicate course
state.

The profile aggregates only existing canonical/evidence data:

```text
slide.channel
  -> standard course metadata and descriptions
  -> standard course tags/groups
  -> native prerequisite channels
  -> sections, compact content metadata, types and duration
  -> standard content tags
  -> latest safe detected-language evidence from analysis results
  -> approved content-relation aggregates grouped by counterpart course/type
```

The builder is deterministic for the same readable database state and performs no
writes, privilege elevation, network call or AI request. It deliberately excludes
learner/member/progress data, generated summaries, transcripts and raw provider
payloads. Both published and unpublished content remain visible to this internal
profile because M3.2 describes the current canonical editorial course; learner-
facing visibility remains governed by normal Odoo access/publication rules.

M3.2 is internal infrastructure for later course retrieval/mapping. It does not add
course-mapping semantics, curriculum coverage, external discovery providers,
embeddings or learner-facing UI.

## Content analysis pipeline

Source → unpublished standard content → queued analysis → historical result →
Manager review → standard tags and approved educational links.

Six small audit/provenance models cover course candidates, source provenance,
analysis requests, immutable processing attempts, immutable normalized results and
reviewed relationships. The transcript on the standard content record remains
editorial; generated transcripts remain in results. No automatic result overwrites
content or publishes a lesson.

## Install and upgrade

Put this repository on `addons_path`, then run:

```bash
odoo -d facodi -i facodi_learning --without-demo=True --stop-after-init
odoo -d facodi -u facodi_learning --stop-after-init
```

Back up the database and matching filestore for an existing deployment. Changes in
19.0.1.3.0 are additive and M3.2 introduces no persistent profile schema, so no
data rewrite or migration is required. Existing sources, jobs, attempts, results,
mappings, candidates and standard eLearning content remain intact. Older audit
history is not retroactively fabricated.

## Manager workflow

In **eLearning → FACODI Learning → Content Analysis**, manage Jobs, Results and
Mappings using the existing actions. Sources remain the provenance entry point for
content ingestion. Create a source with provider `manual`, a stable external
identifier and course; **Import unpublished article** creates one draft article.
Replaying ingestion reuses it, including any editorial changes. The Python
`ingest_manual` method can associate existing content in the same course. Imported
provenance is immutable.

On an eLearning content form, **FACODI Analysis → Queue Analysis** creates a
request. The default `local_metadata` provider uses Odoo data only, without
network access. The standard scheduled action processes a capped batch. Managers
can also process jobs; Officers can request/retry jobs in courses they own.

Managers apply or reject tag suggestions explicitly. Applying reuses standard tags
and records who reviewed them and when; rejecting changes no content. Mappings
are proposed first and reviewed separately. Direct ORM writes cannot bypass review.
Reviewed output is immutable; create a new analysis or relation when meaning changes.

Students see only approved resource links on the standard lesson detail page.
Publication, current website, native visibility and access rules filter targets.
Technical fields and all FACODI audit models remain unavailable to Public/Portal
users. The standard fullscreen training player remains unchanged.

## Provider extensions

Trusted optional addons extend `_get_provider_registry()` on analysis jobs, or
`_get_ingestion_registry()` on sources, calling `super()` in both cases.
Analysis adapters receive a `slide.slide`; ingestion adapters receive a source
and return standard content values. `ingest(values, slide_id=None)` registers by
provider/external identifier/course and forces new content to remain unpublished.

Course Discovery M3.1 itself has no external discovery adapter. Provider-specific
course discovery belongs to a later optional-addon milestone; the core candidate
evaluator and policy remain deterministic and offline.

See [architecture](docs/architecture.md) for normalized output, course-selection,
course-profile and transaction contracts. Runtime secrets belong in an adapter's
deployment environment, never source records or payloads. No external provider SDK
is a core dependency.

## Tests

GitHub Actions installs and upgrades against Odoo 19 + PostgreSQL 16, with a
persistent filestore between runs. Run `--test-tags /facodi_learning` to cover
candidate identity/evaluation/modes/resolution, course-profile schema and
determinism, safe analysis/relation aggregation, privacy/non-mutation boundaries,
request/retry/error isolation, immutable history, provider output, source replay,
Manager review, ACLs, batch processing and safe learner links. Tests explicitly
assert that both automatic and manual new-course resolution leave the canonical
course unpublished.

The monorepo consumes this repository as a pinned submodule; addon changes do not
deploy until the consuming repository intentionally updates its pin.

LGPL-3.0.

## Validation evidence

See [validation report](docs/validation.md) for the isolated Community install/upgrade matrix, browser checks and remaining deployment boundaries.
