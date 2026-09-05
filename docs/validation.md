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
