# Validation — 2026-09-05

## M3.3 Course Mapping Engine

M3.3 was validated against Odoo 19 Community (`19.0-20260817`) and PostgreSQL 16
with the repository CI's clean-install and same-database upgrade gates.

The Task 6 end-to-end UI contract was first committed as a deliberate RED on exact
SHA `cb5a73848f07129e278fb2941b78175b9da27fc2`. GitHub Actions run `33995425071`
reported **0 failures and 5 errors**, all five matching the intentionally missing
contract: Course Mapping action/menu/views, the two `slide.channel` workspace
actions and the learner-facing related-course QWeb view. Previously implemented
M3.3 ranking, prerequisite, policy and visibility tests continued to execute.

The first complete functional GREEN was exact SHA
`2f0f7ecef0cbb619d50ed5a536bf027a71cd8124`, GitHub Actions run `33995669348`.
Both gates passed:

- clean install of `facodi_learning` with the full addon test suite;
- upgrade of the same addon/database with the regression suite.

That GREEN validates the M3.3 functional surface loaded by Odoo, including:

- `facodi.learning.course.mapping` audit lifecycle, constraints and ACL boundaries;
- deterministic `course-mapping-v1` retrieval/ranking from M3.2 profiles;
- idempotent directed proposal generation;
- no learner membership/progress input to ranking;
- native `slide.channel.prerequisite_channel_ids` application for reviewed
  prerequisite mappings;
- direct and transitive prerequisite-cycle prevention;
- independent fail-closed course-mapping Auto Approve policy;
- hard safe-type allowlist and Manager-only automatic terminal decisions;
- immutable automatic decision snapshot/version evidence;
- Public/Portal denial on the raw course-mapping audit model;
- approved-only learner semantic relations with native publication, website and
  `slide.channel.is_visible` filtering;
- backend Course Mapping search/list/form views and Manager review buttons;
- standard `slide.channel` actions for generation and relation workspace;
- distinct Content Mappings and Course Mappings navigation;
- inherited standard course-page QWeb block for learner-safe related courses.

### Final hardening and release gate

The implementation was hardened after the first functional GREEN rather than
freezing the earlier test result as release evidence.

Prerequisite application first gained deterministic source/target row locking before
re-reading the native prerequisite graph, checking for cycles and writing the
standard field. Exact SHA `4497c73b20b3a30b07f21436b5cc1e1f381a0522`, GitHub
Actions run `33996049568`, passed both clean-install and upgrade gates.

Generated proposal provenance is server-owned. Direct ORM `create()` accepts only
manual proposals and rejects forged `origin="analysis"` or `ranking_version` values;
the deterministic engine uses the private `_create_generated()` boundary. Exact SHA
`be38c5d00bcbf95647230caf1c438ac0c62647ae`, GitHub Actions run `33996472834`,
passed both gates.

Bounded retrieval then received a dedicated RED test on exact SHA
`a6ab7ed17d3587716110ad82c3895ea1ea93ca73`. Run `33996577166` reported
**1 failure and 0 errors of 100 tests** because a high-sequence course sharing a
standard course tag with the source was excluded by the previous `sequence,id`
pre-limit. The implementation now retrieves website-compatible active courses with
shared standard course tags first, then fills any remaining bounded slots using the
stable `sequence,id` fallback. Exact SHA
`c064c968b3338a075064fe26ec61554bfecf0811`, GitHub Actions run `33996912592`,
passed both the clean-install and same-database upgrade gates.

The PR review identified that source/target row locks alone cannot serialize two
FACODI prerequisite writes with disjoint endpoints that jointly close a larger
cycle. A deliberate RED was committed at exact SHA
`63d3b403a8abf658f0ed1f7722b468894fc8facb`. Pull-request CI run `33997302875`
reported **1 failure and 0 errors of 101 tests**, exclusively because graph-wide
serialization was absent. The review path now acquires a database-transaction-level,
fail-closed FACODI advisory lock before source/target row locks, cache invalidation,
cycle validation and the native prerequisite write. This serializes prerequisite
mutations made through the FACODI review path even when the new edges have disjoint
endpoints. Exact SHA `2fedc8de95ca6c6a38d0d3463ef3ddd22891e2de`, pull-request
CI run `33997458255`, passed both clean-install and same-database upgrade gates.
The advisory lock is only a concurrency guard for FACODI review operations; native
Odoo prerequisite edits performed outside this path remain ordinary Odoo writes.
The only prerequisite truth continues to be `slide.channel.prerequisite_channel_ids`.

A later PR integrity review found that server-owned generated proposals could no
longer be forged at creation time, but their proposed `confidence` or `evidence`
could still be rewritten through ordinary ORM `write()`. That could falsify ranking
evidence or influence a later automatic decision. A deliberate RED at exact SHA
`48c8a4d7bcde4012dc2754ef39a0597afbf4be63`, pull-request CI run `33997693435`,
reported **1 failure and 0 errors of 102 tests** exclusively because the expected
`AccessError` was not raised. Ordinary writes now treat every `origin="analysis"`
proposal as immutable evidence from creation onward; manual proposed mappings remain
editable, while Manager review and Auto Approve continue through the controlled
internal write paths. Exact SHA `5d25c83942f45c7235c4241deeaf3dd5d66e601f`,
pull-request CI run `33997832186`, passed both clean-install and same-database
upgrade gates.

PR #6 was subsequently merged to `main` as merge commit
`43909fe915fc7ff11b54f33fb8aae9e4e7ae9f08`. One review finding remained for a
follow-up patch: proposal generation still used a non-atomic `search -> create`
boundary. Two requests for the same source course could both observe no row and
compete on the unique directed-triple constraint, causing the losing transaction to
fail and potentially roll back proposals created earlier in that request.

