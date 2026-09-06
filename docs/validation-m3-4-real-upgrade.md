# M3.4 Real Upgrade Validation — 2026-09-06

This report supplements `docs/validation.md` with an explicit historical upgrade gate for M3.4.

## Upgrade path under test

- Baseline: merged `main` at `1ff81c0585728037dfb24b3310d5905ce38c6fc7`, addon version `19.0.1.4.1`.
- Target: M3.4 branch, addon version `19.0.1.5.0`.
- Runtime: Odoo 19 Community (`odoo:19.0`) and PostgreSQL 16.
- Database: the same PostgreSQL database is installed with the baseline addon, populated with M3.1–M3.3 sentinel records, then upgraded with the M3.4 tree.

## Persisted pre-M3.4 sentinels

`scripts/ci_seed_pre_m34.py` creates only data that exists in the merged M3.1–M3.3 schema:

- one canonical `slide.channel` and one native Odoo prerequisite course;
- two standard `slide.slide` records, including editorial description text;
- one `facodi.learning.course.candidate`;
- one imported `facodi.learning.source` linked to existing content;
- one completed local analysis job/result;
- one approved content-level `facodi.learning.mapping`;
- one approved `facodi.learning.course.mapping`;
- the native `slide.channel.prerequisite_channel_ids` relationship.

The seed commits before the addon upgrade so the verification exercises persisted historical state rather than one transaction containing both versions.

## Post-upgrade assertions

`scripts/ci_verify_post_m34.py` verifies after `-u facodi_learning` with the M3.4 code that:

- the canonical course and both standard content records still exist;
- editorial slide description is unchanged;
- the native Odoo prerequisite is unchanged;
- the M3.1 candidate remains present;
- the source remains imported and linked to the same standard content;
- analysis history remains present;
- the approved content mapping remains approved;
- the approved course mapping remains approved;
- all three M3.4 curriculum models are installed;
- the upgrade fabricates **zero** `curriculum.reference`, `curriculum.unit`, or `curriculum.coverage` rows.

This proves that M3.4 is additive with respect to the representative persisted M3.1–M3.3 state covered by these sentinels. It is not a claim that arbitrary third-party database customizations are migration-tested.

## Harness debugging evidence

The first strengthened CI head was `bbcb7a71052a9ff50fe220a96d9af74adca05762`, GitHub Actions run `34027007458`. The baseline install succeeded, but the run stopped in the seed harness before any M3.4 upgrade because the Docker invocation passed `shell` as the image command and `/entrypoint.sh` attempted `exec shell`, producing:

```text
/entrypoint.sh: line 49: exec: shell: not found
```

This was a CI-harness invocation error, not an addon migration failure. No production model/service code was changed to address it.

Commit `534fd9ac7afd342ee2e8e85fcea847a51ca9fa36` corrected the two shell invocations to `odoo shell`.

GitHub Actions run `34027153404` then passed every gate on that exact head:

1. install merge-base/main addon — **success**;
2. seed persisted pre-M3.4 sentinels — **success**;
3. upgrade the same database from `19.0.1.4.1` to the M3.4 tree — **success**;
4. verify preservation and zero fabricated curriculum rows — **success**;
5. independent clean install of the M3.4 tree with the full addon tests — **success**;
6. same-database re-upgrade/regression suite on the M3.4 tree — **success**.

## Release boundary

M3.4 remains a curriculum **reference and coverage** layer only. The upgrade does not create official academic equivalence, award ECTS, infer university prerequisites, enroll learners in an external programme, or create a second learning-path/progression engine. `slide.channel` remains the canonical course and native Odoo prerequisites remain authoritative.

The commit that adds this report must itself pass the same strengthened CI before the M3.4 pull request is considered merge-ready.
