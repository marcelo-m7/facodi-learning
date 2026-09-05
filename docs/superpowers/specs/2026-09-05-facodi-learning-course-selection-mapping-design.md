# FACODI Learning M3 — Course Selection, Mapping and Curriculum Coverage Design

Status: approved architecture, pending implementation plan

Date: 2026-09-05

## 1. Purpose

This design extends `facodi_learning` from content-level ingestion and enrichment into an auditable course-selection and course-mapping system while preserving Odoo 19 Community as the canonical learning platform.

The design covers five connected capabilities:

1. discover and evaluate external course candidates before they become FACODI courses;
2. support manual, assisted and policy-driven Auto Approve selection;
3. build deterministic profiles for existing `slide.channel` courses;
4. propose and review course-to-course educational relationships without duplicating Odoo-native prerequisites;
5. compare the FACODI course catalogue against external curricular references such as an official university degree study plan.

The system must remain useful without external AI, embeddings or network providers. External discovery and semantic-ranking providers are optional extensions.

## 2. Non-negotiable architectural principles

### 2.1 Odoo remains authoritative

The following standard Odoo records and mechanisms remain canonical:

- `slide.channel`: FACODI course;
- `slide.slide`: course content;
- standard course/content tags and course groups;
- eLearning membership, learner progress, quizzes and comments;
- Website publication and visibility;
- Portal and eLearning Officer/Manager permissions;
- native course prerequisite relationships;
- standard `ir.cron`, ORM transactions and record rules.

FACODI must not introduce a parallel LMS, course catalogue, enrolment model, progress model or learner pathway model.

### 2.2 FACODI owns provenance, evaluation and enrichment

FACODI-specific models may represent:

- external candidates before they become courses;
- discovery executions and provider provenance;
- evaluation evidence and policy decisions;
- semantic relationships that Odoo does not represent natively;
- external curricular references and coverage evidence.

These records supplement Odoo. They do not replace `slide.channel` or `slide.slide`.

### 2.3 Machine decisions are evidence-based and auditable

Automation may shortlist or approve only through explicit versioned policies. Automatic decisions must never masquerade as human review.

### 2.4 Auto Approve never means Auto Publish

Auto Approve may resolve an eligible candidate into an existing `slide.channel` or create a new draft course. It must never publish a course, enroll learners or make content publicly available.

### 2.5 Core remains provider-independent

`facodi_learning` must not depend on YouTube, OpenAI, Gemini, MOOC-provider SDKs or other external services. Optional provider addons extend stable registries/contracts.

## 3. Current architecture preserved

The existing content pipeline remains intact:

```text
source
  -> unpublished slide.slide
  -> analysis job
  -> immutable result
  -> proposed tags/content mappings
  -> Manager review
  -> standard tags + approved content relations
```

Existing models keep their existing responsibilities:

- `facodi.learning.source`: content provenance and idempotent ingestion;
- `facodi.learning.analysis.job`: queued content analysis;
- `facodi.learning.analysis.attempt`: immutable execution evidence;
- `facodi.learning.analysis.result`: immutable normalized analysis output;
- `facodi.learning.mapping`: `slide.slide -> slide.slide` educational relation.

The M3 work must not generalize `facodi.learning.mapping` into a polymorphic all-purpose relation table.

## 4. Canonical course-selection architecture

The system supports both external candidates and courses that already exist in Odoo.

```text
EXTERNAL SOURCE
      |
      v
course candidate
      |
      v
evaluation / selection policy
      |
      +-------------------+
      |                   |
      v                   v
link existing        create draft
slide.channel        slide.channel
      |                   |
      +---------+---------+
                |
                v
          slide.channel
       CANONICAL COURSE
                ^
                |
       existing Odoo courses
```

A candidate exists only while FACODI is deciding whether and how an external learning object should enter the catalogue. Once resolved, `slide.channel` is the operational educational record.

Existing `slide.channel` records do not require artificial candidate records. They enter profiling and mapping directly.

