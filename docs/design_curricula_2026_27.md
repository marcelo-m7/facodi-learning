# UAlg design curricula 2026/27

FACODI publishes two additional official curriculum references for the University of Algarve:

- **1930 — Design e Tecnologias Multimédia (CTeSP)** — source: https://www.ualg.pt/curso/1930/plano
- **1454 — Design de Comunicação (Licenciatura)** — source: https://www.ualg.pt/curso/1454/plano

The official UAlg study plans are canonical for unit names, codes, ECTS, curricular year and semester.

Recovered Open2/Supabase resources are a separate evidence layer. They can create only
`supports` coverage in FACODI. Coverage never means academic equivalence, accreditation,
ECTS recognition, assessment, progression or replacement of the official programme.

## Seeded public support

For Design e Tecnologias Multimédia, the bootstrap currently approves conservative support for:

- 19301001 — Fundamentos do Design
- 19301006 — Design de Interação
- 19301007 — Tipografia e Design Editorial
- 19301008 — Motion Design
- 19301009 — Web Design

For Design de Comunicação, exact historical unit-code mappings are retained. Stronger reviewed
relations (including Tipografia I and the curated art-history collection) can be public; weaker
historical associations remain proposed for editorial review.

The operation is idempotent and is run on fresh installation and by the 19.0.1.124.0 migration.

The Interaction Design seed uses two historical Open2 resources whose latest AI enrichment
explicitly identifies UI, UX, user experience, Figma and prototyping. They remain FACODI
learning support only; the official UAlg study plan stays canonical.


The Design Foundations seed now uses the recovered Nadine Fronza resource whose latest
Open2 enrichment explicitly identifies graphic-design principles and beginner design education.
A dedicated DTM-facing FACODI course avoids presenting an LDCOM-labelled course as the
primary support surface for the 1930 programme.


AI-enriched semantic labels selected from the historical Open2 catalogue are also reconciled
into native Odoo `slide.tag` records for the seeded DTM resources. Tags improve native
catalogue discovery; they are descriptive metadata only and do not alter academic coverage.

## Deterministic recovered content

The clean-install bootstrap now carries the reviewed Open2 recovery needed for the two
public Design de Comunicação supports that are approved by FACODI curation:

- **14541153 — Tipografia I:** 20 typography resources. The unrelated historical
  developer-career video is explicitly excluded.
- **14541196 — História da Arte Moderna e Contemporânea:** 22 curated art-history
  resources. The vector-mathematics and Damascus-travel outliers are explicitly excluded.

The Typography I collection is also reused as supports evidence for
**19301007 — Tipografia e Design Editorial** in Design e Tecnologias Multimédia.
The same canonical slide.channel is reused; FACODI does not duplicate the learning
resource collection for each curriculum reference.

