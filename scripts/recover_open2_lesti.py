#!/usr/bin/env python3
"""Recover the FACODI LESTI catalogue from the versioned Open2 snapshot.

Run inside an Odoo shell where `env` is available, for example:

    FACODI_RECOVERY_SNAPSHOT=/mnt/extra-addons/facodi_learning/recovery/open2_lesti_2026-09-28.json \
      odoo shell -d facodi < scripts/recover_open2_lesti.py

The script is intentionally idempotent. It reuses deterministic __import__ XML IDs,
does not fetch remote content, and preserves the academic boundary between content
coverage and official equivalence/credit recognition.
"""

import json
import os
import re
from html import escape
from pathlib import Path

SNAPSHOT_ENV = "FACODI_RECOVERY_SNAPSHOT"
DEFAULT_SNAPSHOT = Path("recovery/open2_lesti_2026-09-28.json")
COURSE_XID_PREFIX = "__import__.facodi_lesti_"
SLIDE_XID_PREFIX = "__import__.facodi_link_"
COVERAGE_XID_PREFIX = "__import__.facodi_cov_"

UNIT_NAMES = {
    "19411002": "Análise Matemática I",
    "19411008": "Análise Matemática II",
    "19411011": "Algoritmos e Estruturas de Dados",
    "19411012": "Base de Dados I",
    "19411018": "Probabilidades e Estatística",
    "19411020": "Análise de Dados e Visualização da Informação",
    "19411049": "Cibersegurança",
}


def _resolve_snapshot_path():
    explicit = os.environ.get(SNAPSHOT_ENV)
    if explicit:
        return Path(explicit)
    candidates = [
        DEFAULT_SNAPSHOT,
        Path("/mnt/extra-addons/facodi_learning") / DEFAULT_SNAPSHOT,
        Path("/opt/odoo/custom-addons/facodi_learning") / DEFAULT_SNAPSHOT,
        Path("/addons/facodi_learning") / DEFAULT_SNAPSHOT,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "FACODI recovery snapshot not found. Set %s explicitly." % SNAPSHOT_ENV
    )


def _xmlid_record(xmlid, model):
    try:
        record = env.ref(xmlid, raise_if_not_found=False)
    except TypeError:
        record = env.ref(xmlid)
    if record and record._name == model and record.exists():
        return record
    return env[model].browse()


def _ensure_xmlid(xmlid, record):
    module, name = xmlid.split(".", 1)
    imd = env["ir.model.data"].sudo()
    existing = imd.search([("module", "=", module), ("name", "=", name)], limit=1)
    vals = {"module": module, "name": name, "model": record._name, "res_id": record.id, "noupdate": False}
    if existing:
        existing.write(vals)
    else:
        imd.create(vals)


def _upsert_by_xmlid(xmlid, model, values):
    record = _xmlid_record(xmlid, model)
    Model = env[model].sudo().with_context(
        tracking_disable=True,
        website_slides_skip_fetch_metadata=True,
    )
    if record:
        record.sudo().with_context(
            tracking_disable=True,
            website_slides_skip_fetch_metadata=True,
        ).write(values)
        return record, False
    record = Model.create(values)
    _ensure_xmlid(xmlid, record)
    return record, True


def _recovery_title(row, youtube_id):
    """Prefer the original provider title when legacy AI output is synthetic."""
    optimized = str(row.get("optimized_title") or "").strip()
    original = str(row.get("title") or "").strip()
    synthetic = bool(
        optimized
        and (
            optimized.lower().startswith("monynha fun:")
            or "título otimizado" in optimized.lower()
            or re.search(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                optimized,
                re.I,
            )
        )
    )
    title = original if synthetic and original else (optimized or original)
    return (title or ("YouTube video %s" % youtube_id)).strip()[:255]


def _video_description(row):
    source = escape((row.get("channel_name") or "YouTube").strip())
    unit_code = escape(row["unit_code"])
    summary = row.get("short_summary") or row.get("summary_description") or ""
    summary_html = ""
    if summary:
        summary_html = "<p>%s</p>" % escape(str(summary).strip())
    review = row.get("review_status") or "needs_review"
    review_text = "mapeamento auto-revisto" if review == "auto_reviewed" else "mapeamento a rever"
    return (
        "%s"
        "<p>Fonte: %s. Recurso aberto recuperado do acervo FACODI/Open2 "
        "para a UC %s (%s).</p>"
        "<p><strong>Fronteira académica:</strong> correspondência de conteúdo "
        "para apoio ao estudo; não constitui equivalência académica, "
        "reconhecimento de ECTS ou progressão curricular.</p>"
    ) % (summary_html, source, unit_code, review_text)


snapshot_path = _resolve_snapshot_path()
snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
if snapshot.get("schema_version") != 1:
    raise RuntimeError("Unsupported FACODI recovery snapshot schema")
if (snapshot.get("course") or {}).get("code") != "LESTI":
    raise RuntimeError("Snapshot is not the expected LESTI recovery dataset")