## 5. `facodi.learning.course.candidate`

### 5.1 Responsibility

`facodi.learning.course.candidate` is an auditable proposal representing an external course-like object before canonical resolution.

It is not a course and has no learners, progress, publication state, contents or enrolment rules of its own.

### 5.2 Core identity

Required identity fields:

- `provider`;
- `external_id`;
- `source_url` when available.

The external identity is unique on:

```text
(provider, external_id)
```

Repeated discovery of the same external object reuses the same unresolved candidate.

### 5.3 Normalized metadata

Core normalized fields should remain intentionally small:

- `name`;
- `description`;
- `institution` or provider display name;
- `language`;
- `level`;
- `duration_minutes`;
- `license_name` when available;
- `metadata` JSON for provider-specific safe metadata.

The core must not add a database column for every provider-specific field.

### 5.4 Lifecycle

Candidate states:

- `discovered` — normalized candidate exists;
- `evaluated` — current deterministic evaluation is available;
- `shortlisted` — candidate requires or deserves editorial attention;
- `approved` — selection decision accepted but canonical resolution may still be completing;
- `rejected` — terminal editorial rejection;
- `resolved` — candidate is linked to an existing course or created a new draft course.

A separate technical error field may record safe resolution/discovery failures, but technical execution states must not replace editorial states.

### 5.5 Resolution

A candidate can resolve in two ways:

- `existing`: link to an existing `slide.channel`;
- `new`: create a new unpublished `slide.channel`.

Resolution fields include:

- `matched_channel_id` for the best suggested existing match;
- `resolved_channel_id` for the canonical result;
- `resolution_type` (`existing` or `new`);
- `decision_origin` (`manual` or `automatic`);
- `decision_policy_version` when automatic;
- `decision_at`;
- `reviewed_by_id` only for a real human reviewer;
- immutable evaluation snapshot used by the decision.

Automatic decisions must not set `reviewed_by_id` to an administrator merely because the cron ran as that user.

## 6. Candidate evaluation

### 6.1 Deterministic baseline

The first implementation must evaluate candidates without external AI.

Evaluation returns independent signals, not one opaque quality score:

- `relevance_score`;
- `metadata_quality_score`;
- `language_fit_score`;
- `coverage_score`;
- `duplication_risk`.

All normalized scores use the range `0..1`.

The evaluator also returns:

- a recommendation such as `ignore`, `review`, `shortlist` or `review_existing_match`;
- human-readable reasons suitable for Manager review;
- an evaluation-policy/version identifier.

`duplication_risk` is a risk signal, not a negative quality score and must not simply be added to positive scores.

### 6.2 Matching existing courses

Matching is progressive:

1. deterministic source identity where available;
2. normalized title;
3. language;
4. standard Odoo course tags/course groups;
5. institution/provider metadata;
6. later optional semantic similarity.

A likely semantic duplicate may populate `matched_channel_id`, but semantic similarity alone must never auto-link a candidate to an existing course in the baseline implementation.

## 7. Selection modes

The course-selection mode is a Manager-controlled `res.config.settings` option and follows the addon’s existing configuration pattern.

Supported modes:

### 7.1 Manual

```text
discover -> evaluate -> Manager decides
```

No shortlist or approval occurs automatically.

### 7.2 Assisted

```text
discover -> evaluate -> automatic shortlist/recommendation -> Manager decides
```

The system reduces review effort but does not resolve a course automatically.

### 7.3 Auto Approve

```text
discover
  -> evaluate
  -> trusted-provider check
  -> policy guardrails
  -> eligible: approve/resolve
  -> ambiguous: shortlist for manual review
```

Default remains `manual`.

### 7.4 Auto Approve policy

Thresholds are configuration parameters, not scattered hardcoded constants. Baseline configurable signals include:

- minimum relevance;
- minimum metadata quality;
- minimum language fit;
- minimum coverage;
- maximum duplication risk.

