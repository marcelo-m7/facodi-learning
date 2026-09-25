# SDD ledger — plan: marcelo-m7/facodi-theme:docs/superpowers/plans/2026-09-25-facodi-learning-interfaces-d1.md

Pre-flight: this branch owns Tasks 3, 4, 5 and 7 only; theme-side selectors are consumed later from exact green SHAs.
Ruling: execute in an isolated GitHub feature branch because this harness has no network-backed local worktree. Cost if wrong: slower RED/GREEN feedback; exact-head CI is the integration authority.

Task 3: complete (CI run 36186833772 → success; catalogue structure, i18n, real upgrade and current install gates passed).

Task 4: Ruling: enabling TestCurriculumPublicUnits exposed a preexisting bootstrap lifecycle bug introduced by current publication governance. Fixed ensure_lesti_2026_27 at the source to validate/publish through reviewed actions and updated stale tests to archive via action_archive. Cost if wrong: curated LESTI bootstrap could fail or republish incorrectly; TestCurriculumBootstrap is now part of exact-head CI.
