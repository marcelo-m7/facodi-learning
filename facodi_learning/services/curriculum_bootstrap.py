import json
from pathlib import Path

from odoo import fields
from odoo.exceptions import ValidationError


_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "lesti_2026_27.json"
_DESIGN_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "design_curricula_2026_27.json"


def _load_fixture():
    with _FIXTURE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _unit_values(reference, payload):
    return {
        "reference_id": reference.id,
        "external_unit_code": payload["code"],
        "name": payload["name"],
        "credits": payload.get("credits", 0.0),
        "curricular_year": payload.get("year", 0),
        "period": payload.get("period", "other"),
        "classification": payload.get("classification", "unspecified"),
        "option_group": payload.get("option_group"),
        "sequence": payload.get("sequence", 10),
        "metadata": payload.get("metadata") or {},
    }


def ensure_lesti_2026_27(env):
    """Create or safely reconcile the curated UAlg LESTI 2026/27 reference.

    The operation is idempotent. Existing reviewed source facts are never
    rewritten. The bootstrap owns source facts only: new references stay draft
    and private, while an existing reviewed/published reference keeps its
    editorial state unchanged.
    """
    payload = _load_fixture()
    reference_values = dict(payload["reference"])
    # Editorial state is never driven by fixture/bootstrap data.
    reference_values.pop("website_published", None)
    Reference = env["facodi.learning.curriculum.reference"].sudo()
    Unit = env["facodi.learning.curriculum.unit"].sudo()

    reference = Reference.search(
        [
            ("provider", "=", reference_values["provider"]),
            ("external_id", "=", reference_values["external_id"]),
        ],
        limit=1,
    )
    if not reference:
        reference = Reference.create(reference_values)
    else:
        identity_matches = (
            reference.institution == reference_values["institution"]
            and reference.programme_name == reference_values["programme_name"]
            and reference.external_programme_code
            == reference_values["external_programme_code"]
            and reference.academic_year == reference_values["academic_year"]
            and reference.source_url == reference_values["source_url"]
        )
        if not identity_matches:
            raise ValidationError(
                "Curated curriculum identity does not match the existing curriculum reference."
            )

        if reference.state == "draft" and not reference._has_terminal_coverage():
            source_updates = {}
            for field_name in (
                "source_title",
                "source_hash",
                "source_retrieved_at",
                "metadata",
            ):
                wanted = reference_values.get(field_name)
                current = reference[field_name]
                if wanted and current != wanted:
                    source_updates[field_name] = wanted
            if source_updates:
                reference.write(source_updates)

    for unit_payload in payload["units"]:
        unit = Unit.search(
            [
                ("reference_id", "=", reference.id),
                ("external_unit_code", "=", unit_payload["code"]),
            ],
            limit=1,
        )
        values = _unit_values(reference, unit_payload)
        if not unit:
            Unit.create(values)
            continue
        if unit._has_terminal_coverage():
            continue
        mutable = {
            key: value
            for key, value in values.items()
            if key not in {"reference_id", "external_unit_code"}
            and unit[key] != value
        }
        if mutable:
            unit.write(mutable)

    return reference

def _load_design_fixture():
    with _DESIGN_FIXTURE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _ensure_import_xmlid(env, name, record):
    ModelData = env["ir.model.data"].sudo()
    existing = ModelData.search(
        [("module", "=", "__import__"), ("name", "=", name)],
        limit=1,
    )
    if existing:
        if existing.model != record._name or existing.res_id != record.id:
            raise ValidationError(
                "FACODI curated import identity is already bound to another record."
            )
        return existing
    return ModelData.create(
        {
            "module": "__import__",
            "name": name,
            "model": record._name,
            "res_id": record.id,
            "noupdate": True,
        }
    )


def _resolve_import_xmlid(env, name):
    return env.ref(f"__import__.{name}", raise_if_not_found=False)


def _reconcile_design_slide_xmlids(env, payload):
    """Repair the temporary normalized IDs used by the 19.0.1.124.0 recovery.

    Historical Open2 imports preserve the YouTube ID verbatim in __import__
    external IDs. A short-lived 19.0.1.124.0 fixture normalized hyphens to
    underscores, which could create a duplicate beside an already recovered
    production slide. Rebind clean-install records and remove only exact
    same-URL duplicates before normal reconciliation.
    """
    ModelData = env["ir.model.data"].sudo()
    Slide = env["slide.slide"].sudo()
    for item in payload.get("content", []):
        for slide_payload in item.get("slides", []):
            correct_name = slide_payload["xmlid"]
            legacy_name = correct_name.replace("-", "_")
            if legacy_name == correct_name:
                continue

            correct = ModelData.search(
                [
                    ("module", "=", "__import__"),
                    ("name", "=", correct_name),
                    ("model", "=", "slide.slide"),
                ],
                limit=1,
            )
            legacy = ModelData.search(
                [
                    ("module", "=", "__import__"),
                    ("name", "=", legacy_name),
                    ("model", "=", "slide.slide"),
                ],
                limit=1,
            )
            if not legacy:
                continue
            if not correct:
                legacy.write({"name": correct_name})
                continue
            if legacy.res_id == correct.res_id:
                legacy.unlink()
                continue

            expected_url = slide_payload["url"]
            correct_slide = Slide.browse(correct.res_id).exists()
            legacy_slide = Slide.browse(legacy.res_id).exists()
            if (
                not correct_slide
                or not legacy_slide
                or correct_slide.url != expected_url
                or legacy_slide.url != expected_url
                or correct_slide.channel_id != legacy_slide.channel_id
            ):
                raise ValidationError(
                    "FACODI cannot safely reconcile conflicting recovered design content."
                )
            legacy.unlink()
            legacy_slide.unlink()