A candidate must pass every mandatory guardrail to auto-approve.

Auto Approve is fail-closed. Missing/ambiguous evidence, an untrusted provider, unresolved high duplicate risk or invalid metadata routes to manual review.

### 7.5 Trusted providers

Provider eligibility for Auto Approve is separately configurable. A provider can participate in discovery while remaining ineligible for automatic resolution.

A newly installed/experimental provider must not gain Auto Approve authority merely by returning high scores.

## 8. Resolution guarantees

Manual and automatic resolution call the same domain method and share the same validation.

Required guarantees:

- row-level serialization with Odoo locking;
- idempotent retry after successful resolution;
- only one canonical course created from a candidate;
- savepoint/transaction rollback on failed creation/linking;
- no partial `slide.channel` when resolution fails;
- newly created `slide.channel` remains unpublished;
- publication, enrolment and content publication remain outside this flow.

## 9. Course profile

### 9.1 Purpose

Every existing `slide.channel`, regardless of origin, can produce a normalized FACODI course profile for retrieval and comparison.

Origins may include:

- manually created Odoo courses;
- legacy FACODI courses;
- candidates resolved manually;
- candidates resolved by Auto Approve;
- externally ingested courses.

Origin must not alter educational mapping semantics.

### 9.2 Computed baseline profile

The initial profile is computed, not stored as a second canonical record.

Conceptual source data:

- course identity/title;
- standard course tags and course groups;
- language metadata available to FACODI;
- standard description;
- number/structure of contents/sections;
- content types and available durations;
- applied content tags;
- latest/approved FACODI enrichment signals that are safe to aggregate;
- approved incoming/outgoing content mappings;
- native Odoo course prerequisites;
- Website/access context relevant to candidate retrieval.

The profile must never include learner-level progress, emails or personal learner data.

### 9.3 No profile model initially

M3.2 must begin with a deterministic builder such as a model method/service returning normalized data.

Persistent profile snapshots become justified only when expensive semantic providers, embeddings or historical reproducibility require them. If snapshots are later introduced, they are analysis evidence, not an editable second course record.

## 10. Course mapping engine

### 10.1 Retrieval before ranking

The engine must not compare every course with every other course through an expensive provider.

Flow:

```text
source channel
  -> build profile
  -> cheap candidate retrieval/filtering
  -> small candidate set
  -> deterministic ranking
  -> relation proposals
```

Initial retrieval may use title, language, standard tags/groups, Website/access boundaries and basic profile overlap.

### 10.2 Ranking signals

For each pair, deterministic signals may include:

- topic overlap;
- tag overlap;
- language compatibility;
- level compatibility;
- content coverage overlap;
- duration similarity when meaningful.

The engine returns a proposed relation plus confidence in `0..1`. Confidence is proposal evidence, not CRM probability or learner progress.

## 11. Course-to-course relationship ownership

Odoo already owns prerequisites. FACODI must not maintain a second prerequisite truth.

### 11.1 Native Odoo relationship

`prerequisite` proposals may be generated by FACODI, but once approved the final relationship is written to the native `slide.channel` prerequisite mechanism.

Before application FACODI must block obvious prerequisite cycles derived from existing native relationships.

Prerequisites remain manual-review-only in the initial release.

### 11.2 FACODI semantic relationships

Relations not represented natively may use a dedicated model:

`facodi.learning.course.mapping`

Baseline mapping types:

- `related`;
- `alternative`;
- `continuation`;
- `complements`;
- `equivalent`.

Fields mirror the proven content-mapping pattern:

- `source_channel_id`;
- `target_channel_id`;
- `mapping_type`;
- `confidence`;
- `origin` (`manual` or `analysis`);
- `state` (`proposed`, `approved`, `rejected`);
- analysis/evaluation provenance;
- reviewer and timestamp;
- automatic decision policy version when applicable.

Unique directed triples prevent duplicate mappings. Self-relations are rejected.

