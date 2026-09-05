# FACODI Learning finalization plan

Goal: Complete the existing standard-first enrichment pipeline on Odoo 19 Community.
Architecture: slide.channel, slide.slide and slide.tag remain canonical. Keep analysis job/result/mapping; add only a provenance source record for idempotent ingestion. External adapters remain optional.
Spec: user execution briefing, 2026-09-05; this supersedes incomplete baseline plans.

## Task 1: Secure and audit the existing pipeline
- [x] Add regression tests for direct ORM review bypass, immutable historical output, forged requester, public/portal denial and cross-owner mutation.
- [x] Enforce transitions in Python including create/write, preserve explicit Manager review with timestamps, preserve results and failure evidence; never trust client context flags as authorization.
- [x] Lock jobs with native Odoo/PostgreSQL row locking, process bounded batches with savepoints and native cron progress; retry safely without overwriting attempt evidence. Document transactional crash recovery.
- [x] Normalize provider output including transcript, tags and proposed relationships with provenance; never publish/apply automatically. Test errors and multiple jobs.

## Task 2: Minimal idempotent ingestion and usable review
- [x] Add source registry record with provider, external identifier, URL, course/content, timestamps, state, error and metadata; unique provider identity scoped to target course.
- [x] Default local/manual adapter associates existing slide or creates unpublished article through ORM, replays reuse it without overwriting editorial changes. No arbitrary URL fetch in core.
- [x] Integrate sources and result/tag/mapping review in standard eLearning menus/views. Keep student technical metadata private.
- [x] Test idempotency, ACL, validation, rollback and ownership; document extension contract and pipeline.

## Task 3: Portability and validation
- [x] Run module tests using disposable Docker Odoo 19 + PostgreSQL 16; reproduce regressions before fixes.
- [x] Add CI upgrade run and preserve existing editorial/history data. Use additive schema; version bump and migration only where required.
- [x] Update README/architecture to actual code; archive superseded design docs clearly.
- [x] Review diff and commit coherent chunks. Integration, browser and external AI smoke are recorded in docs/validation.md. PR/CI status is recorded on GitHub.