def _ensure_design_content(env, payload):
    Channel = env["slide.channel"].sudo()
    Slide = env["slide.slide"].sudo()
    Tag = env["slide.tag"].sudo()
    for item in payload.get("content", []):
        channel = _resolve_import_xmlid(env, item["xmlid"])
        if not channel:
            values = dict(item["channel"])
            values.update(
                {
                    "channel_type": "training",
                    "enroll": "public",
                    "visibility": "public",
                    "is_published": True,
                }
            )
            channel = Channel.create(values)
            _ensure_import_xmlid(env, item["xmlid"], channel)
        elif not channel.is_published:
            channel.write({"is_published": True})

        for position, slide_payload in enumerate(item.get("slides", []), start=1):
            slide = _resolve_import_xmlid(env, slide_payload["xmlid"])
            if not slide:
                slide = Slide.create(
                    {
                        "name": slide_payload["name"],
                        "channel_id": channel.id,
                        "slide_category": "article",
                        "source_type": "external",
                        "url": slide_payload["url"],
                        "description": slide_payload.get("description") or "",
                        "is_published": True,
                        "sequence": position * 10,
                    }
                )
                _ensure_import_xmlid(env, slide_payload["xmlid"], slide)

            tag_names = [
                name.strip()
                for name in slide_payload.get("tags", [])
                if isinstance(name, str) and name.strip()
            ]
            tags = Tag
            for name in dict.fromkeys(tag_names):
                tag = Tag.search([("name", "=", name)], limit=1)
                if not tag:
                    tag = Tag.create({"name": name})
                tags |= tag
            if tags:
                desired_tags = slide.tag_ids | tags
                if set(desired_tags.ids) != set(slide.tag_ids.ids):
                    # Seed semantic tags without deleting editor-added metadata.
                    slide.write({"tag_ids": [(6, 0, desired_tags.ids)]})


def ensure_design_curricula_2026_27(env):
    """Reconcile the two official 2026/27 UAlg design curricula and supports links.

    Official study-plan facts remain canonical in curriculum references and units.
    Recovered or AI-enriched resources only create supports coverage and never
    imply academic equivalence, accreditation, ECTS recognition or approval.
    """
    payload = _load_design_fixture()
    Reference = env["facodi.learning.curriculum.reference"].sudo()
    Unit = env["facodi.learning.curriculum.unit"].sudo()
    Coverage = env["facodi.learning.curriculum.coverage"].sudo()
    references = {}

    for programme in payload["programmes"]:
        reference_values = dict(programme["reference"])
        publish_requested = bool(reference_values.pop("website_published", False))
        reference = Reference.search(
            [
                ("provider", "=", reference_values["provider"]),
                ("external_id", "=", reference_values["external_id"]),
            ],
            limit=1,
        )
        if not reference:
            reference = Reference.create(reference_values)
        else:
            identity_matches = (
                reference.institution == reference_values["institution"]
                and reference.programme_name == reference_values["programme_name"]
                and reference.external_programme_code == reference_values["external_programme_code"]
                and reference.academic_year == reference_values["academic_year"]
                and reference.source_url == reference_values["source_url"]
            )
            if not identity_matches:
                raise ValidationError(
                    "Curated design curriculum identity does not match the existing curriculum reference."
                )

        for unit_payload in programme["units"]:
            unit = Unit.search(
                [
                    ("reference_id", "=", reference.id),
                    ("external_unit_code", "=", unit_payload["code"]),
                ],
                limit=1,
            )
            values = _unit_values(reference, unit_payload)
            if not unit:
                Unit.create(values)
            elif not unit._has_terminal_coverage():
                mutable = {
                    key: value
                    for key, value in values.items()
                    if key not in {"reference_id", "external_unit_code"}
                    and unit[key] != value
                }
                if mutable:
                    unit.write(mutable)

        if reference.state == "draft":
            reference.action_validate()
        if publish_requested and reference.state == "validated" and not reference.website_published:
            reference.action_publish()
        references[reference.external_programme_code] = reference

    _reconcile_design_slide_xmlids(env, payload)
    _ensure_design_content(env, payload)

    for relation in payload.get("coverage", []):
        reference = references.get(relation["programme_code"])
        if not reference:
            continue
        unit = Unit.search(
            [
                ("reference_id", "=", reference.id),
                ("external_unit_code", "=", relation["unit_code"]),
            ],
            limit=1,
        )
        channel = _resolve_import_xmlid(env, relation["channel_xmlid"])
        if not unit or not channel:
            continue
        coverage = Coverage.search(
            [
                ("channel_id", "=", channel.id),
                ("curriculum_unit_id", "=", unit.id),
                ("coverage_type", "=", "supports"),
            ],
            limit=1,
        )
        if not coverage:
            coverage = Coverage.create(
                {
                    "channel_id": channel.id,
                    "curriculum_unit_id": unit.id,
                    "coverage_type": "supports",
                    "confidence": relation["confidence"],
                    "origin": "manual",
                    "evidence": {
                        "source": relation["evidence"],
                        "official_source_url": reference.source_url,
                        "academic_year": reference.academic_year,
                        "boundary": (
                            "Content support only; no academic equivalence, "
                            "accreditation or ECTS recognition."
                        ),
                    },
                }
            )
        if relation.get("approved") and coverage.state == "proposed":
            coverage.action_approve()

    return references