The existing `facodi.learning.mapping` remains content-only.

## 12. Auto Approve for course mappings

Mapping Auto Approve uses policy by relationship risk, independent from course-candidate thresholds.

Initial policy:

- `related`: configurable Auto Approve allowed;
- `complements`: configurable Auto Approve allowed after sufficient evidence;
- `alternative`: manual initially;
- `equivalent`: manual initially;
- `continuation`: manual initially unless a later policy explicitly permits it;
- native `prerequisite`: manual initially.

Automatic course-relation decisions store policy version and evidence snapshot and do not pretend to have a human reviewer.

## 13. Discovery providers

### 13.1 Contract

The core exposes a discovery registry conceptually similar to the existing analysis/ingestion registries.

Provider output is normalized before candidate persistence and contains only approved core fields plus safe provider metadata.

The core includes a `manual` provider/workflow so the complete M3.1 pipeline works with no network access.

### 13.2 Optional addons

Examples:

- `facodi_learning_youtube`;
- `facodi_learning_oer`;
- provider-specific institutional catalogue addons;
- later semantic/AI evaluation or ranking addons.

External provider addons may discover and normalize candidates. They must not directly create or publish `slide.channel` records.

## 14. `facodi.learning.discovery.run`

Recurring/explicit provider execution uses a small operational audit model:

- provider;
- state (`pending`, `processing`, `completed`, `failed`);
- start/completion timestamps;
- items seen;
- candidates created;
- candidates refreshed;
- candidates ignored;
- safe last error.

A discovery run is technical execution history, not editorial course state.

Each provider run is transactionally isolated from other providers. Failure in one provider must not block successful discovery from another provider.

Standard `ir.cron`, bounded batches and Odoo `_commit_progress()` patterns are preferred. No Celery/Redis/private worker framework is introduced.

## 15. Candidate refresh semantics

Unresolved candidates in `discovered`, `evaluated` or `shortlisted` may refresh normalized metadata and be reevaluated.

A later refresh can make a previously ambiguous candidate eligible for Auto Approve.

Human terminal decisions (`rejected`, `resolved`) must not be silently reversed by a later discovery run.

When a provider identifies a materially new source revision requiring independent review, it must use a stable versioned external identity rather than rewriting historical evidence.

## 16. External curriculum reference layer

### 16.1 Why it exists

Course-to-course mapping alone cannot answer a second important FACODI question:

> How well does the FACODI catalogue cover an external academic curriculum?

An official degree study plan is not itself a FACODI course and must not be forced into `slide.channel`. It is an external reference structure used for gap analysis, selection guidance and coverage evidence.

This is not a learner pathway and does not own enrolment or progress.

### 16.2 Reference models

The curriculum capability is intentionally separated from Odoo’s operational course records.

Proposed models:

`facodi.learning.curriculum.reference`

- institution;
- programme name;
- external programme code when available;
- academic year/version;
- source URL;
- provider/source identifier;
- normalized metadata;
- imported/validated timestamps.

`facodi.learning.curriculum.unit`

- reference ID;
- external unit code;
- name;
- ECTS/credits when supplied by the source;
- curricular year;
- period/semester/annual value supplied by the source;
- mandatory/optional classification when available;
- option-group label when supplied;
- sequence/order for faithful source presentation;
- safe source metadata.

These models store external reference facts, not FACODI teaching state.

### 16.3 Curriculum coverage mapping

A separate auditable relationship maps FACODI courses to external curriculum units:

`facodi.learning.curriculum.coverage`

Conceptual fields:

- `channel_id` (`slide.channel`);
- `curriculum_unit_id`;
- coverage type such as `covers`, `partial`, `supports`, `equivalent`;
- confidence;
- origin (`manual` or `analysis`);
- state (`proposed`, `approved`, `rejected`);
- provenance/evaluation reference;
- reviewer/timestamp;
- automatic policy evidence if Auto Approve is later enabled for low-risk coverage types.

