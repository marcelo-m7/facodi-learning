# M3.2 Course Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, non-persistent FACODI course profile for every canonical Odoo `slide.channel`, aggregating standard course/content metadata and safe FACODI enrichment signals for later retrieval and mapping.

**Architecture:** Keep `slide.channel` and `slide.slide` authoritative. Add a focused pure-ish service in `facodi_learning/services/course_profile.py` and expose it through a private `_facodi_course_profile()` method on a thin `slide.channel` extension. The profile is computed on demand, JSON-serializable, versioned, deterministic for the same database state/caller, and contains no learner/member/progress data.

**Tech Stack:** Odoo 19 Community, Python ORM, `website_slides`, existing FACODI analysis/mapping models, Odoo `html2plaintext`, PostgreSQL 16 CI.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-learning-course-selection-mapping-design.md` sections 9, 17, 20, 23.2, 24 and 25/M3.2.

## Global Constraints

- Odoo 19 Community standard `slide.channel` is the canonical course record.
- Odoo standard `slide.slide`, course tags/groups and native prerequisites remain canonical.
- M3.2 must not introduce `facodi.learning.course.profile` or any second editable course record.
- M3.2 must work without external AI, embeddings, network providers or additional worker frameworks.
- The profile must not include learner-level progress, partner/member identities, emails, invitations, votes or per-user completion state.
- Only safe aggregate FACODI enrichment may be included; raw provider payloads, transcripts and generated summaries are excluded from the baseline schema.
- Profile generation must not publish courses, enroll learners or mutate canonical course/content records.
- Existing M2/M3.1 analysis, ingestion, mapping and course-selection behavior must remain unchanged.
- Release gate remains clean Odoo 19 install, ORM/security tests, addon upgrade and regression tests on the exact head.
- M3.2 is an internal foundation for M3.3 and adds no learner-facing UI.

---

## File Structure

### Create

- `facodi_learning/services/course_profile.py`
  - Owns `COURSE_PROFILE_VERSION`, text normalization, safe aggregation helpers and `build_course_profile(channel)`.
  - Must not define Odoo models or persistent fields.

- `facodi_learning/models/slide_channel.py`
  - Thin Odoo extension of `slide.channel` exposing private `_facodi_course_profile()` only.
  - Delegates to the service; contains no aggregation logic.

- `facodi_learning/tests/test_course_profile.py`
  - Full M3.2 behavioral contract and regression fixtures.

### Modify

- `facodi_learning/services/__init__.py`
  - Export `COURSE_PROFILE_VERSION` and `build_course_profile`.

- `facodi_learning/models/__init__.py`
  - Import the new `slide_channel` extension.

- `facodi_learning/tests/__init__.py`
  - Import `test_course_profile`.

- `facodi_learning/__manifest__.py`
  - Bump addon version from `19.0.1.2.0` to `19.0.1.3.0` after M3.2 behavior is green.

- `README.md`
  - Document the computed Course Profile capability and explicit no-persistence/no-learner-data boundary.

- `docs/architecture.md`
  - Add the M3.2 data-flow and stable profile schema summary.

## Stable Profile Contract

`build_course_profile(channel)` and `channel._facodi_course_profile()` return one dictionary per singleton course with this exact top-level shape:

```python
{
    "schema_version": "course-profile-v1",
    "channel": {
        "id": 42,
        "name": "Databases",
        "channel_type": "training",
        "active": True,
        "website_id": 1,
        "website_published": False,
        "visibility": "public",
        "enroll": "public",
        "description": "Course description as plain text",
        "short_description": "Short description as plain text",
        "detailed_description": "Detailed description as plain text",
    },
    "course_tags": [
        {
            "id": 7,
            "name": "Databases",
            "group_id": 2,
            "group_name": "Topic",
        }
    ],
    "prerequisite_channel_ids": [5],
    "structure": {
        "section_count": 2,
        "content_count": 5,
        "total_duration": 3.5,
        "category_counts": {
            "article": 1,
            "document": 1,
            "infographic": 0,
            "quiz": 1,
            "video": 2,
        },
    },
    "sections": [
        {
            "id": 101,
            "name": "Foundations",
            "sequence": 0,
            "content_ids": [102, 103],
            "duration": 1.5,
        }
    ],
    "contents": [
        {
            "id": 102,
            "name": "Relational Model",
            "sequence": 1,
            "section_id": 101,
            "slide_category": "article",
            "slide_type": "article",
            "completion_time": 0.5,
            "tag_ids": [11],
            "tag_names": ["SQL"],
        }
    ],
    "analysis": {
        "analyzed_content_count": 3,
        "detected_languages": ["en", "pt"],
    },
    "approved_content_relations": {
        "outgoing": [
            {
                "target_channel_id": 77,
                "mapping_type": "related",
                "count": 2,
            }
        ],
        "incoming": [
            {
                "source_channel_id": 88,
                "mapping_type": "supports",
                "count": 1,
            }
        ],
    },
}
```

Contract rules:

- `course_tags` sort by standard Odoo tag order `(group_sequence, sequence, id)`.
- `prerequisite_channel_ids` sort numerically.
- `sections` sort by `(sequence, id)`.
- `contents` sort by `(sequence, id)` and exclude `is_category=True` records.
- Each section `content_ids` follows the same `(sequence, id)` ordering.
- `tag_ids` and `tag_names` use deterministic tag ordering by `(name.casefold(), id)`.
- `category_counts` always contains exactly the five Odoo `slide_category` keys shown above, including zeros.
- `total_duration` uses the standard Odoo `slide.channel.total_time` value converted to `float`.
- Analysis language signals come from the latest immutable analysis result for each content item, ordered by `create_date desc, id desc`; only non-empty `detected_language` values are aggregated.
- `analysis` exposes no `summary`, `transcript`, `raw_payload`, provider token, model prompt or learner information.
- Content mappings contribute only when `state == "approved"`.
- Proposed/rejected mappings never affect the profile.
- Mapping aggregation is course-level evidence grouped by other channel and `mapping_type`; raw content mapping IDs are not exposed.
- The service performs no writes and no `sudo()` elevation.
- The service is called on a singleton record and raises through normal Odoo access behavior if the caller cannot read required records.

---

### Task 1: Lock the Course Profile contract with RED tests

**Files:**
- Create: `facodi_learning/tests/test_course_profile.py`
- Modify: `facodi_learning/tests/__init__.py`

**Interfaces:**
- Consumes: standard `slide.channel`, `slide.slide`, `slide.channel.tag`, `slide.tag`, `facodi.learning.analysis.result`, `facodi.learning.mapping`.
- Produces: failing behavioral contract for `slide.channel._facodi_course_profile()` and exact schema/version expected by later tasks.

- [ ] **Step 1: Import the new test module**

Append to `facodi_learning/tests/__init__.py`:

```python
from . import test_course_profile
```

- [ ] **Step 2: Create the baseline test class and realistic Manager**

Create `facodi_learning/tests/test_course_profile.py` with imports and fixture:

```python
from odoo import Command
from odoo.tests import TransactionCase


