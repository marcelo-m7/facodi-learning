# FACODI Learning architecture

Odoo 19 Community owns courses, content, tags and learner behavior. FACODI owns
only provenance and enrichment. There is no dependency on `theme_facodi`.

| Model | Responsibility |
| --- | --- |
| `facodi.learning.source` | Stable provider/external ID/course identity, URL, metadata, state, timestamps and canonical content link |
| `facodi.learning.analysis.job` | Requester, provider, state, attempt count and latest outcome |
| `facodi.learning.analysis.attempt` | Immutable evidence for each completed or failed execution, including retries |
| `facodi.learning.analysis.result` | Immutable normalized output; separate human tag review metadata |
| `facodi.learning.mapping` | Directed related/prerequisite/recommended/supports proposal and Manager review |

Attempts are separate from successful results because failures also require
history. There is no model for every pipeline stage, no worker queue and no new
LMS or taxonomy. `slide.channel` and its standard sequence/sections represent
learning paths; mappings express optional educational relationships, not new
progression or enrolment rules.

## Ingestion

`source.ingest(values, slide_id=None)` serializes initial registration on the
standard target course row. A SQL uniqueness constraint protects
`(provider, external_id, channel_id)`; use an explicit version in the external ID
when a source revision must be imported independently. Identities are immutable.
Replays return the same source/content and never overwrite editorial edits.
Manager-only ACLs guard ingestion; target course/content write access is checked.

Core `manual` ingestion creates a draft article or associates existing content in
the same course. Source URLs are provenance only: core does not fetch arbitrary
URLs. Trusted adapters extend `_get_ingestion_registry()` and return ORM values.
A savepoint rolls back partial content on failure while retaining a failed source.
New content always receives the source course and unpublished state. Imported
provenance cannot be edited; new revisions use new source identities.

## Analysis contract

`job._get_provider_registry()` maps provider names to callables receiving one
standard slide. The default `local_metadata` adapter is deterministic and offline.
Return a dictionary with any of:

- `summary`, `transcript`, `detected_language`, `model_name`: text;
- `suggested_tag_ids`: existing standard tag IDs;
- `suggested_tags`: proposed names, created/reused only on explicit Manager apply;
- `proposed_mappings`: dictionaries with `target_slide_id`, `mapping_type` and
  optional confidence between 0 and 1;
- `raw_payload`: JSON-serializable metadata without secrets.

The boundary validates types, tag/target existence and access before persisting.
Any malformed result rolls back its proposals/output and fails only its job.
Mapping SQL uniqueness prevents duplicate directed triples; self-links and invalid
confidence/provenance are rejected. Relations do not enforce prerequisite cycles
or replace standard enrolment/progression.

## Transactions and cron

States are pending → processing → completed/failed; explicit retry returns failed
to pending while retaining the previous error and immutable attempts. Completed
jobs cannot be reprocessed. Provider changes are allowed only while pending.

Odoo `try_lock_for_update()` prevents simultaneous processing or review. A job's
processing state and terminal outcome are in one transaction: worker death rolls
back to pending, so no timer-based lease/stale-worker mechanism is necessary.
Adapters must not commit and must use timeouts and idempotent external requests.
External services may see a retried request after a crash; this is not a claim of
exactly-once network execution.

Standard `ir.cron` caps batches at 100, defaults to 10, isolates provider failures
with savepoints and uses Odoo 19 `_commit_progress()` per job in real cron context.
The scheduled action is `noupdate` so module upgrades preserve administrator tuning.
Persisted errors contain exception type and a safe generic explanation; raw
provider exceptions are not logged because they may contain credentials.

## Security and editorial review

Officers read audit records and request/retry only for their own courses. Managers
process, ingest and review. Model methods enforce state transitions on create/write,
not only on buttons. Private server methods create immutable results/attempts;
client context flags cannot grant access. Standard content technical fields are
restricted to the eLearning Officer group.

The only elevated operations are configuration-parameter reads and an approved
relation lookup for learner links. The latter returns ordinary non-sudo slides,
filtered by published content/course, native visibility/access and current website.
Students cannot read raw jobs, provenance, transcript drafts or confidence.
Tag review records approver/rejector and timestamps separately from generated data.

## Source website and portability

The reference `edu-open2.odoo.com` was inspected read-only. It uses Odoo 19 Enterprise
and `theme_default`; custom addons were absent. Its proposal form posts to a Studio
model `x_propostas_de_conteud`. That database-specific form/model is not copied to
Community. Portable contribution pages use standard contact; moving the existing
proposal backlog requires a separately mapped data migration, not a theme install.

Schema changes preserve old results and approvals; new attempt records begin with
new executions, without invented historical attempts. Back up database+filestore
before upgrades. Existing editorial pages are outside this addon’s ownership.

Referenced source/target slides use restrictive foreign keys for mappings, so
removing content cannot silently erase approved relation history. Remove an
unreviewed manual proposal explicitly where appropriate; archive historical
content instead of deleting it. Upgrading the addon applies these foreign-key
changes through the native ORM schema update without a data rewrite.
