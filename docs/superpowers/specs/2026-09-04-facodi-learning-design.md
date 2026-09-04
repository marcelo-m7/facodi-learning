# FACODI Learning — Design

Date: 2026-09-04
Target: Odoo 19 Community
Repository: `marcelo-m7/facodi-learning`
Technical addon: `facodi_learning`

## Purpose

FACODI Learning extends Odoo's standard eLearning application with analysis and educational mapping while keeping Odoo records authoritative. It is independently installable and has no dependency on FACODI branding.

## Standard-first decisions

- `slide.channel` is the canonical course model.
- `slide.slide` is the canonical educational content model.
- `slide.tag` is reused instead of creating a FACODI topic/tag model.
- Standard eLearning Officer/Manager groups are reused instead of FACODI-specific access groups.
- Standard `res.config.settings`/`ir.config_parameter` configure functional analysis settings.
- Standard `ir.cron` processes bounded batches; no third-party queue is required by core.
- Standard eLearning views and menus are inherited/extended; the application is not replaced.

## FACODI-owned records

### `facodi.learning.analysis.job`
Auditable processing request for one `slide.slide`. States: `pending`, `processing`, `completed`, `failed`. It tracks provider, attempts, timestamps, requester, final result and a sanitized failure message.

### `facodi.learning.analysis.result`
Historical normalized output linked to a job and standard content. New analyses append records instead of overwriting prior results. Suggested topics are links to standard `slide.tag` records.

### `facodi.learning.mapping`
A proposed/approved/rejected relation between two standard `slide.slide` records. Automated analysis can propose mappings but only a standard eLearning Manager can approve or reject them.

## Provider interface

Provider-specific code is isolated behind `_get_provider_registry()`. Core ships only `local_metadata`, a deterministic no-network provider using Odoo-owned title/description/transcript/tags. Future provider addons extend the registry and return the same normalized shape; they do not alter core domain records.

## Processing flow

1. Officer queues analysis from a standard eLearning content form.
2. Job is persisted as `pending`.
3. `ir.cron` selects a bounded batch.
4. Job moves to `processing` and invokes the configured provider.
5. Normalized result is appended and job becomes `completed`.
6. Exceptions keep the Odoo content intact and move the job to `failed`.
7. Failed jobs can be returned to `pending` for retry.
8. Suggested tags or semantic mappings require explicit user actions before changing learning classification/review state.

## Security

Record rules mirror `website_slides`: Officers read broadly and mutate FACODI records only for content in courses they own; Managers administer all. Review transitions also check Manager membership in Python.

## Testing

CI uses the official `odoo:19.0` image with PostgreSQL 16 on a clean database. Tests cover installation plus analysis lifecycle, provider failure/retry, historical result preservation, standard-tag reuse, mapping validation and Manager-only review. No network/API secret is required.

## Monorepo contract

The repository root exposes exactly one installable addon directory, `facodi_learning`. `facodi-monorepo` consumes this repository as `addons/facodi-learning` and pins an exact commit before building an immutable Odoo image.

## Out of scope for core

- FACODI theme/branding
- replacement of Odoo eLearning models
- hard-coded external AI vendor
- provider credentials in source or normal business records
- automatic mapping approval
- direct infrastructure/deployment logic