class TestCourseProfile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Course Profile Manager",
                "login": "course-profile-manager",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "website_slides.group_website_slides_manager"
                            ).id,
                        ]
                    )
                ],
            }
        )
        cls.ProfileChannel = cls.env["slide.channel"].with_user(cls.manager)
        cls.ProfileSlide = cls.env["slide.slide"].with_user(cls.manager)
```

- [ ] **Step 3: Add the empty-course schema test**

Add:

```python
def test_empty_course_profile_has_stable_schema(self):
    channel = self.ProfileChannel.create({"name": "Empty Course"})

    profile = channel._facodi_course_profile()

    self.assertEqual(profile["schema_version"], "course-profile-v1")
    self.assertEqual(profile["channel"]["id"], channel.id)
    self.assertEqual(profile["channel"]["name"], "Empty Course")
    self.assertEqual(profile["course_tags"], [])
    self.assertEqual(profile["prerequisite_channel_ids"], [])
    self.assertEqual(profile["structure"]["section_count"], 0)
    self.assertEqual(profile["structure"]["content_count"], 0)
    self.assertEqual(
        profile["structure"]["category_counts"],
        {
            "article": 0,
            "document": 0,
            "infographic": 0,
            "quiz": 0,
            "video": 0,
        },
    )
    self.assertEqual(profile["sections"], [])
    self.assertEqual(profile["contents"], [])
    self.assertEqual(
        profile["analysis"],
        {"analyzed_content_count": 0, "detected_languages": []},
    )
    self.assertEqual(
        profile["approved_content_relations"],
        {"outgoing": [], "incoming": []},
    )
