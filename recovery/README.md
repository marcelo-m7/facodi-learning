# FACODI disaster-recovery assets

This directory stores **versioned recovery evidence**, not a second production
database.

## 2026-09-28 Odoo reset

The FACODI Odoo database was reset and the original production records were lost.
A surviving historical Supabase project (`Open2`, ref
`wvkjainfwsyiyfcmbtid`) still contained enough data to reconstruct the main
LESTI learning catalogue.

The snapshot `open2_lesti_2026-09-28.json` was captured before further
reconstruction work. It contains:

- the historical LESTI course record;
- 36 LESTI playlist records;
- 353 playlist/video associations with their latest available AI enrichment;
- 15 legacy editorial/content pages retained as historical source material.

Only seven LESTI playlists had recoverable video content. Four were historically
`auto_reviewed` at confidence 0.88; three were marked `needs_review`.

## Restore procedure

Run `scripts/recover_open2_lesti.py` inside an Odoo shell after
`facodi_learning`, Website and eLearning are installed and after the **current
official curriculum reference** has been restored.

Example:

```bash
FACODI_RECOVERY_SNAPSHOT=/mnt/extra-addons/facodi_learning/recovery/open2_lesti_2026-09-28.json \
  odoo shell -d facodi < /mnt/extra-addons/facodi_learning/scripts/recover_open2_lesti.py
```

The script is idempotent and uses deterministic `__import__` XML IDs. It:

1. recreates/updates the seven recoverable LESTI eLearning courses;
2. recreates/updates the 353 external YouTube learning-resource records;
3. links courses to current curriculum units by `external_unit_code`;
4. approves only mappings whose historical source state was
   `auto_reviewed`;
5. leaves `needs_review` mappings proposed for human review.

Recovered YouTube resources are intentionally represented as external article
links during disaster restoration. This avoids making hundreds of synchronous
provider requests while the database is being rebuilt. They can later be
promoted selectively through the normal FACODI analysis/editorial pipeline.

## Academic boundary

The snapshot is learning-content evidence only.

A recovered mapping must **never** be interpreted as official academic
equivalence, ECTS recognition, transcript credit, curriculum completion or a
substitute for the university's current programme. The current Odoo curriculum
reference remains authoritative for institutional facts.

## Legacy pages

The snapshot includes historical pages such as privacy, cookies, legal notice,
infrastructure and project information. They are preserved for editorial
recovery, but must not be republished blindly: some refer to previous domains,
the previous React/Supabase architecture, or superseded legal/technical facts.


## Extended public-catalog recovery

A second, broader snapshot, `open2_public_catalog_2026-09-28.json`, preserves the
public historical learning catalogue without copying private profiles, contact
messages, direct messages or user submissions.

It currently contains:

- 2 historical course records;
- 87 historical curriculum-unit rows;
- 10 category rows;
- 86 public playlists;
- 616 playlist/resource associations.

The public associations break down as follows:

- LESTI: 353 associations / 329 unique videos across 7 playlists with content;
- LDC (historical playlist code; canonical course code LDCOM): 52 associations /
  49 unique videos across 8 playlists with content;
- generic community playlists: 116 associations / 106 unique videos across
  7 playlists with content;
- historical Odoo 18 HR playlist: 95 associations / 95 unique videos.

Use `scripts/recover_open2_public_catalog.py` for the wider restore. It
normalizes the historical `LDC` playlist code to `LDCOM`, keeps
`needs_review` material as draft except for the already-recovered LESTI
policy, and deliberately restores the Odoo 18 material as draft because its
version context is stale relative to the current Odoo 19 implementation.

On 2026-09-28 the live Odoo recovery also enriched all 353 restored LESTI
resource records from the saved AI metadata, including optimized titles,
summaries, semantic tags, source provenance, historical review state and the
academic-boundary notice.
