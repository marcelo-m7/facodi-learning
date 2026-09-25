# SDD ledger — plan: marcelo-m7/facodi-theme:docs/superpowers/plans/2026-09-25-facodi-learning-interfaces-d1.md

Pre-flight: this branch owns Tasks 3, 4, 5 and 7 only; theme-side selectors are consumed later from exact green SHAs.
Ruling: execute in an isolated GitHub feature branch because this harness has no network-backed local worktree. Cost if wrong: slower RED/GREEN feedback; exact-head CI is the integration authority.

Task 3: complete (CI run 36186833772 → success; catalogue structure, i18n, real upgrade and current install gates passed).

Task 4: Ruling: enabling TestCurriculumPublicUnits exposed a preexisting bootstrap lifecycle bug introduced by current publication governance. Fixed ensure_lesti_2026_27 at the source to validate/publish through reviewed actions and updated stale tests to archive via action_archive. Cost if wrong: curated LESTI bootstrap could fail or republish incorrectly; TestCurriculumBootstrap is now part of exact-head CI.

Task 4: Ruling: enabling the previously unexecuted public-unit suite exposed a stale assertion comparing a Python list to an Odoo recordset. Compare the list to [self.reference] so the test still proves exactly one public validated reference. Cost if wrong: public-map visibility regression; the same suite covers hidden-reference exclusion and exact URL/coverage values.

Task 4: complete (CI run 36188839045 → success; D1 Roadmap/UC/module detail, lifecycle regression, real upgrade and 123-test current-install gates passed).

Task 5: Ruling: the reviewed course-to-curriculum block is owned by website_curriculum.xml in the current repository, while the generic course contribution CTA is in website_slides.xml. Keep that ownership and add semantic hooks in place rather than moving markup. Cost if wrong: styling spans two QWeb files, but data queries and view inheritance remain unchanged and are covered by the static/Odoo gates.

Task 5: complete (CI run 36189366107 → success; reviewed course curriculum sheet, contribution callout, i18n, real upgrade and current-install gates passed).

Task 7: complete (CI run 36190611525 → success; release 19.0.1.22.0, D1 static/i18n contracts, pre-M3.4 real upgrade, 123-test current install and same-tree upgrade passed).
