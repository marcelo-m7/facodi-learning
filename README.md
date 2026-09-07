# FACODI Learning

`facodi_learning` extends Odoo 19 Community `website_slides` with auditable
course discovery, content ingestion and educational enrichment. It works
independently of any theme.

## Standard Odoo remains authoritative

Courses (`slide.channel`), content (`slide.slide`), tags (`slide.tag`), membership,
publication, progress, quizzes, comments, Portal and eLearning Officer/Manager
roles are reused. There is no FACODI LMS, parallel course model or pathway model.
FACODI course candidates are temporary/audit records; every approved new course
becomes one standard `slide.channel`. FACODI course mappings are reviewed semantic
evidence; native Odoo course prerequisites remain the canonical prerequisite graph.
External curriculum references added by M3.4 are comparison/audit data only and do
not replace Odoo courses or learner progression.

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

## Course Mapping — M3.3

In **eLearning → FACODI Learning → Course Mapping → Course Mappings**, Officers can
work with course-relation proposals and Managers can approve or reject them. The
standard course form also exposes **Find Related Courses** plus a FACODI Course
Mappings stat button; no parallel course editor or route is introduced.

`course-mapping-v1` uses the M3.2 profile to retrieve a bounded set of compatible
standard courses and rank each pair deterministically from title overlap, standard
course-tag overlap, language compatibility and duration similarity. Retrieval and
ranking do not use learner membership/progress, external AI, embeddings, network
calls or privilege elevation. Re-running generation reuses an existing directed
`(source, target, relation type)` proposal instead of rewriting its audit evidence.
Generation is serialized per source course with a fail-closed transaction advisory
lock, so overlapping requests cannot both pass the search/create boundary; a
concurrent request is asked to retry before any proposal is created.

Course-level semantic relations are stored in `facodi.learning.course.mapping` with
source/target standard courses, relation type, confidence, origin, ranking evidence,
review status and decision audit. Supported semantic types are `related`,
`alternative`, `continuation`, `complements` and `equivalent`. `prerequisite` is a
special reviewed proposal: on Manager approval FACODI writes only the native
`slide.channel.prerequisite_channel_ids` relation. The FACODI row remains audit
evidence and never becomes a second prerequisite truth. Direct and transitive
prerequisite cycles are rejected before the native write.

Course-mapping Auto Approve is configured independently from M3.1 course selection.
It defaults to **Manual**, is fail-closed, requires an authorized Manager context
and a configured minimum confidence, and can only act on a strict allowlist of
low-risk semantic types. `prerequisite`, `alternative`, `equivalent` and
`continuation` are never auto-approved. Automatic decisions store the effective
policy snapshot/version and do not pretend a human reviewer approved them.

Approved semantic relations can appear as **Related courses** inside the standard
Odoo course page. Public/Portal users still cannot read the FACODI audit model: the
server elevates only the approved-relation ID lookup, then returns ordinary
non-sudo `slide.channel` records filtered by standard publication, current website
and native `is_visible` rules. Prerequisite relations are not rendered by this
semantic related-course block because Odoo owns prerequisite behavior.

M3.3 intentionally does not add learner-personalized recommendations, curriculum
credit recognition, vector storage, embeddings or AI-based course mapping.

## Curriculum Reference & Coverage — M3.4

M3.4 provides an internal editorial workspace for comparing canonical FACODI
courses with a versioned external curriculum reference. It does **not** create a
FACODI degree/pathway model and it does not alter Odoo learner progression.

The backend lives in **eLearning → FACODI Learning → Curriculum Coverage** with
separate **References**, **Curricular Units** and **Coverage** actions. A reference
stores institution/programme/version/source identity. Its curricular units retain
source-shaped facts such as external unit code, source credit value, curricular
year, period, classification, option group and sequence.

`facodi.learning.curriculum.coverage` relates a standard `slide.channel` to an
external curricular unit using reviewed evidence types `covers`, `partial`,
`supports` or `equivalent`. One course may support several units and one unit may
have several approved FACODI courses. The `equivalent` label is internal coverage
evidence only: **it does not grant official academic equivalence, ECTS recognition,
credit award, enrolment or transcript status.** Source ECTS values are descriptive
facts from the external plan, not FACODI-awarded credits.

Gap analysis is deterministic and read-only. It considers only approved coverage
and classifies each curricular unit as `covered`, `partial` or `gap`; proposals and
rejections do not affect results. It does not inspect learner membership, progress
or completion. Curriculum year, semester/period, sequence and option-group data do
not infer Odoo prerequisites. Native `slide.channel.prerequisite_channel_ids`
continues to be managed only by the standard Odoo/M3.3 prerequisite flow.

Public and Portal users have no access to curriculum audit records and M3.4 adds no
public curriculum QWeb route. Officers can inspect the workspace and work on manual
coverage for courses they own; Manager review remains terminal and auditable.

The Universidade do Algarve LESTI 2026/27 plan is included only as a regression-test
shape: programme code `1941`, representative units such as Programação and Base de
Dados II, and the final Estágio/Projeto option group validate the generic data
model. No UAlg-specific production seed, scraper, provider, partnership assumption,
credit decision or automatic syllabus match is shipped. External discovery/import
of curricula belongs to a later provider milestone.

## Content analysis pipeline

