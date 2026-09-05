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
| `facodi.learning.mapping` | Directed content-level related/prerequisite/recommended/supports proposal and Manager review |
| `facodi.learning.course.mapping` | Reviewed course-level semantic relation evidence; native Odoo prerequisites remain canonical |

Attempts are separate from successful results because failures also require
history. Course candidates are not canonical courses: a resolved new candidate
creates exactly one standard `slide.channel`, while resolution to an existing
course links the candidate to that standard channel. There is no model for every
pipeline stage, no worker queue and no new LMS or taxonomy. `slide.channel` and its
standard sequence/sections remain the canonical course structure.

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

## M3.2 course profile

M3.2 adds no persistent model. `slide.channel` exposes the private method:

```python
profile = channel._facodi_course_profile()
```

The method delegates to `services/course_profile.py`, which computes a plain,
JSON-serializable dictionary on demand. The schema is versioned as
`course-profile-v1`; an incompatible future shape must use a new schema version
rather than silently changing M3.2 semantics.

Top-level keys are stable:

```text
schema_version
channel
course_tags
prerequisite_channel_ids
structure
sections
contents
analysis
approved_content_relations
```

`channel` contains canonical standard metadata and plain-text descriptions.
`course_tags` preserves standard Odoo channel-tag grouping/order. Native
`prerequisite_channel_ids` are copied only as ordered standard course IDs; FACODI
does not create a duplicate prerequisite graph.

`structure` contains section/content counts, standard `slide.channel.total_time`
and fixed category counts for article/document/infographic/quiz/video. Sections
and contents are ordered deterministically by `(sequence, id)`. Content entries are
compact signals only: ID, name, sequence, standard section/category/type,
completion time and standard content tags. Category rows (`is_category=True`) are
represented as sections, not duplicated as contents.

Analysis contributes only safe aggregate evidence. For each current content item,
the latest immutable `facodi.learning.analysis.result` by `create_date desc, id
desc` may contribute its non-empty `detected_language`. The profile exposes only
`analyzed_content_count` and the sorted distinct language set. Generated summary,
transcript, raw payload, provider credentials/prompts and suggested-but-unreviewed
content are not copied into the baseline profile.

Content relations contribute only when `facodi.learning.mapping.state ==
"approved"`. They are collapsed into deterministic course-level counts grouped by
counterpart `slide.channel` and mapping type. Proposed/rejected mappings and raw
mapping IDs do not affect the profile. This is evidence for retrieval, not a
course-level relation decision.

The builder performs no writes, no `sudo()`, no network call and no external AI
request. It uses the caller's ordinary ORM environment and native access behavior.
It intentionally includes current unpublished standard content because the profile
represents canonical editorial state for internal processing. Learner-facing
publication/access filtering remains separate and unchanged.

Learner/member/progress state is outside the schema. Adding/removing a
`slide.channel.partner` does not change the profile, and no partner identity,
email, membership count, completion flag or user-specific progress is included.

## M3.3 course mapping

M3.3 creates a reviewed course-relation layer without changing the canonical
course model. The flow is:

```text
slide.channel
  -> course-profile-v1
  -> bounded deterministic retrieval
  -> course-mapping-v1 ranking
  -> facodi.learning.course.mapping proposal
  -> Manager review / restricted Auto Approve
  -> approved semantic relation
       or native slide.channel prerequisite write
```

### Retrieval and ranking

`services/course_mapping.py` retrieves a bounded set of active target
`slide.channel` records, excludes the source course and respects a specific source
website when one is configured. It never consults learner membership, completion or
progress. The service then builds M3.2 profiles and computes deterministic signals:

- normalized title overlap;
- standard course-tag Jaccard overlap;
- detected-language compatibility when language evidence exists;
- standard total-duration similarity.

The weighted result is versioned as `course-mapping-v1`. Proposed relation
generation is idempotent by directed `(source_channel_id, target_channel_id,
mapping_type)` identity. An existing proposal is reused rather than silently
rewriting its original ranking evidence. Generation additionally acquires a
transaction-scoped advisory try-lock keyed by the source course before profiling,
searching or inserting proposals. A competing request for the same source fails
closed with a retryable validation error before any proposal is created; different
source courses remain parallel. The SQL unique directed triple remains the data
integrity backstop, while the per-source lock closes the concurrent `search ->
create` race. The baseline ranker proposes only `related`; other relation types are
explicit editorial choices or future provider outputs.

Retrieval/ranking perform no `sudo()`, network request, AI request, embedding
lookup, or learner-data access. Officers can generate proposals only through the
ordinary permissions of the source course and mapping model.

### Course mapping audit model

`facodi.learning.course.mapping` stores two standard course references plus relation
type, confidence, origin, proposal state, ranking/evidence metadata and review
history. Source and target must differ and the directed relation triple is unique.
Supported types are:

- `related`
- `alternative`
- `continuation`
- `complements`
- `equivalent`
- `prerequisite`

Reviewed rows are immutable audit history. Review is serialized with
`try_lock_for_update()` and restricted to eLearning Managers. Direct ORM writes
cannot forge approved/rejected state or terminal reviewer/policy/native-application
evidence.

### Native prerequisites

A course mapping with `mapping_type="prerequisite"` is never a second prerequisite
truth. Its semantics are `source_channel_id` requires `target_channel_id`. Manager
approval validates the existing native prerequisite graph and then uses
`Command.link(target.id)` on the source course's standard
`prerequisite_channel_ids` field.