```

- [ ] **Step 4: Add standard course/content aggregation test**

Add a fixture with one section and mixed content types:

```python
def test_profile_aggregates_standard_course_and_content_metadata(self):
    tag_group = self.env["slide.channel.tag.group"].create({"name": "Topic"})
    course_tag = self.env["slide.channel.tag"].create(
        {"name": "Databases", "group_id": tag_group.id}
    )
    content_tag = self.env["slide.tag"].create({"name": "SQL"})
    prerequisite = self.ProfileChannel.create({"name": "Programming"})
    channel = self.ProfileChannel.create(
        {
            "name": "Databases",
            "description": "<p>Relational foundations</p>",
            "description_short": "<p>DB basics</p>",
            "description_html": "<p>Detailed DB material</p>",
            "tag_ids": [Command.link(course_tag.id)],
            "prerequisite_channel_ids": [Command.link(prerequisite.id)],
        }
    )
    section = self.ProfileSlide.create(
        {
            "name": "Foundations",
            "channel_id": channel.id,
            "is_category": True,
            "sequence": 10,
        }
    )
    article = self.ProfileSlide.create(
        {
            "name": "Relational Model",
            "channel_id": channel.id,
            "slide_category": "article",
            "slide_type": "article",
            "sequence": 20,
            "completion_time": 0.5,
            "tag_ids": [Command.link(content_tag.id)],
        }
    )
    video = self.ProfileSlide.create(
        {
            "name": "SQL Demo",
            "channel_id": channel.id,
            "slide_category": "video",
            "slide_type": "youtube_video",
            "sequence": 30,
            "completion_time": 1.0,
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
    )

    profile = channel._facodi_course_profile()

    self.assertEqual(profile["channel"]["description"], "Relational foundations")
    self.assertEqual(profile["course_tags"][0]["name"], "Databases")
    self.assertEqual(profile["prerequisite_channel_ids"], [prerequisite.id])
    self.assertEqual(profile["structure"]["section_count"], 1)
    self.assertEqual(profile["structure"]["content_count"], 2)
    self.assertEqual(profile["structure"]["category_counts"]["article"], 1)
    self.assertEqual(profile["structure"]["category_counts"]["video"], 1)
    self.assertEqual(profile["sections"][0]["id"], section.id)
    self.assertEqual(profile["sections"][0]["content_ids"], [article.id, video.id])
    self.assertEqual(profile["contents"][0]["tag_names"], ["SQL"])
```

- [ ] **Step 5: Add deterministic repeat-output test**

```python
def test_profile_output_is_deterministic(self):
    channel = self.ProfileChannel.create({"name": "Deterministic Course"})
    self.ProfileSlide.create(
        {
            "name": "B",
            "channel_id": channel.id,
            "sequence": 20,
            "slide_category": "article",
            "slide_type": "article",
        }
    )
    self.ProfileSlide.create(
        {
            "name": "A",
            "channel_id": channel.id,
            "sequence": 10,
            "slide_category": "article",
            "slide_type": "article",
        }
    )

    first = channel._facodi_course_profile()
    channel.invalidate_recordset()
    second = channel._facodi_course_profile()

    self.assertEqual(first, second)
    self.assertEqual([item["name"] for item in first["contents"]], ["A", "B"])
```

- [ ] **Step 6: Run the focused tests and verify RED**

Run using the same Odoo 19 container/PostgreSQL 16 test pattern as `.github/workflows/ci.yml`, installing `facodi_learning` with:

```text
--test-tags /facodi_learning --stop-after-init
```

Expected result: the new course-profile tests fail because `slide.channel` has no `_facodi_course_profile()` method yet. Existing tests must continue to load before the missing-method failures.

- [ ] **Step 7: Commit the RED contract**

```bash
git add facodi_learning/tests/__init__.py facodi_learning/tests/test_course_profile.py
git commit -m "test: define deterministic course profile contract"
```

---

### Task 2: Implement the deterministic service and `slide.channel` adapter

**Files:**
- Create: `facodi_learning/services/course_profile.py`
- Create: `facodi_learning/models/slide_channel.py`
- Modify: `facodi_learning/services/__init__.py`
- Modify: `facodi_learning/models/__init__.py`
- Test: `facodi_learning/tests/test_course_profile.py`

**Interfaces:**
- Consumes: one `slide.channel` singleton.
- Produces: `build_course_profile(channel) -> dict` and `slide.channel._facodi_course_profile() -> dict`.

- [ ] **Step 1: Create the service with stable constants and normalization helpers**

Create `facodi_learning/services/course_profile.py`:

```python
from collections import Counter, defaultdict

from odoo.tools import html2plaintext


COURSE_PROFILE_VERSION = "course-profile-v1"
COURSE_CATEGORIES = ("article", "document", "infographic", "quiz", "video")


def _plain_text(value):
    if not value:
        return ""
    return " ".join(html2plaintext(value).split())


def _ordered_content(slides):
    return slides.sorted(key=lambda slide: (slide.sequence, slide.id))


def _ordered_tags(tags):
    return tags.sorted(key=lambda tag: ((tag.name or "").casefold(), tag.id))
```

- [ ] **Step 2: Add course-tag and structural aggregation**

Add:

```python
def _course_tags(channel):
    tags = channel.tag_ids.sorted(
        key=lambda tag: (tag.group_sequence, tag.sequence, tag.id)
    )
    return [
        {
            "id": tag.id,
            "name": tag.name or "",
            "group_id": tag.group_id.id,
            "group_name": tag.group_id.name or "",
        }
        for tag in tags
    ]


def _sections_and_contents(channel):
    sections = channel.slide_category_ids.sorted(
        key=lambda slide: (slide.sequence, slide.id)
    )
    contents = _ordered_content(channel.slide_content_ids)
    content_by_section = defaultdict(list)
    category_counts = Counter({category: 0 for category in COURSE_CATEGORIES})

    normalized_contents = []
    for slide in contents:
        category_counts[slide.slide_category] += 1
        content_by_section[slide.category_id.id].append(slide.id)
        tags = _ordered_tags(slide.tag_ids)
        normalized_contents.append(
            {
                "id": slide.id,
                "name": slide.name or "",
                "sequence": slide.sequence,
                "section_id": slide.category_id.id or False,
                "slide_category": slide.slide_category,
                "slide_type": slide.slide_type or False,
                "completion_time": float(slide.completion_time or 0.0),
                "tag_ids": tags.ids,
                "tag_names": [tag.name or "" for tag in tags],
            }
        )

    normalized_sections = [
        {
            "id": section.id,
            "name": section.name or "",
            "sequence": section.sequence,
            "content_ids": content_by_section.get(section.id, []),
            "duration": float(section.completion_time or 0.0),
        }
        for section in sections
    ]
    return normalized_sections, normalized_contents, dict(category_counts)
```

- [ ] **Step 3: Add safe analysis aggregation**

The baseline profile records only whether contents have immutable analysis and the latest detected languages; it never returns summary/transcript/raw payload.

```python
def _analysis_signals(channel, content_ids):
    if not content_ids:
        return {"analyzed_content_count": 0, "detected_languages": []}

    results = channel.env["facodi.learning.analysis.result"].search(
        [("slide_id", "in", content_ids)],
        order="create_date desc, id desc",
    )
    latest_by_slide = {}
    for result in results:
        latest_by_slide.setdefault(result.slide_id.id, result)

    languages = sorted(
        {
            result.detected_language.strip()
            for result in latest_by_slide.values()
            if result.detected_language and result.detected_language.strip()
        }
    )
    return {
        "analyzed_content_count": len(latest_by_slide),
        "detected_languages": languages,
    }
```

- [ ] **Step 4: Add approved content-relation aggregation**

```python
def _approved_content_relations(channel, content_ids):
    empty = {"outgoing": [], "incoming": []}
    if not content_ids:
        return empty

    Mapping = channel.env["facodi.learning.mapping"]
    outgoing = Mapping.search(
        [("source_slide_id", "in", content_ids), ("state", "=", "approved")]
    )
    incoming = Mapping.search(
        [("target_slide_id", "in", content_ids), ("state", "=", "approved")]
    )

    outgoing_counts = Counter(
        (mapping.target_slide_id.channel_id.id, mapping.mapping_type)
        for mapping in outgoing
    )
    incoming_counts = Counter(
        (mapping.source_slide_id.channel_id.id, mapping.mapping_type)
        for mapping in incoming
    )

    return {
        "outgoing": [
            {
                "target_channel_id": target_channel_id,
                "mapping_type": mapping_type,
                "count": count,
            }
            for (target_channel_id, mapping_type), count in sorted(
                outgoing_counts.items()
            )
        ],
        "incoming": [
            {
                "source_channel_id": source_channel_id,
                "mapping_type": mapping_type,
                "count": count,
            }
            for (source_channel_id, mapping_type), count in sorted(
                incoming_counts.items()
            )
        ],
    }
```

- [ ] **Step 5: Implement `build_course_profile(channel)`**

```python
def build_course_profile(channel):
    channel.ensure_one()
    channel.check_access("read")

    sections, contents, category_counts = _sections_and_contents(channel)
    content_ids = [content["id"] for content in contents]

    return {
        "schema_version": COURSE_PROFILE_VERSION,
        "channel": {
            "id": channel.id,
            "name": channel.name or "",
            "channel_type": channel.channel_type,
            "active": bool(channel.active),
            "website_id": channel.website_id.id or False,
            "website_published": bool(channel.website_published),
            "visibility": channel.visibility,
            "enroll": channel.enroll,
            "description": _plain_text(channel.description),
            "short_description": _plain_text(channel.description_short),
            "detailed_description": _plain_text(channel.description_html),
        },
        "course_tags": _course_tags(channel),
        "prerequisite_channel_ids": sorted(channel.prerequisite_channel_ids.ids),
        "structure": {
            "section_count": len(sections),
            "content_count": len(contents),
            "total_duration": float(channel.total_time or 0.0),
            "category_counts": {
                category: category_counts.get(category, 0)
                for category in COURSE_CATEGORIES
            },
        },
        "sections": sections,
        "contents": contents,
        "analysis": _analysis_signals(channel, content_ids),
        "approved_content_relations": _approved_content_relations(
            channel, content_ids
        ),
    }
```

- [ ] **Step 6: Export the service**

Append to `facodi_learning/services/__init__.py`:

```python
from .course_profile import COURSE_PROFILE_VERSION, build_course_profile
```

- [ ] **Step 7: Add the thin `slide.channel` extension**

Create `facodi_learning/models/slide_channel.py`:

```python
from odoo import models

from odoo.addons.facodi_learning.services.course_profile import build_course_profile


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    def _facodi_course_profile(self):
        self.ensure_one()
        return build_course_profile(self)
```

- [ ] **Step 8: Load the model extension**

Add to `facodi_learning/models/__init__.py`:

```python
from . import slide_channel
```

- [ ] **Step 9: Run M3.2 tests**

Run the Odoo 19 test suite focused on `/facodi_learning`.

Expected: the empty, standard aggregation and deterministic repeat tests pass. Any mismatch in Odoo field semantics is corrected in the service, not by weakening the tests.

- [ ] **Step 10: Run all existing FACODI tests**

Expected: all existing analysis, source ingestion, content mapping, security and M3.1 course-selection tests remain green.

- [ ] **Step 11: Commit the minimal GREEN implementation**

```bash
git add facodi_learning/services/course_profile.py \
  facodi_learning/services/__init__.py \
  facodi_learning/models/slide_channel.py \
  facodi_learning/models/__init__.py
git commit -m "feat: add deterministic course profile builder"
```

---

### Task 3: Prove analysis and mapping enrichment boundaries

**Files:**
- Modify: `facodi_learning/tests/test_course_profile.py`
- Modify only if a test exposes a real contract gap: `facodi_learning/services/course_profile.py`

**Interfaces:**
- Consumes: `build_course_profile(channel)` from Task 2.
- Produces: proof that M3.2 aggregates only safe latest-analysis language signals and approved content mappings.

- [ ] **Step 1: Add a helper for immutable analysis results**

Inside `TestCourseProfile` add:

```python
def _record_analysis_result(self, slide, detected_language):
    job = self.env["facodi.learning.analysis.job"].create(
        {"slide_id": slide.id, "provider": "local_metadata"}
    )
    return self.env["facodi.learning.analysis.result"]._record_output(
        {
            "job_id": job.id,
            "slide_id": slide.id,
            "provider": "local_metadata",
            "model_name": "profile-test",
            "summary": "Internal generated summary",
            "detected_language": detected_language,
            "transcript": "Internal transcript",
            "raw_payload": {"secret_like_field": "must-not-escape"},
            "suggested_tags": [],
            "proposed_mappings": [],
        }
    )
```

- [ ] **Step 2: Add partial/latest analysis test**

```python
def test_profile_uses_latest_language_signal_without_raw_analysis_output(self):
    channel = self.ProfileChannel.create({"name": "Languages"})
    analyzed = self.ProfileSlide.create(
        {
            "name": "Analyzed",
            "channel_id": channel.id,
            "slide_category": "article",
            "slide_type": "article",
        }
    )
    self.ProfileSlide.create(
        {
            "name": "Not analyzed",
            "channel_id": channel.id,
            "slide_category": "article",
            "slide_type": "article",
        }
    )
    self._record_analysis_result(analyzed, "en")
    self._record_analysis_result(analyzed, "pt")

    profile = channel._facodi_course_profile()

    self.assertEqual(profile["analysis"]["analyzed_content_count"], 1)
    self.assertEqual(profile["analysis"]["detected_languages"], ["pt"])
    serialized = repr(profile)
    self.assertNotIn("Internal generated summary", serialized)
    self.assertNotIn("Internal transcript", serialized)
    self.assertNotIn("secret_like_field", serialized)
```

- [ ] **Step 3: Add approved-only mapping aggregation test**

Create a second course with source/target slides, then create three mappings: one approved, one proposed and one rejected. Use Manager review actions for terminal states.

```python
def test_profile_aggregates_only_approved_content_relations(self):
    source_channel = self.ProfileChannel.create({"name": "Source"})
    target_channel = self.ProfileChannel.create({"name": "Target"})
    source = self.ProfileSlide.create(
        {
            "name": "Source Content",
            "channel_id": source_channel.id,
            "slide_category": "article",
            "slide_type": "article",
        }
    )
    targets = self.ProfileSlide.create(
        [
            {
                "name": "Approved Target",
                "channel_id": target_channel.id,
                "slide_category": "article",
                "slide_type": "article",
            },
            {
                "name": "Proposed Target",
                "channel_id": target_channel.id,
                "slide_category": "article",
                "slide_type": "article",
            },
            {
                "name": "Rejected Target",
                "channel_id": target_channel.id,
                "slide_category": "article",
                "slide_type": "article",
            },
        ]
    )
    Mapping = self.env["facodi.learning.mapping"].with_user(self.manager)
    approved = Mapping.create(
        {
            "source_slide_id": source.id,
            "target_slide_id": targets[0].id,
            "mapping_type": "related",
        }
    )
    approved.action_approve()
    Mapping.create(
        {
            "source_slide_id": source.id,
            "target_slide_id": targets[1].id,
            "mapping_type": "recommended",
        }
    )
    rejected = Mapping.create(
        {
            "source_slide_id": source.id,
            "target_slide_id": targets[2].id,
            "mapping_type": "supports",
        }
    )
    rejected.action_reject()

    profile = source_channel._facodi_course_profile()

    self.assertEqual(
        profile["approved_content_relations"]["outgoing"],
        [
            {
                "target_channel_id": target_channel.id,
                "mapping_type": "related",
                "count": 1,
            }
        ],
    )
```

- [ ] **Step 4: Add incoming relation coverage**

Extend the mapping test with an approved reverse relation and assert the source course appears under `incoming` with the expected type/count.

- [ ] **Step 5: Run focused tests and observe RED/GREEN correctly**

If the Task 2 implementation already satisfies the new tests, record that they pass without production changes. If a test exposes a real mismatch, change only the relevant helper and rerun the focused test before rerunning the suite.

- [ ] **Step 6: Commit enrichment-boundary tests**

```bash
git add facodi_learning/tests/test_course_profile.py facodi_learning/services/course_profile.py
git commit -m "test: cover safe course profile enrichment"
```

---

### Task 4: Prove privacy, non-mutation and canonical-data boundaries

**Files:**
- Modify: `facodi_learning/tests/test_course_profile.py`
- Modify only if required by a failing invariant: `facodi_learning/services/course_profile.py`

**Interfaces:**
- Consumes: stable profile contract from Tasks 1–3.
- Produces: explicit regression evidence that profiles contain no learner state and do not mutate Odoo records.

- [ ] **Step 1: Add learner-data exclusion test**

Create a partner/member record using standard eLearning membership, build the profile before and after membership changes, and assert profile equality.

```python
def test_profile_is_independent_from_learner_membership(self):
    channel = self.ProfileChannel.create({"name": "Privacy Course"})
    self.ProfileSlide.create(
        {
            "name": "Lesson",
            "channel_id": channel.id,
            "slide_category": "article",
            "slide_type": "article",
        }
    )
    before = channel._facodi_course_profile()
    learner = self.env["res.partner"].create(
        {"name": "Profile Learner", "email": "learner@example.invalid"}
    )
    self.env["slide.channel.partner"].create(
        {"channel_id": channel.id, "partner_id": learner.id}
    )
    channel.invalidate_recordset()
    after = channel._facodi_course_profile()

    self.assertEqual(before, after)
    serialized = repr(after)
    self.assertNotIn("learner@example.invalid", serialized)
    forbidden_keys = {
        "partner_ids",
        "channel_partner_ids",
        "members_count",
        "completion",
        "completed",
        "is_member",
        "user_has_completed",
    }
    self.assertTrue(forbidden_keys.isdisjoint(after.keys()))
    self.assertTrue(forbidden_keys.isdisjoint(after["channel"].keys()))
```

If the standard `slide.channel.partner` model requires additional fields in Odoo 19, use its minimal required standard creation contract rather than bypassing it with SQL or `sudo()`.

- [ ] **Step 2: Add no-mutation test**

```python
def test_profile_generation_does_not_write_course_or_content(self):
    channel = self.ProfileChannel.create({"name": "Read Only Profile"})
    slide = self.ProfileSlide.create(
        {
            "name": "Lesson",
            "channel_id": channel.id,
            "slide_category": "article",
            "slide_type": "article",
        }
    )
    channel_write_date = channel.write_date
    slide_write_date = slide.write_date

    channel._facodi_course_profile()
    channel.invalidate_recordset()
    slide.invalidate_recordset()

    self.assertEqual(channel.write_date, channel_write_date)
    self.assertEqual(slide.write_date, slide_write_date)
```

- [ ] **Step 3: Add unpublished-content neutrality test**

Create one published and one unpublished standard content item and assert both appear in the internal profile. This proves M3.2 describes the canonical current course, while learner-facing publication filtering remains a separate M3.3/Website concern.

```python
def test_internal_profile_includes_current_unpublished_content(self):
    channel = self.ProfileChannel.create({"name": "Draft Course"})
    published = self.ProfileSlide.create(
        {
            "name": "Published",
            "channel_id": channel.id,
            "slide_category": "article",
            "slide_type": "article",
            "is_published": True,
        }
    )
    draft = self.ProfileSlide.create(
        {
            "name": "Draft",
            "channel_id": channel.id,
            "slide_category": "article",
            "slide_type": "article",
            "is_published": False,
        }
    )

    profile = channel._facodi_course_profile()

    self.assertEqual(
        {item["id"] for item in profile["contents"]},
        {published.id, draft.id},
    )
```

- [ ] **Step 4: Run focused tests**

Expected: all privacy/non-mutation tests pass without `sudo()` or writes added to the builder.

- [ ] **Step 5: Run complete FACODI regression suite**

Expected: all previous tests plus M3.2 pass on clean install.

- [ ] **Step 6: Commit the boundary proofs**

```bash
git add facodi_learning/tests/test_course_profile.py facodi_learning/services/course_profile.py
git commit -m "test: enforce course profile privacy boundaries"
```

---

### Task 5: Version, document and run exact-head release gates

**Files:**
- Modify: `facodi_learning/__manifest__.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Test: full repository CI

**Interfaces:**
- Consumes: completed M3.2 profile implementation.
- Produces: portable addon version `19.0.1.3.0`, documented internal contract and exact-head CI evidence.

- [ ] **Step 1: Bump the addon version**

Change in `facodi_learning/__manifest__.py`:

```python
"version": "19.0.1.3.0",
```

No migration script is required because M3.2 creates no persistent schema or data model.

- [ ] **Step 2: Document M3.2 in README**

Add a concise Course Profile section stating:

```text
slide.channel
  -> deterministic FACODI profile
  -> standard course metadata
  -> sections/content types/duration
  -> standard course/content tags
  -> latest safe analysis language signals
  -> approved content-relation aggregates
  -> native prerequisites
```

Also state explicitly that M3.2:

- creates no profile table;
- persists no duplicate course state;
- includes no learner/member/progress data;
- uses no AI/network dependency;
- is internal input for future course retrieval/mapping.

- [ ] **Step 3: Update `docs/architecture.md`**

Document the private API:

```python
profile = channel._facodi_course_profile()
```

Document `schema_version == "course-profile-v1"`, the top-level keys and the rule that future incompatible schema changes require a new profile version rather than silently changing M3.2 semantics.

- [ ] **Step 4: Run clean-install CI on the exact branch head**

Use the repository GitHub Actions workflow with Odoo 19 and PostgreSQL 16.

Required evidence:

```text
Install addon and run Odoo tests -> success
0 failed, 0 error(s)
```

Record the exact commit SHA and workflow run ID.

- [ ] **Step 5: Run addon upgrade regression gate on the same exact head**

Required evidence:

```text
Upgrade addon and run regression tests -> success
0 failed, 0 error(s)
```

No release-ready claim is allowed if the tested SHA differs from the branch/PR head.

- [ ] **Step 6: Inspect warnings and distinguish repository failures from upstream noise**

Expected Odoo test fixtures may intentionally log denied ACL operations and rejected foreign-key deletion attempts. Treat only new M3.2-specific exceptions, failing tests, unsafe access elevation, mutation or upgrade errors as blockers.

- [ ] **Step 7: Commit documentation/versioning**

```bash
git add facodi_learning/__manifest__.py README.md docs/architecture.md
git commit -m "docs: finalize M3.2 course profile"
```

- [ ] **Step 8: Open a stacked draft PR**

Until PR #3 is merged, open M3.2 against:

```text
base: feat/m3-1-course-selection-core
head: feat/m3-2-course-profile
```

PR title:

```text
M3.2: add deterministic course profile
```

The PR body must state that it is intentionally stacked on M3.1 and will be retargeted to `main` after PR #3 merges. It must include the exact tested SHA, clean-install count, upgrade count and explicit scope exclusions for M3.3+.

- [ ] **Step 9: Final review gate**

Before marking the PR ready for review:

- confirm no persistent profile model/table was added;
- confirm no learner/member/progress fields appear in profile output;
- confirm no `sudo()` was added to profile generation;
- confirm no external network/AI dependency was introduced;
- confirm M3.1 behavior and all older tests remain green;
- confirm PR diff contains only M3.2 implementation/tests/docs plus the already-stacked M3.1 ancestry;
- confirm the exact head is 0 commits behind its stacked base.

## Expected M3.2 Definition of Done

```text
slide.channel
      |
      v
_facodi_course_profile()
      |
      v
course-profile-v1
  |-- canonical course metadata
  |-- standard course tags/groups
  |-- native prerequisites
  |-- sections + compact content signals
  |-- content categories + total duration
  |-- latest safe language evidence
  |-- approved content-relation aggregates
  |
  +-- no persistence
  +-- no learner data
  +-- no AI/network
  +-- no mutation
```

M3.2 is complete only when the same exact branch head passes both clean-install and upgrade regression gates on Odoo 19 Community.