A curriculum unit may be covered by multiple FACODI courses and one FACODI course may cover multiple external units.

No automatic academic credit recognition is implied by this mapping.

### 16.4 LESTI / Universidade do Algarve reference case

The official University of Algarve study-plan pages for the Licenciatura em Engenharia de Sistemas e Tecnologias Informáticas (LESTI), course code 1941, provide a concrete validation case.

Official references checked on 2026-09-05:

- https://www.ualg.pt/curso/1941/plano
- https://www.ise.ualg.pt/curso/1941/plano

The published plan demonstrates source dimensions the model must preserve:

- academic-year version (for example 2026/27 and 2025/26);
- curricular year;
- semester/period;
- curricular-unit name;
- curricular-unit code;
- ECTS;
- mandatory/common trunk structure;
- option groups and alternative units.

Examples visible in the published plans include Programming, Web Technologies, Object-Oriented Programming, Algorithms and Data Structures, Databases I/II, Software Engineering, Probability and Statistics, Artificial Intelligence, and a 30-ECTS Internship/Project choice in the final stage of the degree, depending on the published academic-year structure.

The public study-plan page used for this design does not provide explicit prerequisite relationships between curricular units. FACODI must therefore not infer official prerequisites merely from curricular year or semester order. A prerequisite can be proposed semantically as a FACODI/Odoo educational relation only when supported by separate evidence; it must not be presented as an official UAlg rule unless an authoritative source states it.

### 16.5 Coverage-driven selection

A curriculum reference can influence candidate evaluation without becoming the candidate’s owner.

Example:

```text
LESTI curriculum unit: Base de Dados II
        |
        v
current FACODI approved coverage
        |
        +-- strong -> no discovery priority
        |
        +-- partial/gap -> raise coverage need
                           |
                           v
                    candidate evaluation
```

`coverage_score` therefore may be calculated against one or more selected curriculum targets. The evaluation evidence must record which curriculum/version informed that score.

The core must remain usable without any configured curriculum reference.

### 16.6 No parallel curriculum execution engine

The curriculum reference layer must not create:

- learner registrations in a university programme;
- academic transcripts;
- official credit decisions;
- automatic ECTS recognition;
- semester progression rules;
- a new FACODI learning-path engine.

It is a benchmark/reference and coverage system only.

## 17. Security model

The addon reuses standard eLearning roles.

### 17.1 Public and Portal

Public/Portal users cannot read candidates, discovery runs, evaluation scores, provider metadata, confidence, rejected/proposed relations or curriculum audit records.

Learners may see only safe approved output after native Website/eLearning access filters.

### 17.2 Officers

Officers may:

- read relevant FACODI audit information according to existing eLearning rules;
- create/request manual candidates where configured;
- reevaluate or propose mappings for courses they own;
- inspect approved curriculum coverage where allowed.

Officers cannot configure Auto Approve, execute privileged provider configuration, terminally resolve candidates, or apply native prerequisites.

### 17.3 Managers

Managers may:

- manage providers and selection policies;
- approve/reject/resolve candidates;
- create/link canonical courses;
- review semantic mappings;
- apply approved native prerequisite decisions;
- manage curriculum references and coverage review.

No new FACODI curator group is required unless a later concrete authorization boundary proves standard roles insufficient.

## 18. Secrets and provider safety

Runtime secrets remain in deployment/provider configuration, never candidate metadata or raw payloads.

Providers must use timeouts, pagination/rate-limit handling and idempotent external requests.

Persisted errors are sanitized. Provider exceptions, authorization headers, cookies, tokens and secret-bearing raw responses are not persisted or logged verbatim.

## 19. Learner-facing behavior

Students see only approved relations whose target `slide.channel` remains accessible under native publication, Website, visibility and enrolment/access rules.

Possible presentation labels include:

- Related Courses;
- Before You Start;
- Continue Learning;
- Complementary Courses.

Internal confidence, policy version, curriculum coverage scores and discovery provenance are not exposed to learners.

