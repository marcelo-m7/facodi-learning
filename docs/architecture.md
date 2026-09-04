# FACODI Learning Architecture

## Standard-first boundary

FACODI Learning is an extension of Odoo 19 Community eLearning (`website_slides`), not a parallel LMS.

```text
Odoo website_slides
├── slide.channel       canonical course
├── slide.slide         canonical lesson/content
├── slide.tag           canonical content tags
├── Officer / Manager   canonical back-office roles
└── ir.cron             canonical scheduler
          │
          ▼
facodi_learning
├── analysis job        processing/audit state only
├── analysis result     historical normalized output
└── learning mapping    proposed relationship between slide.slide records
```

## Analysis flow

1. An Officer selects a standard `slide.slide` and queues analysis.
2. FACODI creates `facodi.learning.analysis.job`; it does not copy the content record.
3. Standard `ir.cron` processes a bounded pending batch.
4. The selected provider returns a normalized result.
5. FACODI appends `facodi.learning.analysis.result` and keeps older results.
6. Suggested tags point to standard `slide.tag` records and are applied only through an explicit action.
7. A provider may create proposed mappings; approval is a separate human decision.

The baseline `local_metadata` provider is deliberately deterministic and network-free. Its purpose is to establish the stable provider contract and make the core addon independently installable/testable.

## Security

FACODI reuses the standard groups `website_slides.group_website_slides_officer` and `website_slides.group_website_slides_manager`.

Record rules follow the standard eLearning pattern: Officers can read analysis records broadly but creation/write is limited to content in courses they own; Managers have complete administration. Mapping approval/rejection additionally performs an explicit Manager check in Python so the business transition cannot be bypassed by calling the method directly.

## Provider extensions

External AI, transcription or video APIs belong in separate provider addons. They inherit the analysis job model and extend `_get_provider_registry()` after calling `super()`. The core addon consumes only normalized dictionaries and therefore does not embed vendor schemas or credentials.

## Upgrade discipline

The module version follows Odoo conventions (`19.0.x.y.z`). Schema changes should be additive when practical. Data migrations, when needed, belong under Odoo's module migration directories and must preserve analysis history. Standard Odoo models are never redefined as FACODI-owned canonical copies.
