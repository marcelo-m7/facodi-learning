# M3.5b YouTube Discovery Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `facodi_learning_youtube` addon that discovers public YouTube playlists as FACODI course candidates through the M3.5a registry without adding YouTube/network dependencies to the core addon.

**Architecture:** The optional addon inherits `facodi.learning.discovery.run` only to register provider key `youtube`. A focused service calls YouTube Data API v3 `playlists.list` for configured channel IDs, paginates with `nextPageToken`, returns normalized playlist metadata, and reads the API key exclusively from `FACODI_YOUTUBE_API_KEY` in the process environment. The provider returns candidate dictionaries only; core discovery owns candidate upsert/evaluation and only M3.1 Manager policy may later resolve a candidate to `slide.channel`.

**Tech Stack:** Odoo 19 Community, Python stdlib `urllib`, YouTube Data API v3, PostgreSQL 16, GitHub Actions. No Google client SDK.

**Spec:** `docs/superpowers/specs/2026-09-05-facodi-learning-course-selection-mapping-design.md` sections 13, 15, 17–18; M3.5a provider registry.

## Global Constraints

- This addon depends on `facodi_learning`; the core never depends on this addon.
- API key is read only from `FACODI_YOUTUBE_API_KEY`; no settings/database field stores it.
- Provider configuration stores only non-secret channel IDs/default language.
- Only public playlist metadata is discovered; no video download, transcript scraping, OAuth mutation or content copying.
- Provider never creates/publishes `slide.channel` or `slide.slide` directly.
- Requests use finite timeout, bounded pagination and sanitized errors.
- YouTube playlist identity is `provider="youtube"`, `external_id="playlist:<playlist_id>"`.

---

### Task 1: Optional Addon Skeleton and Provider Registry Extension

**Files:**
- Create: `facodi_learning_youtube/__init__.py`
- Create: `facodi_learning_youtube/__manifest__.py`
- Create: `facodi_learning_youtube/models/__init__.py`
- Create: `facodi_learning_youtube/models/discovery_run.py`
- Create: `facodi_learning_youtube/services/__init__.py`
- Create: `facodi_learning_youtube/services/youtube.py`
- Create: `facodi_learning_youtube/tests/__init__.py`
- Create: `facodi_learning_youtube/tests/test_youtube_discovery.py`

**Interfaces:**
- `discover_youtube_playlists(run, limit) -> iterable[dict]`.
- Registry extension adds `youtube` while preserving all core providers via `super()`.

- [ ] Write RED test that installing the addon registers `youtube` and does not remove `manual`/other registry providers.
- [ ] Implement addon skeleton and registry inheritance only.
- [ ] Verify core and provider addon install together and commit GREEN.

### Task 2: YouTube API Client, Pagination and Normalization

**Files:**
- Modify: `facodi_learning_youtube/services/youtube.py`
- Test: `facodi_learning_youtube/tests/test_youtube_discovery.py`

**Interfaces:**
- `_youtube_get_json(endpoint, params, *, timeout=10) -> dict` uses `urllib.request.urlopen`.
- Provider reads `FACODI_YOUTUBE_API_KEY`, non-secret config params, and calls `playlists.list` with `part=snippet,contentDetails,status`, `channelId`, `maxResults<=50`, optional `pageToken`.
- Output candidate includes source URL, title, description, channel title/institution, default language when configured, and safe metadata (`playlist_id`, `channel_id`, `published_at`, `item_count`).

- [ ] Write RED tests with mocked HTTP responses for one page, multiple pages, per-run limit, multiple channels, missing key, malformed response and provider HTTP/URL failure.
- [ ] Implement finite-timeout GET without logging full URL/query string.
- [ ] Raise sanitized provider errors that never include API key or raw response body.
- [ ] Map playlists to normalized candidate dictionaries; skip private/unlisted playlists when status evidence marks them non-public.
- [ ] Re-run provider + core tests and commit GREEN.

### Task 3: Provider Settings and Manager UX

**Files:**
- Create: `facodi_learning_youtube/models/res_config_settings.py`
- Modify: `facodi_learning_youtube/models/__init__.py`
- Create: `facodi_learning_youtube/views/res_config_settings_views.xml`
- Modify: `facodi_learning_youtube/__manifest__.py`
- Test: `facodi_learning_youtube/tests/test_youtube_discovery.py`

**Interfaces:**
- `facodi_learning.youtube_channel_ids`: comma-separated public channel IDs.
- `facodi_learning.youtube_default_language`: optional normalized language code.
- No API-key field exists in ORM or views.

- [ ] Write RED tests for settings fields/XML and explicit absence of API-key fields/config parameters.
- [ ] Implement settings and help text explaining `FACODI_YOUTUBE_API_KEY` deployment requirement.
- [ ] Verify only Managers can configure via normal eLearning settings access.
- [ ] Re-run tests and commit GREEN.

### Task 4: End-to-End Discovery Run Integration

**Files:**
- Modify: `facodi_learning_youtube/tests/test_youtube_discovery.py`
- Modify: `README.md` or create `facodi_learning_youtube/README.md`

**Interfaces:**
- Core `facodi.learning.discovery.run(provider="youtube")` creates/refreshes `facodi.learning.course.candidate` through M3.5a only.

- [ ] Write E2E test: mocked YouTube playlists → discovery run → candidate rows with stable playlist identity → replay refreshes rather than duplicates → candidate remains governed by M3.1 selection/publication rules.
- [ ] Assert provider layer never directly creates `slide.channel` or `slide.slide`.
- [ ] Assert a terminal rejected/resolved candidate is ignored on later YouTube refresh.
- [ ] Re-run clean install, addon tests and upgrade gates.

### Task 5: Release and Documentation

**Files:**
- Modify: `facodi_learning_youtube/__manifest__.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/validation.md`

**Interfaces:**
- Initial optional addon version `19.0.1.0.0`.

- [ ] Document API/quota boundary: the implementation uses official `playlists.list`, pagination via `nextPageToken`, max page size 50, finite timeout and environment-only key.
- [ ] Document that provider discovery is playlist metadata only and does not import media/transcripts/content.
- [ ] Run exact-head core + optional-addon install/tests and real upgrade regression.
- [ ] Review diff for secrets/network leakage and open PR to `main` only after all gates are GREEN.
