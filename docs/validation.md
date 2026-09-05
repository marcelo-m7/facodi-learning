# Validation — 2026-09-05

## Portability, security and pipeline

Started from main `4af9212`. Executed with isolated PostgreSQL 16 and Odoo 19.0
Community (19.0-20260817), without Enterprise addons or network provider SDKs.

- Independent clean install and upgrades pass. Final Learning suite: **25 tests**, zero failures/errors.
- Clean combined install passed; final combined upgrade: **33 tests**, zero failures/errors.
- Coverage includes provider validation, errors (including empty exception text), retries and immutable attempts/results, cron batch limits, direct ORM/context review bypass, ownership, public/Portal denial, taxonomy approval/rejection, provenance, duplicate/self mappings, relation deletion protection, source idempotency and failure rollback, and approved student links with native visibility/multiwebsite checks.
- Two independent database transactions: a locked job is skipped by the second processor; after completion, repeated processing leaves exactly one attempt and result.
- Upgraded a database installed from old main, preserving editorial content, transcript, historical result and approved mapping. New evidence fields are additive; historical reviewer/timestamps that were never recorded are not invented.
- Real Gemini API smoke succeeded with `gemini-3.5-flash-lite`. Its structured output was normalized through the provider registry into an immutable result. Content stayed unpublished and tags were created/applied only by an explicit Manager action. The prompt used synthetic arithmetic content; no private website data was transmitted.
- The core remains provider-neutral. The API smoke and trusted ingestion adapters were temporary validation harnesses, not a bundled production Gemini or YouTube integration.

```sh
odoo -d facodi_test -i facodi_learning --without-demo=True --workers=0 --test-tags /facodi_learning --stop-after-init
odoo -d facodi_test -u facodi_learning --without-demo=True --workers=0 --test-tags /facodi_learning --stop-after-init
```

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

Student links are exposed in the standard detailed lesson page. The fullscreen
player is preserved; no parallel navigation/progression or prerequisite engine
was added. No deployment or content mutation was made on Odoo Online. CI status
is reported by the PR's actual GitHub Actions runs.
