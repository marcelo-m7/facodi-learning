# FACODI Learning architecture

Odoo 19 Community owns courses, content, tags and learner behavior. FACODI owns
only discovery/provenance, analysis evidence and reviewed enrichment. There is no
dependency on `theme_facodi`.

| Model | Responsibility |
| --- | --- |
| `facodi.learning.course.candidate` | Stable provider/external course identity, normalized source metadata, deterministic evaluation and terminal decision audit |
| `facodi.learning.source` | Stable provider/external ID/course identity, URL, metadata, state, timestamps and canonical content link |
| `facodi.learning.analysis.job` | Requester, provider, state, attempt count and latest outcome |
| `facodi.learning.analysis.attempt` | Immutable evidence for each completed or failed execution, including retries |
| `facodi.learning.analysis.result` | Immutable normalized output; separate human tag review metadata |
| `facodi.learning.mapping` | Directed related/prerequisite/recommended/supports proposal and Manager review |

Attempts are separate from successful results because failures also require
history. Course candidates are not canonical courses: a resolved new candidate
creates exactly one standard `slide.channel`, while resolution to an existing
course links the candidate to that standard channel. There is no model for every
pipeline stage, no worker queue and no new LMS or taxonomy. `slide.channel` and its
standard sequence/sections represent learning paths; mappings express optional
educational relationships, not new progression or enrolment rules.

## M3.1 course selection

Course candidates use immutable `(provider, external_id)` identity protected both
by deterministic ORM validation and a SQL uniqueness constraint. `requested_by_id`
is server-owned. Source metadata may be refreshed only while the candidate remains
unresolved; provider/external identity, generated evaluation evidence and terminal
decision evidence cannot be forged through ordinary ORM writes.

`services/course_selection.py` contains the deterministic evaluation and selection
policy boundary. The evaluator normalizes titles, computes a local title-similarity
signal and persists relevance, metadata quality, language fit, M3.1 coverage
baseline, duplicate risk, recommendation and stable evaluator version
`course-evaluation-v1`. It performs no network call. `matched_channel_id` is a
review suggestion and never becomes an automatic existing-course resolution in
M3.1.

Selection configuration is read through `ir.config_parameter` with `sudo()` only
for configuration access. Invalid modes fail back to Manual; thresholds are parsed,
clamped to `0..1` and invalid values fall back to conservative defaults. Languages
and trusted providers are normalized non-empty sets. The policy is versioned as
`course-selection-v1`.

The three modes have deliberately different authority:

- Manual: evaluation only; no automatic shortlist or resolution.
- Assisted: eligible review recommendations may become `shortlisted`; no terminal
  decision is created.
- Auto Approve: eligibility is fail-closed across trusted provider, score
  thresholds, duplicate risk, recommendation and unresolved state. Only an actual
  superuser/eLearning Manager execution context may perform the automatic terminal
  action; Officer execution never escalates privileges and remains reviewable.

Automatic and manual new-course resolution share `_resolve()`. Manual Managers may
also resolve to an explicitly selected existing standard course. `_resolve()` uses
Odoo `try_lock_for_update()` and refuses unavailable row locks with a retryable
validation error. After locking it invalidates/re-reads the candidate, returns the
same canonical channel for an idempotent replay of the same resolution and rejects
conflicting second decisions.

Canonical create/link plus decision persistence occur inside a savepoint. A failed
new-course create leaves no partial `slide.channel`; only sanitized failure text is
stored on the unresolved candidate. New channels are created through the ordinary
current-user ORM environment and are explicitly `website_published=False`. There is
no `sudo()` around resolution, and Auto Approve never publishes content.

Every terminal resolution stores a JSON decision snapshot containing all five
scores, recommendation, evaluator version and the effective selection thresholds,
languages/trusted-provider evidence and policy version. Later settings changes do
not recompute or rewrite the stored snapshot. Manual decisions additionally record
`reviewed_by_id`; automatic decisions record their policy version and no human
reviewer.

Candidate ACLs mirror eLearning operational roles: Public/Portal have no model
access; Officers can read candidate audit records and create/write only their own
unresolved candidates; Managers have model-level access but Python lifecycle guards
still protect identity and terminal evidence. Terminal resolution/rejection remains
Manager-only.

M3.1 intentionally stops at course selection. Curriculum reference/coverage,
external discovery runs/providers, course-profile aggregation, semantic course
mapping and AI ranking belong to later milestones and must not be inferred from the
M3.1 candidate schema.

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

Analysis states are pending → processing → completed/failed; explicit retry returns
failed to pending while retaining the previous error and immutable attempts.
Completed jobs cannot be reprocessed. Provider changes are allowed only while
pending.

Odoo `try_lock_for_update()` prevents simultaneous processing/review and is also
the concurrency primitive for M3.1 course resolution. A job's processing state and
terminal outcome are in one transaction: worker death rolls back to pending, so no
timer-based lease/stale-worker mechanism is necessary. Adapters must not commit and
must use timeouts and idempotent external requests. External services may see a
retried request after a crash; this is not a claim of exactly-once network execution.

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
Students cannot read raw jobs, provenance, transcript drafts, course candidates or
confidence. Tag review records approver/rejector and timestamps separately from
generated data.

## Source website and portability

The reference `edu-open2.odoo.com` was inspected read-only. It uses Odoo 19 Enterprise
and `theme_default`; custom addons were absent. Its proposal form posts to a Studio
model `x_propostas_de_conteud`. That database-specific form/model is not copied to
Community. Portable contribution pages use standard contact; moving the existing
proposal backlog requires a separately mapped data migration, not a theme install.

Schema changes preserve old results and approvals; new attempt records begin with
new executions, without invented historical attempts. M3.1 adds candidate schema
and backend views without rewriting existing learning/content-analysis data. Back
up database+filestore before upgrades. Existing editorial pages are outside this
addon's ownership.

Referenced source/target slides use restrictive foreign keys for mappings, so
removing content cannot silently erase approved relation history. Remove an
unreviewed manual proposal explicitly where appropriate; archive historical
content instead of deleting it. Upgrading the addon applies these foreign-key
changes through the native ORM schema update without a data rewrite.

New analysis-origin mappings require a matching result reference. Legacy rows
lacking provenance are preserved on upgrade rather than assigned invented evidence.