Before the write, FACODI traverses the native Odoo graph and rejects both direct and
transitive cycles. Re-approval is idempotent when the native link already exists.
The mapping row records who/when applied the native link but learner progression
continues to use Odoo's standard prerequisite implementation.

Content-level `facodi.learning.mapping` prerequisite labels remain optional content
relationships and do not mutate the native course prerequisite graph.

### Course mapping Auto Approve

Course mapping policy is independent from M3.1 course-selection policy. Settings
are stored with the normal `res.config.settings` + `config_parameter` pattern:

- `facodi_learning.course_mapping_mode`
- `facodi_learning.course_mapping_auto_types`
- `facodi_learning.course_mapping_min_confidence`

The default is Manual. Auto mode is fail-closed: execution must be an actual
superuser/eLearning Manager context, confidence must meet the configured threshold,
and the relation type must be in both the administrator configuration and the hard
safe-type set. The hard safe set permits only `related` and `complements`.
`prerequisite`, `alternative`, `equivalent` and `continuation` cannot auto-approve
even if configured accidentally.

Automatic decisions persist a versioned decision snapshot and do not populate a
human reviewer. Generation applies this policy only to generated
`origin="analysis"` proposals that remain `proposed`; a coincident manual proposal
is never converted into an automatic decision.

### Backend and learner surfaces

The standard `slide.channel` form is inherited only to add **Find Related Courses**
and a FACODI Course Mappings stat button. Review lives under
**eLearning → FACODI Learning → Course Mapping → Course Mappings**. Content-level
relations remain separately named **Content Mappings** under Content Analysis.

The public course page remains `website_slides.course_main`. A small inherited QWeb
block calls `channel._facodi_related_channels(website)` and renders only approved
non-prerequisite semantic targets. Because Public/Portal users intentionally have no
ACL on the audit model, the helper uses `sudo()` only to discover approved target
IDs. It then switches back to the real caller's non-sudo `slide.channel` environment
and filters `active`, `is_published`, current website and native `is_visible`.
Confidence, policy snapshots and raw evidence are never exposed to learners.

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
Content-mapping SQL uniqueness prevents duplicate directed triples; self-links and
invalid confidence/provenance are rejected. Content-level relations do not replace
standard enrolment, course progression or the native prerequisite graph.

## Transactions and cron

Analysis states are pending → processing → completed/failed; explicit retry returns
failed to pending while retaining the previous error and immutable attempts.
Completed jobs cannot be reprocessed. Provider changes are allowed only while
pending.

Odoo `try_lock_for_update()` prevents simultaneous processing/review and is also
the concurrency primitive for M3.1 course resolution and M3.3 course-mapping
review. M3.3 proposal generation uses a separate transaction advisory try-lock per
source course because proposal identity spans a check-then-insert boundary and a
wait/re-fetch strategy is not relied on inside the transaction's PostgreSQL snapshot.
Prerequisite review also uses its own transaction advisory lock to serialize FACODI
mutations of the native prerequisite graph before row locks and cycle validation.
These locks are operational guards only; standard Odoo records and SQL constraints
remain authoritative.

A job's processing state and terminal outcome are in one transaction: worker death
rolls back to pending, so no timer-based lease/stale-worker mechanism is necessary.
Adapters must not commit and must use timeouts and idempotent external requests.
External services may see a retried request after a crash; this is not a claim of
exactly-once network execution.

Standard `ir.cron` caps analysis batches at 100, defaults to 10, isolates provider
failures with savepoints and uses Odoo 19 `_commit_progress()` per job in real cron
context. Persisted errors contain exception type and a safe generic explanation;
raw provider exceptions are not logged because they may contain credentials.

## Security and editorial review

Officers read audit records and request/retry only for their own courses. Managers
process, ingest and perform terminal review. Model methods enforce lifecycle
transitions on create/write, not only on buttons. Private server methods create
immutable results/attempts; client context flags cannot grant access. Standard
content technical fields are restricted to the eLearning Officer group.

Elevated learner operations are deliberately narrow: configuration-parameter reads
and approved content/course relation ID lookups. Learner helpers return ordinary
non-sudo standard records filtered by publication, native visibility/access and
current website. Students cannot read raw jobs, provenance, transcript drafts,
course candidates, mapping confidence/evidence or decision snapshots. M3.2 profile
generation and M3.3 ranking use no privilege elevation.

## Source website and portability

The reference `edu-open2.odoo.com` was inspected read-only. It uses Odoo 19
Enterprise and `theme_default`; custom addons were absent. Its proposal form posts
to a Studio model `x_propostas_de_conteud`. That database-specific form/model is not
copied to Community. Portable contribution pages use standard contact; moving the
existing proposal backlog requires a separately mapped data migration, not a theme
install.

Schema changes preserve old results and approvals; new attempt records begin with
new executions, without invented historical attempts. M3.1 adds candidate schema,
M3.2 adds only computed profile code, and M3.3 adds an additive course-mapping audit
table/fields/settings/views. No milestone rewrites old audit history. Back up the
database and matching filestore before upgrades. Existing editorial pages remain
outside this addon's ownership except for additive inherited QWeb fragments.

Referenced source/target slides use restrictive foreign keys for content mappings,
so removing content cannot silently erase approved relation history. Archive
historical content instead of deleting it. Course mappings likewise retain audited
standard course references and are reviewed as history rather than disposable
recommendation cache.
