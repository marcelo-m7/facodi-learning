# FACODI Learning

`facodi-learning` provides the Odoo 19 Community addon **`facodi_learning`** for analysis and educational mapping in FACODI.

The module follows a standard-first rule: Odoo eLearning remains the learning platform. FACODI extends it only where the standard application has no equivalent mechanism.

## What stays standard Odoo

- `slide.channel` remains the course model.
- `slide.slide` remains the canonical content/lesson model.
- `slide.tag` remains the content-tag vocabulary.
- eLearning Officer and Manager groups remain the authorization roles.
- Website/eLearning forms, menus, settings and scheduled actions are inherited or extended rather than replaced.
- The normal Odoo publication, membership, access, completion, quiz and website behavior is untouched.

## What this addon adds

- Auditable analysis jobs for `slide.slide`.
- Append-only analysis result history.
- Optional transcript metadata on standard eLearning content.
- Suggested standard `slide.tag` values and an explicit action to apply them.
- Proposed semantic relationships between standard eLearning content records.
- Human approval/rejection of mappings by an eLearning Manager.
- A bounded scheduled-action processor using standard `ir.cron`.
- Settings under the standard eLearning configuration page.
- An extensible provider registry, with a no-network `local_metadata` provider as the safe default.

## Installation

The repository root contains exactly one installable addon directory:

```text
facodi_learning/
```

Add the repository root to `addons_path`, update the Apps list and install **FACODI Learning**.

CLI example:

```bash
odoo -d facodi -i facodi_learning --stop-after-init
```

## Configuration

Open **eLearning → Configuration → Settings → FACODI Analysis**.

The default provider is `local_metadata`. It analyses only metadata already held by Odoo and performs no network request. External AI/video providers should be implemented as separate provider extensions and must not change the FACODI domain models.

Pending jobs are processed by the standard scheduled action **FACODI: Process learning analysis jobs**. The batch size is configurable and capped in code to protect cron workers from unbounded work.

## Provider extension contract

A provider addon inherits `facodi.learning.analysis.job`, calls `super()` in `_get_provider_registry()` and adds a callable. The callable receives one `slide.slide` and returns normalized keys such as `summary`, `detected_language`, `suggested_tag_ids`, `model_name` and `raw_payload`.

Provider-specific request/response code belongs outside the core domain models. Secrets must come from deployment/runtime configuration, never from source code.

## Testing

GitHub Actions starts PostgreSQL 16 and installs the addon in the official `odoo:19.0` image on a clean database, then runs the module tests:

```text
--test-tags /facodi_learning
```

The suite verifies the job lifecycle, retry behavior, history preservation, reuse of standard eLearning tags, mapping constraints and Manager-only review.

## Monorepo contract

`marcelo-m7/facodi-monorepo` consumes this repository as a Git submodule at:

```text
addons/facodi-learning
```

The monorepo pins a commit. A change in this repository does not deploy itself until the monorepo intentionally updates that submodule pointer and builds a new image.

## License

LGPL-3.0, aligned with the module manifest.
