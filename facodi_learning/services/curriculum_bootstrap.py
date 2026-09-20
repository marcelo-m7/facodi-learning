import json
from pathlib import Path

from odoo import fields


_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "lesti_2026_27.json"


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
    rewritten. Publication state is operational and may be enabled when the
    persisted identity/source still matches the curated fixture.
    """
    payload = _load_fixture()
    reference_values = dict(payload["reference"])
    # Validation is an operational human-curation state. Timestamp it at the
    # installation/reconciliation event instead of fabricating a source-fetch time.
    reference_values["validated_at"] = fields.Datetime.now()
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
        if identity_matches:
            operational = {"website_published": True}
            if not reference.validated_at:
                operational["validated_at"] = fields.Datetime.now()
            reference.write(operational)

            if not reference._has_terminal_coverage():
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
