# M3.4 Curriculum Evidence Integrity

M3.4 treats external curricula as versioned reference evidence. These records are not canonical FACODI courses and they are not academic-recognition decisions.

## Identity

A curriculum reference is identified by `(provider, external_id)`. A curricular unit is identified by `(reference_id, external_unit_code)`.

Those identities are immutable after creation. A materially new programme/study-plan revision must use a new stable/versioned external identity rather than rewriting the old reference.

## Correctable source facts before review

Managers may correct normalized source facts while the affected curriculum has no terminal coverage decision. This allows transcription/import corrections before FACODI relies on the source in reviewed evidence.

Reference facts that may be corrected before terminal coverage include institution, programme name/code, academic year/version, source URL and safe source metadata.

Unit facts that may be corrected before terminal coverage include name, source credit value, curricular year, period, classification, option group, sequence and safe source metadata.

`validated_at` is operational revalidation metadata and may continue to change without changing the curriculum identity or reviewed facts.

## Freeze after terminal coverage

A coverage row becomes terminal when it is `approved` or `rejected`.

Once a unit has any terminal coverage, its substantive external facts are immutable. Once any unit belonging to a reference has terminal coverage, the reference's substantive programme/source facts are also immutable.

This prevents later edits from changing the meaning of an already reviewed `facodi.learning.curriculum.coverage` row. New or materially changed source information must be represented as a new versioned curriculum reference/unit identity and reviewed again.

The freeze is enforced in the ORM, not only in the backend views, so RPC/API writes cannot bypass it.

## What is not frozen

The rule does not create a parallel snapshot table and does not make all curriculum metadata permanently immutable from first import. Before terminal coverage, source corrections remain possible. Operational `validated_at` timestamps also remain mutable.

## Academic boundary

Coverage types (`covers`, `partial`, `supports`, `equivalent`) remain internal FACODI editorial evidence. `equivalent` never means official university equivalence, recognition of ECTS, award of credit, transcript status or programme progression.

Curricular year, period, sequence and option groups are source facts only. They do not create native Odoo prerequisites. `slide.channel` remains the canonical FACODI course and `slide.channel.prerequisite_channel_ids` remains the only prerequisite graph.