The implementation should follow the same limited-elevation pattern already used by `_facodi_related_slides()`: relation lookup may be privileged internally, but returned canonical records must be ordinary access-filtered Odoo records.

## 20. Transactions, concurrency and idempotency

Required invariants:

- unique candidate identity `(provider, external_id)`;
- candidate resolution serialized with row locking;
- unique course mapping `(source_channel_id, target_channel_id, mapping_type)`;
- unique/controlled curriculum coverage relation for the same channel/unit/type;
- automatic retry after terminal success is harmless;
- provider or resolution failures do not leave partial canonical data;
- reviewed historical evidence cannot be silently rewritten.

## 21. Configuration

Manager-facing `res.config.settings` includes, at minimum:

- course-selection mode (`manual`, `assisted`, `auto`);
- deterministic evaluation thresholds;
- maximum duplication risk;
- trusted-provider Auto Approve eligibility;
- discovery enabled/disabled controls and bounded batch size;
- course-mapping Auto Approve thresholds by low-risk relation type.

Configuration uses `config_parameter` following the existing FACODI analysis settings pattern.

Policy decisions store a policy version so later threshold changes do not rewrite the rationale for historical decisions.

## 22. Administrative UX

Reorganize the technical FACODI menu into an editorially meaningful hierarchy:

```text
eLearning
└── FACODI Learning
    ├── Course Discovery
    │   ├── Candidates
    │   └── Discovery Runs
    ├── Course Mapping
    │   └── Relations
    ├── Curriculum Coverage
    │   ├── References
    │   ├── Units
    │   └── Coverage
    └── Content Analysis
        ├── Jobs
        ├── Results
        └── Content Mappings
```

Managers should primarily see decisions and evidence rather than raw technical jobs.

## 23. Testing strategy

### 23.1 M3.1 Course Selection Core

Tests prove:

- repeated provider/external ID creates one candidate;
- unresolved metadata refresh is allowed;
- terminal identity/decision evidence is protected;
- Manual mode never approves automatically;
- Assisted mode shortlists but never resolves automatically;
- Auto mode resolves only when every policy guardrail passes;
- untrusted provider cannot auto-resolve;
- high duplicate risk routes to review;
- concurrent resolution creates/links only one canonical course;
- `new` resolution creates exactly one unpublished `slide.channel`;
- `existing` resolution creates no new channel;
- retries after success are idempotent;
- Officer cannot perform Manager-only resolution;
- Public/Portal cannot read candidates;
- resolution failure rolls back partial course creation;
- later configuration changes do not mutate prior decision evidence.

### 23.2 M3.2 Course Profile

Tests cover:

- empty course;
- course with no analysis;
- partially analyzed course;
- aggregated standard tags and approved FACODI signals;
- mixed content types/languages where supported;
- deterministic repeat output;
- no learner-private data in profile.

### 23.3 M3.3 Course Mapping

Tests prove:

- self-mapping rejected;
- duplicate mapping idempotent/rejected safely;
- confidence validation;
- inaccessible/missing target rejected;
- low-risk relation can follow configured Auto Approve policy;
- strong-risk relations remain manual;
- prerequisite proposals do not create cycles;
- approved native prerequisite writes only to the Odoo-native field;
- only approved accessible semantic relations appear learner-facing;
- proposed/rejected/private/different-website inaccessible targets remain hidden.

### 23.4 Curriculum reference and coverage

Tests prove:

- academic-year versions remain independent;
- source codes/ECTS/year/period/option group are preserved exactly as imported;
- repeated import of the same curriculum version is idempotent;
- multiple courses may cover one unit;
- one course may cover multiple units;
- proposed/rejected coverage is not treated as approved coverage;
- changing a later academic-year plan does not rewrite historical versions;
- curricular year/semester ordering does not automatically create prerequisites;
- a LESTI-like fixture with mandatory units, option groups and a final 30-ECTS choice can be represented without creating learner progression logic.

