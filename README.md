# FACODI Learning

`facodi_learning` extends Odoo 19 Community `website_slides` with auditable
content ingestion and educational enrichment. It works independently of any theme.

## Standard Odoo remains authoritative

Courses (`slide.channel`), content (`slide.slide`), tags (`slide.tag`), membership,
publication, progress, quizzes, comments, Portal and eLearning Officer/Manager
roles are reused. There is no FACODI LMS or pathway model.

## Pipeline

Source → unpublished standard content → queued analysis → historical result →
Manager review → standard tags and approved educational links.

Five small audit models cover provenance, requests, immutable processing attempts,
immutable normalized results and reviewed relationships. The transcript on the
standard content record remains editorial; generated transcripts remain in results.
No automatic result overwrites content or publishes a lesson.

## Install and upgrade

Put this repository on `addons_path`, then run:

```bash
odoo -d facodi -i facodi_learning --without-demo=True --stop-after-init
odoo -d facodi -u facodi_learning --stop-after-init
```

Back up the database and matching filestore for an existing deployment. Schema
changes in 19.0.1.1.0 are additive except audit foreign keys becoming restrictive;
no data rewrite or post-init migration is required. Old results and reviewed
mappings remain intact. Old retries retain their existing counter/error; the new
attempt history starts with the next execution and is not fabricated retroactively.

## Manager workflow

In **eLearning → FACODI Analysis**, manage Sources, Jobs, Results and Mappings.
Create a source with provider `manual`, a stable external identifier and course;
**Import unpublished article** creates one draft article. Replaying ingestion
reuses it, including any editorial changes. The Python `ingest_manual` method
can associate existing content in the same course. Imported provenance is immutable.

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
Technical fields and all audit models remain unavailable to Public/Portal users.
The standard fullscreen training player remains unchanged.

## Provider extensions

Trusted optional addons extend `_get_provider_registry()` on analysis jobs, or
`_get_ingestion_registry()` on sources, calling `super()` in both cases.
Analysis adapters receive a `slide.slide`; ingestion adapters receive a source
and return standard content values. `ingest(values, slide_id=None)` registers by
provider/external identifier/course and forces new content to remain unpublished.

See [architecture](docs/architecture.md) for normalized output and transaction
contracts. Runtime secrets belong in the adapter's deployment environment, never
source records or payloads. No external provider SDK is a core dependency.

## Tests

GitHub Actions installs and upgrades against Odoo 19 + PostgreSQL 16, with a
persistent filestore between runs. Run `--test-tags /facodi_learning` to cover
request/retry/error isolation, immutable history, provider output, source replay,
Manager review, ACLs, batch processing and safe learner links.

The monorepo consumes this repository as a pinned submodule; addon changes do not
deploy until the consuming repository intentionally updates its pin.

LGPL-3.0.

## Validation evidence

See [validation report](docs/validation.md) for the isolated Community install/upgrade matrix, browser checks and remaining deployment boundaries.
