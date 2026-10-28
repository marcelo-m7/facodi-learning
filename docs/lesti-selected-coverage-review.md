# Selected-unit curriculum coverage review — UAlg/LESTI pilot

This increment reuses the existing `curriculum-coverage-ranking-v1` engine and Odoo 19's **internal eLearning Manager** review workflow. It does not introduce a competing recommender in the Tube O2 frontend or an autonomous academic-equivalence classifier.

## Editorial workflow

1. In **FACODI Learning → Curriculum → Curricular Units**, search for the validated Universidade do Algarve / LESTI reference for academic year 2026/27.
2. Select the relevant pilot units, beginning with **Pré-Cálculo/Análise Matemática** and **Aprendizagem Automática**, using the actual unit names and immutable `external_unit_code` values from Odoo. Never infer or invent a unit identifier.
3. From **Action**, choose **Suggest coverage for selected units (max 10)**. The server verifies the eLearning Manager group and refuses empty selections or more than ten records.
4. The existing deterministic engine ranks published courses by title and unit-name token recall. It checks all published courses before taking the top five per selected unit; records below the existing confidence threshold are not created.
5. Only **new, immutable, versioned** `facodi.learning.curriculum.coverage` records with `state=proposed` and `origin=analysis` are created. Existing proposals and terminal decisions are never duplicated or reopened. Reviewers receive the matching proposal list (or existing pending rows on replay).
6. Review individual evidence and canonical course content, then explicitly **Approve** or **Reject** in the Odoo form. Unapproved proposals do not appear in the public Tube O2 Atlas.
7. After formal review, confirm the Atlas shows only approved course associations. No action in this feature can award ECTS, define Odoo prerequisites, or declare academic equivalence.

**Important:** this is deterministic proposal generation, **not generative AI** and not authoritative assessment of coverage. The current evaluation version and scoring signals are stored with evidence for human review; future embeddings/FAISS recommendations must be separate versioned evidence and equally review-gated.

## Security and limits

- Only managers in `website_slides.group_website_slides_manager` (and superusers) can execute the batch method. The bound Odoo server action is also restricted to this group. Direct RPC calls are checked again at the model method.
- Maximum **10 selected units per invocation**, at most **5 ranked candidates per unit**. If any unit is outside the allowed record rules, the method must fail rather than escalate with `sudo()`.
- No background cron, scheduled generation, automatic approval, state transitions or opening of the write-capable Supabase/Odoo connector is introduced.
- The `monynha@facodi.com` integration account should remain **read-only** for published curricular data. It must **not** be granted eLearning Manager privileges to run this action.
- Do not execute this action on production until an administrator has verified source provenance, unit identities, and review capacity.

## Technical verification / rollout

- Verify Python syntax, XML data validity and new Odoo `TransactionCase` tests, especially group denial, no selection, 11-unit cap, scoped creation, no duplicates, replay and `proposed` state.
- Install/upgrade the module in a staging Odoo 19 database using the pinned addon revision; test the list action visibility for Manager vs Officer. Existing per-unit and per-reference buttons must still work.
- Only after Odoo staging QA, deploy the addon via the normal `facodi-deploy` pin workflow and `-u facodi_learning`, then review proposals in the Odoo backend. **Do not merge this branch into FACODI production without that gate.**
- Validate that the public `facodi-curriculum` Edge Function still exposes only `state=approved` relations and that the Tube O2 Atlas is unchanged until editorial approval.