playlists = {
    row["unit_code"]: row
    for row in snapshot.get("playlists", [])
    if row.get("unit_code") and row.get("is_public") and (row.get("video_count") or 0) > 0
}

created_channels = 0
updated_channels = 0
channels = {}
for sequence, unit_code in enumerate(sorted(playlists), start=1):
    playlist = playlists[unit_code]
    unit_name = UNIT_NAMES.get(unit_code) or playlist.get("name") or unit_code
    count = int(playlist.get("video_count") or 0)
    confidence = playlist.get("classification_confidence")
    review = playlist.get("review_status") or "needs_review"
    confidence_note = (
        " Confiança editorial histórica: %s." % confidence
        if confidence is not None
        else ""
    )
    values = {
        "name": "LESTI · %s" % unit_name,
        "description_short": "<p>%s recursos abertos recuperados para apoio ao estudo.</p>" % count,
        "description": (
            "<p>Roteiro aberto associado à UC %s — %s, no contexto LESTI/UAlg.</p>"
            "<p>Recuperado do acervo FACODI/Open2: %s recursos; estado histórico: %s.%s</p>"
            "<p><strong>Nota:</strong> correspondência de conteúdo; não constitui "
            "equivalência académica, reconhecimento de ECTS ou substituição do programa oficial.</p>"
        ) % (unit_code, escape(unit_name), count, escape(review), escape(confidence_note)),
        "description_html": (
            "<p>Este curso organiza recursos públicos relacionados com a unidade curricular "
            "%s. Reveja sempre o programa e as orientações oficiais da instituição.</p>"
        ) % unit_code,
        "channel_type": "training",
        "enroll": "public",
        "visibility": "public",
        "is_published": True,
        "sequence": sequence * 10,
    }
    record, created = _upsert_by_xmlid(
        COURSE_XID_PREFIX + unit_code, "slide.channel", values
    )
    channels[unit_code] = record
    created_channels += int(created)
    updated_channels += int(not created)

created_slides = 0
updated_slides = 0
seen = set()
for row in snapshot.get("videos", []):
    unit_code = row.get("unit_code")
    youtube_id = (row.get("youtube_id") or "").strip()
    if unit_code not in channels or not youtube_id:
        continue
    identity = (unit_code, youtube_id)
    if identity in seen:
        continue
    seen.add(identity)

    title = _recovery_title(row, youtube_id)
    values = {
        "name": title,
        "channel_id": channels[unit_code].id,
        # Keep the native Odoo video semantics while suppressing remote
        # metadata fetches through the recovery context above.
        "slide_category": "video",
        "source_type": "external",
        "video_url": "https://www.youtube.com/watch?v=%s" % youtube_id,
        "description": _video_description(row),
        "is_published": True,
        "sequence": int(row.get("position") or 0) + 10,
    }
    _, created = _upsert_by_xmlid(
        "%s%s_%s" % (SLIDE_XID_PREFIX, unit_code, youtube_id),
        "slide.slide",
        values,
    )
    created_slides += int(created)
    updated_slides += int(not created)

# Reconnect recovered learning courses to the currently installed official
# curriculum reference. Never create or rewrite academic units from the legacy
# snapshot because the current Odoo curriculum is authoritative.
Coverage = env["facodi.learning.curriculum.coverage"].sudo()
Unit = env["facodi.learning.curriculum.unit"].sudo()
created_coverages = approved_coverages = proposed_coverages = 0
for unit_code, channel in channels.items():
    unit = Unit.search([("external_unit_code", "=", unit_code)], limit=1)
    if not unit:
        continue
    playlist = playlists[unit_code]
    existing = Coverage.search(
        [
            ("channel_id", "=", channel.id),
            ("curriculum_unit_id", "=", unit.id),
            ("coverage_type", "=", "supports"),
        ],
        limit=1,
    )
    if existing:
        continue
    evidence = {
        "source": "versioned Open2 disaster-recovery snapshot",
        "snapshot": snapshot_path.name,
        "legacy_review_status": playlist.get("review_status"),
        "legacy_classification_confidence": playlist.get("classification_confidence"),
        "boundary": snapshot.get("academic_boundary"),
    }
    coverage = Coverage.create(
        {
            "channel_id": channel.id,
            "curriculum_unit_id": unit.id,
            "coverage_type": "supports",
            "confidence": float(playlist.get("classification_confidence") or 0.0),
            "evidence": evidence,
        }
    )
    created_coverages += 1
    _ensure_xmlid(COVERAGE_XID_PREFIX + unit_code, coverage)
    if playlist.get("review_status") == "auto_reviewed":
        coverage.action_approve()
        approved_coverages += 1
    else:
        proposed_coverages += 1

env.cr.commit()
print(
    "FACODI recovery complete: "
    "channels +%s/~%s, slides +%s/~%s, coverage +%s (%s approved, %s proposed)"
    % (
        created_channels,
        updated_channels,
        created_slides,
        updated_slides,
        created_coverages,
        approved_coverages,
        proposed_coverages,
    )
)
