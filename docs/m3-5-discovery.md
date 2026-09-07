# M3.5 Course Discovery

FACODI course discovery is an operational ingestion layer for **course candidates**, not a parallel LMS and not a direct course-creation pipeline. External providers return normalized course metadata; the core persists or refreshes `facodi.learning.course.candidate` and then delegates evaluation/resolution to the existing M3.1 course-selection policy.

## Core contract

`facodi.learning.discovery.run` records one provider execution. Runs are created pending, may be processed only by eLearning Managers, and retain server-owned execution evidence: state, requester, timestamps, counters and sanitized error text. eLearning Officers have read-only access to runs; Public/Portal have no ACL.

Providers extend `_get_course_discovery_registry()` and receive `(run, limit)`. Each yielded item is normalized through `services/course_discovery.py`. Invalid items are ignored individually. A provider-level exception rolls back candidate mutations from that run and marks only that run failed; raw provider exception text is not persisted.

Candidate identity remains the M3.1 unique `(provider, external_id)`. Discovery adds `discovered_at`, `last_discovered_at` and `last_discovery_run_id` as server-owned provenance. Unresolved candidates may refresh normalized metadata and are reevaluated. Terminal rejected/resolved candidates are ignored by later runs and are never silently rewritten. Providers never call `slide.channel.create()`; a later M3.1 Manager/Auto-Approve decision may resolve a candidate through the existing locked selection path.

## Concurrency and scheduling

Processing locks the discovery-run row and also acquires a transaction advisory try-lock scoped to the provider. Two runs of the same provider therefore cannot concurrently race on candidate identity, while independent providers remain parallel. Lock contention fails closed with a retryable validation error.

The standard Odoo scheduled action calls `_cron_discover_courses()`. Discovery is disabled by default and does nothing until `facodi_learning.discovery_enabled` is true. Only provider identifiers listed in `facodi_learning.discovery_enabled_providers` are scheduled. `facodi_learning.discovery_batch_size` is clamped to `1..100`. In real cron context the worker uses Odoo 19 `_commit_progress()` between provider runs. No Celery, Redis, custom worker or core network SDK is introduced.

## Administrative UX

Managers configure Course Discovery under eLearning settings. The backend workspace is:

```text
eLearning
└── FACODI Learning
    └── Course Discovery
        ├── Candidates
        └── Discovery Runs
```

Candidate forms expose discovery provenance read-only. Discovery-run forms expose `Run Discovery` only to eLearning Managers and keep execution counters/errors read-only.

## Provider addons

The core ships only the offline `manual` discovery provider. Network-backed catalogs belong in optional addons such as `facodi_learning_youtube`. Runtime credentials must remain in environment/provider configuration and must never be persisted in candidate metadata, run errors or logs.

Version `19.0.1.6.0` completes the M3.5 core discovery contract additively. Existing candidates, curriculum references, mappings, standard courses and learning content require no historical rewrite.