### 23.5 Provider contract tests

A fake provider covers:

- valid candidate;
- duplicate candidate;
- malformed identity;
- invalid metadata;
- safe provider exception;
- timeout-like failure;
- isolation between successful and failed provider runs.

## 24. Install, upgrade and portability

All schema evolution should be additive to existing M2 data.

Existing content analysis/results/mappings are not converted to course mappings.

Release gates remain:

```text
contract/static tests
  -> clean Odoo 19 install
  -> ORM/security tests
  -> HTTP/Website tests where applicable
  -> upgrade existing database
  -> regression tests again
```

The core M3 must install and operate with no external provider addon and no network access.

## 25. Delivery slices

### M3.1 — Course Selection Core

Deliver:

- `facodi.learning.course.candidate`;
- deterministic evaluation service;
- Manual/Assisted/Auto Approve modes;
- trusted-provider policy;
- deterministic duplicate matching;
- manual provider/workflow;
- safe link-existing/create-draft resolution;
- audit/security/UI/tests.

Definition of done:

```text
candidate
  -> normalize
  -> evaluate
  -> deduplicate
  -> manual/assisted/auto selection
  -> resolve safely
  -> canonical unpublished/existing slide.channel
```

### M3.2 — Course Profile

Deliver deterministic profile generation from Odoo course/content data and approved FACODI enrichment without persistent second-course state.

### M3.3 — Course Mapping Engine

Deliver candidate retrieval, deterministic ranking, auditable semantic relation proposals, Manager review, low-risk policy-driven Auto Approve and native prerequisite application.

### M3.4 — Curriculum Reference and Coverage

Deliver versioned external curriculum references, units and coverage mappings. Validate with an official-plan-shaped fixture modeled on the published LESTI/UAlg study-plan structure without hardcoding UAlg-specific logic.

### M3.5 — External Discovery Providers

Add optional YouTube/OER/institutional catalogue adapters and `facodi.learning.discovery.run` scheduling/operations.

### M3.6 — Semantic/AI Ranking

Add optional semantic ranking/evaluation providers only after deterministic retrieval, audit and policy boundaries are stable.

AI improves ranking and analysis; it does not become the canonical source of course or curriculum truth.

## 26. Explicit non-goals

M3 does not create:

- `facodi.course` parallel to `slide.channel`;
- learner pathways/progress models;
- automatic publication;
- automatic enrolment;
- automatic official academic-credit recognition;
- inferred official university prerequisite rules without authoritative evidence;
- mandatory external AI/embedding dependencies;
- a generic polymorphic relation table covering every object type;
- a second job framework unless a later slice proves the existing Odoo/job patterns insufficient.

## 27. Final architecture

```text
                    EXTERNAL PROVIDERS
                           |
                           v
                    DISCOVERY RUN
                           |
                           v
                   COURSE CANDIDATE
                           |
                           v
                      EVALUATION
                           |
                           v
                  SELECTION POLICY
                manual/assisted/auto
                           |
                           v
                       RESOLUTION
                           |
                +----------+----------+
                |                     |
          link existing          create draft
                |                     |
                +----------+----------+
                           v
                     slide.channel
                    CANONICAL COURSE
                           |
                     COURSE PROFILE
                           |
                           +---------------------------+
                           |                           |
                           v                           v
                   COURSE MAPPING              CURRICULUM COVERAGE
                           |                           |
                  +--------+--------+                  v
                  |                 |         external curriculum
                  v                 v          reference + units
          Odoo prerequisite   FACODI semantic          |
                              course.mapping           |
                  |                 |                  |
                  +--------+--------+------------------+
                           |
                           v
                    reviewed evidence
                           |
                           v
                   learner-safe output
```

This design keeps Odoo authoritative while adding a reusable, auditable mechanism for deciding which courses enter FACODI, how courses relate to each other, and how the catalogue covers external educational structures such as an official university degree plan.