Source → unpublished standard content → queued analysis → historical result →
Manager review → standard tags and approved educational links.

Audit/provenance models cover course candidates, source provenance, analysis
requests, immutable processing attempts/results, content relationships, reviewed
course relationships and reviewed curriculum coverage. The transcript on the
standard content record remains editorial; generated transcripts remain in results.
No automatic result overwrites content or publishes a lesson.

## Install and upgrade

Put this repository on `addons_path`, then run:

```bash
odoo -d facodi -i facodi_learning --without-demo=True --stop-after-init
odoo -d facodi -u facodi_learning --stop-after-init
```

Back up the database and matching filestore for an existing deployment. Version
`19.0.1.4.0` added the M3.3 course-mapping audit schema, settings and views through
the normal Odoo module upgrade. Version `19.0.1.4.1` is a schema-neutral M3.3
concurrency hardening patch. Version `19.0.1.5.0` adds the M3.4 external curriculum
reference/unit and reviewed coverage schema plus backend-only workspace and read-only
gap analysis. The M3.4 upgrade is additive: it performs no historical rewrite and
does not fabricate curriculum references or coverage for existing courses.

## Manager workflow

In **eLearning → FACODI Learning → Content Analysis**, manage Jobs, Results and
**Content Mappings** using the existing actions. Sources remain the provenance entry
point for content ingestion. Create a source with provider `manual`, a stable
external identifier and course; **Import unpublished article** creates one draft
article. Replaying ingestion reuses it, including any editorial changes. The Python
`ingest_manual` method can associate existing content in the same course. Imported
provenance is immutable.

On an eLearning content form, **FACODI Analysis → Queue Analysis** creates a
request. The default `local_metadata` provider uses Odoo data only, without
network access. The standard scheduled action processes a capped batch. Managers
can also process jobs; Officers can request/retry jobs in courses they own.

Managers apply or reject tag suggestions explicitly. Applying reuses standard tags
and records who reviewed them and when; rejecting changes no content. Content
mappings are proposed first and reviewed separately. Direct ORM writes cannot
bypass review. Reviewed output is immutable; create a new analysis or relation when
meaning changes.

For course relationships, open a standard eLearning course and use **Find Related
Courses**, or open **FACODI Learning → Course Mapping → Course Mappings**. Managers
review proposed semantic relations there. Approving a prerequisite updates the
standard Odoo prerequisite field after cycle validation; approving other semantic
relations changes no course publication, enrollment or progression state.

For curriculum comparison, open **FACODI Learning → Curriculum Coverage**. Managers
maintain versioned external references/units and review coverage proposals; Officers
can inspect them and create manual evidence for their own FACODI courses. The
standard course form's **Curriculum Coverage** stat button opens only evidence for
that canonical course. Review does not change publication, membership, learner
progress or native prerequisite state.

Students see only approved resource links on the standard lesson detail page and
approved learner-safe related courses on the standard course page. Curriculum
references/coverage remain backend-only. Publication, current website and native
visibility/access rules filter learner targets. Technical fields and all FACODI
audit models remain unavailable to Public/Portal users. The standard fullscreen
training player remains unchanged.

## Provider extensions

Trusted optional addons extend `_get_provider_registry()` on analysis jobs, or
`_get_ingestion_registry()` on sources, calling `super()` in both cases.
Analysis adapters receive a `slide.slide`; ingestion adapters receive a source
and return standard content values. `ingest(values, slide_id=None)` registers by
provider/external identifier/course and forces new content to remain unpublished.

Course Discovery M3.1 itself has no external discovery adapter. Provider-specific
course discovery belongs to a later optional-addon milestone; the core candidate
evaluator, course profile and M3.3 mapping ranker remain deterministic and offline.
M3.4 likewise includes no external curriculum fetcher: references can be curated
manually today, while a future provider may populate the same generic reference/unit
models without changing their editorial meaning.

See [architecture](docs/architecture.md) for normalized output, course-selection,
course-profile, course-mapping, curriculum-coverage and transaction contracts.
Runtime secrets belong in an adapter's deployment environment, never source records
or payloads. No external provider SDK is a core dependency.

## Tests

GitHub Actions installs and upgrades against Odoo 19 + PostgreSQL 16, with a
persistent filestore between runs. Run `--test-tags /facodi_learning` to cover
candidate identity/evaluation/modes/resolution, course-profile schema and
determinism, deterministic course retrieval/ranking, idempotent course proposals,
native prerequisite application and cycle prevention, independent course-mapping
Auto Approve policy, learner-safe course visibility, curriculum identity/lifecycle,
approved-only gap analysis, LESTI-shaped many-to-many coverage, backend/QWeb
boundaries, content analysis/history, ACLs and safe learner links. Tests explicitly
assert that automatic course-selection resolution never publishes a new course,
course mapping never bypasses standard Odoo prerequisite/publication/access
mechanics, and M3.4 does not infer official credit/equivalence/prerequisites from an
external curriculum.

The monorepo consumes this repository as a pinned submodule; addon changes do not
deploy until the consuming repository intentionally updates its pin.

LGPL-3.0.

## Validation evidence

See [validation report](docs/validation.md) for the isolated Community install/upgrade matrix, curriculum validation case, browser checks and remaining deployment boundaries.
