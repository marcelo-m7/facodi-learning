# FACODI public catalogue: editorial review queue

Snapshot of the FACODI Odoo instance on 2026-10-03. This is a triage aid, not an approval of any resource or an academic equivalence assessment. Recount in Odoo before acting: publication and review states can change independently of this file.

## Current state before reconciliation

- 23 published courses and 551 published slides are visible in the FACODI catalogue.
- 539 content-publication reviews are pending. Of these, 538 refer to published slides; one refers to content that is not currently public.
- Thirteen published slides in **Gastronomia e Inovação Alimentar** (course 41; slide IDs 1049–1061) have no review row. This course and its slides have no `website_id`, so the previous publication guard did not associate them with FACODI. The domain-specific guard and backfill must be deployed, then `website(1).action_facodi_enable_publication_review()` run and checked for exactly one pending review per unapproved public slide.
- A pending review is a request for human assessment. Historical labels such as `auto_reviewed` and a numeric confidence score are not an approval, a rights check, or evidence of academic coverage.

## Review order

1. **Publication provenance and rights.** For each pending review, confirm the source URL, author, permitted-use basis, editorial purpose and actual content. Decide through the Manager review action; do not populate evidence from historical scores.
2. **Course fit.** Start with the thin public courses: Cibersegurança; Communication Design III/IV; Multimedia and Interaction Design; Web Design; Motion Design; Design Foundations; and Communication Design I each had one resource. A one-resource course is a provisional collection, not evidence of a complete course.
3. **Duplicate titles.** Check whether these are legitimate cross-course reuse or accidental copies: 777/800, 778/799, 801/794 and 1039/798. Compare canonical source identity before removing or merging any record.
4. **Curricular coverage.** Retain explicit gaps in the 122-unit LESTI reference; 101 units had no approved coverage in the public audit. Add mappings only from validated sources and approved evidence. Never infer ECTS recognition from topic similarity.

## Completion criteria

- Every public slide has an accountable review decision based on verifiable source and rights evidence, or is deliberately unpublished.
- Every published course has a truthful scope and useful ordering; thin collections are clearly labelled or expanded with reviewed resources.
- Duplicates have a documented source and reason for appearing in more than one course.
- Public curriculum coverage matches approved records; gaps remain visible until a Manager approves evidence.
- Public PT, ES and FR pages are reviewed in context, including editor-owned pages and policy text. The cookie inventory must be checked against actual browser traffic before its policy is described as complete.
