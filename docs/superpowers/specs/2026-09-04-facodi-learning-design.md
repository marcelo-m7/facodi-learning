# FACODI Learning — Design

Date: 2026-09-04
Target: Odoo 19 Community
Repository: `marcelo-m7/facodi-learning`

## Purpose

`facodi-learning` is the functional Odoo addon responsible for video ingestion, analysis, enrichment and educational mapping for FACODI. It must extend Odoo's standard eLearning models instead of recreating a separate LMS.

The addon must remain independent from FACODI branding. It may be installed without `facodi-theme`.

## Architectural principles

1. Prefer standard Odoo models and services before creating FACODI-specific ones.
2. Treat `website_slides` as the operational learning-content layer.
3. Extend `slide.slide` for analysable content instead of duplicating videos as a second canonical content model.
4. Keep external AI/video-analysis providers behind a service interface so provider choice can change without changing the domain model.
5. Persist analysis state and results in Odoo so jobs are auditable and retryable.
6. Do not require a third-party queue framework in the first version; scheduled processing uses standard `ir.cron` and explicit job records.
7. Do not store API secrets in source code or normal business records. Provider credentials must be obtained from deployment/runtime configuration.
8. All migrations must be additive and versioned under the standard Odoo module migration structure.

## Odoo module

Technical module name:

`facodi_learning`

Initial dependencies:

- `base`
- `mail`
- `website`
- `website_slides`

The module must not depend on `facodi_theme`.

## Domain model

### `slide.slide` extension

The standard eLearning content record remains the canonical educational content object. The addon adds analysis-oriented fields only, including:

- analysis state
- last analysis timestamp
- detected language
- machine-generated summary
- normalized keywords/topics
- provider/model provenance
- confidence/quality metadata

Provider-specific raw payloads must not be mixed into the main model; they belong to analysis result records.

### `facodi.learning.analysis.job`

Auditable processing request for one `slide.slide`.

Lifecycle:

`pending -> processing -> completed`

Failure lifecycle:

`pending/processing -> failed -> pending` on retry.

Core responsibilities:

- identify source content
- record requested operation
- record timestamps and attempts
- capture human-readable error information
- retain provider/model metadata used for the run

### `facodi.learning.analysis.result`

Immutable-or-append-oriented result record linked to a job and source slide. It stores normalized output plus optional raw provider response metadata.

Normalized output includes:

- summary
- topics
- keywords
- learning concepts
- detected language
- confidence values when supplied

A new analysis run creates a new result rather than silently overwriting historical analysis.

### `facodi.learning.topic`

Reusable normalized topic vocabulary for analysis and mapping. Topics may be linked to multiple slides.

### `facodi.learning.mapping`

Represents a proposed or approved educational relationship between a source learning item and a target learning context.

The first implementation supports mappings between standard Odoo eLearning records and leaves extension points for future curriculum-domain addons.

Mapping states:

- `proposed`
- `approved`
- `rejected`

Each mapping records:

- source content
- target content/context
- mapping type
- score/confidence
- origin (`manual` or `analysis`)
- analysis result provenance where applicable
- reviewer and review timestamp

Automated analysis may propose mappings but must not silently mark them approved.

## Service layer

Provider integration lives under a dedicated service package rather than model methods containing vendor-specific HTTP logic.

Conceptual interface:

- obtain source metadata/transcript
- normalize input
- analyse content
- normalize provider response
- create result
- derive mapping proposals

The domain layer consumes normalized dictionaries/data objects. Vendor-specific request/response shapes must remain isolated in adapters.

## Processing flow

1. User creates or selects an eLearning content record.
2. User requests analysis, or an eligible scheduled policy creates a job.
3. A job is persisted as `pending`.
4. Standard scheduled processing claims a bounded number of pending jobs.
5. Job moves to `processing`.
6. Service adapter obtains analysable text/metadata and runs the configured analysis provider.
7. Normalized result is persisted.
8. Mapping proposals are created when applicable.
9. Job becomes `completed`.
10. Any exception records a sanitized error and moves the job to `failed` without deleting prior results.

## User interface

The addon adds a FACODI analysis section to standard eLearning content forms rather than replacing Odoo eLearning screens.

Initial UI provides:

- current analysis status
- request analysis action
- retry failed analysis action
- latest normalized result
- historical results
- proposed/approved mappings
- manual approve/reject actions for proposals

A lightweight FACODI Learning menu may expose jobs and analysis administration to authorized internal users.

## Security

Security groups:

- Learning User: read analysis results and proposals on content they may access through standard Odoo rules.
- Learning Curator: request/retry analysis and approve/reject mappings.
- Learning Administrator: configure functional settings and inspect all jobs/results.

Standard Odoo access rules remain authoritative for the underlying eLearning records.

## Failure handling

- External-provider failures never delete or corrupt `slide.slide`.
- Jobs retain attempt count and last sanitized error.
- Retries create a new processing attempt while preserving analysis history.
- Provider timeouts and malformed responses are treated as job failures, not transaction-wide content failures.
- Automated mappings stay proposed until human approval.

## Testing

The repository must contain automated Odoo tests covering at minimum:

- module installation on a clean Odoo 19 database
- job lifecycle transitions
- successful normalized analysis using a fake provider
- provider failure and retry
- historical result preservation
- mapping proposal creation
- mapping approval/rejection permissions
- no dependency on `facodi_theme`

CI must install the module against Odoo 19 and run the module tests without real network/API credentials.

## Repository structure

```text
facodi-learning/
├── facodi_learning/
│   ├── __init__.py
│   ├── __manifest__.py
│   ├── models/
│   ├── services/
│   ├── security/
│   ├── views/
│   ├── data/
│   ├── migrations/
│   └── tests/
├── .github/workflows/
│   └── ci.yml
├── docs/
│   └── architecture.md
├── .gitignore
├── LICENSE
└── README.md
```

## Public contract with `facodi-monorepo`

The repository root contains exactly one installable Odoo addon directory named `facodi_learning` plus repository-level documentation/CI files.

`facodi-monorepo` consumes this repository as a Git submodule under:

`addons/facodi-learning`

The monorepo pins an exact commit. Updating `facodi-learning` does not deploy anything until the monorepo submodule pointer is intentionally updated and its image pipeline passes.

## Out of scope for the initial repository

- FACODI branding/theme implementation
- replacement of standard Odoo eLearning course/content models
- direct production deployment logic
- hard-coded AI vendor selection
- automatic approval of curriculum mappings
- third-party queue framework requirement

These exclusions keep the addon independently installable, testable and compatible with the monorepo image-build model.