### Post-merge concurrency patch — 19.0.1.4.1

A dedicated RED was added on exact SHA
`c180d9bc9befb50d9da16da66d3dd2c660b57d20`. GitHub Actions run `33998870904`
reported **1 failure and 0 errors of 103 tests**: while another PostgreSQL session
held the expected per-source transaction advisory lock, mapping generation did not
raise the required retryable `ValidationError` and therefore was not serialized.

The implementation now acquires `pg_try_advisory_xact_lock` for the source course
immediately after normal read/write access checks and before profile retrieval,
proposal searches or inserts. The lock is scoped by source course, so unrelated
courses remain parallel. If the same course is already being generated in another
transaction, FACODI fails closed before creating any proposal and instructs the
caller to retry. This deliberately avoids waiting and then relying on a same-
transaction re-fetch under PostgreSQL/Odoo `REPEATABLE READ`. A later retry uses the
normal idempotent search path and reuses existing relations.

Exact SHA `f9e7823e5abeb0cafe3bc8d5cda0754e9179eef0`, GitHub Actions run
`33999011617`, passed both gates:

- clean install with the full FACODI addon tests: success;
- same-database addon upgrade/regression suite: success.

The patch is schema-neutral and is released as `19.0.1.4.1`; it requires no data
migration or historical rewrite. The final version/documentation head is required
to pass the same two gates before the follow-up pull request is considered
merge-ready.

No M3.3 test or implementation introduces AI/embedding calls, vector storage,
learner-personalized ranking, automatic course publication or a second prerequisite
graph. Course relations are additive audit records; prerequisite truth remains the
standard Odoo field.

```sh
odoo -d facodi_test -i facodi_learning --without-demo=True --workers=0 --test-tags /facodi_learning --stop-after-init
odoo -d facodi_test -u facodi_learning --without-demo=True --workers=0 --test-tags /facodi_learning --stop-after-init
```

## Portability, security and content-analysis pipeline

Earlier validation started from main `4af9212` with isolated PostgreSQL 16 and
Odoo 19.0 Community, without Enterprise addons or network provider SDKs.

- Independent clean install and upgrades passed for the content-analysis baseline.
- Coverage includes provider validation, errors (including empty exception text), retries and immutable attempts/results, cron batch limits, direct ORM/context review bypass, ownership, public/Portal denial, taxonomy approval/rejection, provenance, duplicate/self mappings, relation deletion protection, source idempotency and failure rollback, and approved student links with native visibility/multiwebsite checks.
- Two independent database transactions demonstrated that a locked analysis job is skipped by the second processor; after completion, repeated processing leaves exactly one attempt and result.
- A database installed from the older baseline was upgraded while preserving editorial content, transcript, historical result and approved mapping. New evidence fields are additive; historical reviewer/timestamps that were never recorded are not invented.
- A real Gemini API smoke succeeded with `gemini-3.5-flash-lite`. Its structured output was normalized through the provider registry into an immutable result. Content stayed unpublished and tags were created/applied only by an explicit Manager action. The prompt used synthetic arithmetic content; no private website data was transmitted.
- The core remains provider-neutral. The API smoke and trusted ingestion adapters were temporary validation harnesses, not bundled production Gemini or YouTube integrations.

## User-supplied sources

Public metadata inspected on 2026-09-05:

| Reference | Confirmed scope |
| --- | --- |
| [Matemateca](https://www.youtube.com/@Matemateca) | Matemateca - Ester Velasquez; channel `UCfwhmgRZqb1MHNfUHMQNUJg` |
| [Probability and Statistics playlist](https://www.youtube.com/playlist?list=PLrOyM49ctTx8HWnxWRBtKrfcuf7ew_3nm) | Public preview yielded 40 unique videos; first examples are by Professor Douglas Maioli. This is a preview count, not a completeness guarantee. |
| [Professor Aquino playlists](https://www.youtube.com/@LCMAquino/playlists) | Professor Aquino - Matemática; channel `UCKuwqceoy_TPnGG_5AnI7DQ` |
| [UAlg course plan](https://www.ualg.pt/curso/1941/plano) | Academic-year selector includes 2026/27; mathematics subjects include Linear Algebra/Analytic Geometry, Mathematical Analysis I/II, and Probability/Statistics. |

Two real examples were ingested through a temporary trusted adapter into
standard `slide.slide` video records in an unpublished disposable course:

- [O que é Estatística?](https://www.youtube.com/watch?v=snXf8YT7L3U)
- [Introdução à Probabilidade](https://www.youtube.com/watch?v=u8Ltc5645Nk)

The source rows retain original URL, video ID, author, playlist and inspection
date. Replaying ingestion reused the same two source/content records. Even an
adapter requesting publication was forced to create unpublished content. No
curriculum mapping was inferred or approved from title similarity. Videos,
transcripts and full copyrighted descriptions were not copied.

## Boundaries

No bulk YouTube harvesting, scheduled external synchronization, transcript
retrieval or production AI adapter is claimed. A separate adapter addon can use
the tested registry; it must implement timeouts, credentials, access/rights and
normalization. The source registry provides provenance and idempotency today.
The UAlg reference is evidence for future editorial review, not an asserted
FACODI partnership or an automatically matched syllabus.

Student content links are exposed in the standard detailed lesson page. M3.3 adds
only reviewed related-course links to the standard course page. The fullscreen
player is preserved; no parallel navigation/progression engine was added. Native
Odoo prerequisites remain authoritative. No deployment or content mutation was
made on Odoo Online. CI status is reported by the repository's actual GitHub
Actions runs.
