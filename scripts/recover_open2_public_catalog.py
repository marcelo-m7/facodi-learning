#!/usr/bin/env python3
"""Recover the wider historical FACODI/Open2 public learning catalogue.

This script consumes recovery/open2_public_catalog_2026-09-28.json and is
intentionally conservative about publication:

* LESTI resources are restored using the existing deterministic FACODI IDs.
* Historical LDC playlist code is normalized to the course code LDCOM.
* Generic/public playlists marked auto_reviewed/reviewed are publishable.
* needs_review material is recovered as draft, not silently promoted.
* The historical Odoo 18 HR playlist is recovered as draft because its product
  version is no longer current for FACODI's Odoo 19 context.
* Academic coverage is only created when a matching CURRENT Odoo curriculum
  unit already exists. Legacy unit facts never overwrite the current reference.

Run inside an Odoo shell after facodi_learning + website_slides are installed.
"""

import json
import os
import re
from html import escape
from pathlib import Path

SNAPSHOT_ENV = "FACODI_PUBLIC_RECOVERY_SNAPSHOT"
DEFAULT_SNAPSHOT = Path("recovery/open2_public_catalog_2026-09-28.json")

COURSE_ALIASES = {"LDC": "LDCOM"}
ACADEMIC_CODES = {"LESTI", "LDCOM"}


def _slug(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "catalog"


def _resolve_snapshot_path():
    explicit = os.environ.get(SNAPSHOT_ENV)
    if explicit:
        return Path(explicit)
    for candidate in (
        DEFAULT_SNAPSHOT,
        Path("/mnt/extra-addons/facodi_learning") / DEFAULT_SNAPSHOT,
        Path("/opt/odoo/custom-addons/facodi_learning") / DEFAULT_SNAPSHOT,
        Path("/addons/facodi_learning") / DEFAULT_SNAPSHOT,
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Set %s to the recovery snapshot path" % SNAPSHOT_ENV)


def _xmlid_record(xmlid, model):
    record = env.ref(xmlid, raise_if_not_found=False)
    if record and record._name == model and record.exists():
        return record
    return env[model].browse()


def _ensure_xmlid(xmlid, record):
    module, name = xmlid.split(".", 1)
    imd = env["ir.model.data"].sudo()
    found = imd.search([("module", "=", module), ("name", "=", name)], limit=1)
    values = {
        "module": module,
        "name": name,
        "model": record._name,
        "res_id": record.id,
        "noupdate": False,
    }
    if found:
        found.write(values)
    else:
        imd.create(values)


def _upsert(xmlid, model, values):
    rec = _xmlid_record(xmlid, model)
    Model = env[model].sudo().with_context(
        tracking_disable=True,
        website_slides_skip_fetch_metadata=True,
    )
    if rec:
        rec.sudo().with_context(
            tracking_disable=True,
            website_slides_skip_fetch_metadata=True,
        ).write(values)
        return rec, False
    rec = Model.create(values)
    _ensure_xmlid(xmlid, rec)
    return rec, True


def _course_code(playlist):
    raw = playlist.get("course_code")
    return COURSE_ALIASES.get(raw, raw)


def _publication_state(playlist):
    review = playlist.get("review_status") or "needs_review"
    course_code = _course_code(playlist)
    unit_code = playlist.get("unit_code")

    # Existing LESTI recovery policy already publishes the seven recoverable UCs.
    if course_code == "LESTI" and unit_code:
        return True
    # Old Odoo 18 learning material is useful but version-sensitive.
    if course_code == "odoo":
        return False
    return review in {"auto_reviewed", "reviewed"}


def _channel_xmlid(playlist):
    course_code = _course_code(playlist)
    unit_code = playlist.get("unit_code")
    if course_code == "LESTI" and unit_code:
        return "__import__.facodi_lesti_%s" % unit_code
    if course_code == "LDCOM" and unit_code:
        return "__import__.facodi_ldcom_%s" % unit_code
    return "__import__.facodi_catalog_%s" % _slug(playlist.get("slug") or playlist.get("name"))


def _channel_name(playlist):
    course_code = _course_code(playlist)
    unit_code = playlist.get("unit_code")
    name = (playlist.get("name") or unit_code or "Open course").strip()
    if course_code == "LDCOM":
        cleaned = re.sub(r"\s*-\s*\d+º Ano.*$", "", name).strip()
        return "LDCOM · %s" % cleaned
    if course_code == "LESTI":
        cleaned = re.sub(r"\s*-\s*\d+º Ano.*$", "", name).strip()
        if cleaned.startswith("LESTI ·"):
            return cleaned
        return "LESTI · %s" % cleaned
    if course_code == "odoo":
        return "Odoo 18 · Recursos Humanos"
    return name


def _slide_xmlid(playlist, item):
    course_code = _course_code(playlist)
    unit_code = playlist.get("unit_code")
    youtube_id = item["youtube_id"]
    if course_code == "LESTI" and unit_code:
        return "__import__.facodi_link_%s_%s" % (unit_code, youtube_id)
    base = unit_code or playlist.get("slug") or playlist.get("name")
    return "__import__.facodi_link_%s_%s" % (_slug(base), youtube_id)


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


def _description(playlist, item):
    summary = item.get("short_summary") or item.get("summary_description") or ""
    source = item.get("channel_name") or "YouTube"
    review = playlist.get("review_status") or "needs_review"
    blocks = []
    if summary:
        blocks.append("<p>%s</p>" % escape(str(summary).strip()))
    blocks.append(
        "<p>Fonte: %s. Recurso recuperado do catálogo histórico FACODI/Open2. "
        "Estado editorial histórico: %s.</p>"
        % (escape(source), escape(review))
    )
    if _course_code(playlist) in ACADEMIC_CODES:
        blocks.append(
            "<p><strong>Fronteira académica:</strong> correspondência de conteúdo "
            "para apoio ao estudo; não constitui equivalência académica, reconhecimento "
            "de ECTS, aprovação ou progressão curricular.</p>"
        )
    if _course_code(playlist) == "odoo":
        blocks.append(
            "<p><strong>Nota de versão:</strong> o acervo foi classificado historicamente "
            "para Odoo 18 e deve ser revisto antes de ser apresentado como material atual de Odoo 19.</p>"
        )
    return "".join(blocks)


snapshot_path = _resolve_snapshot_path()
snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
if snapshot.get("schema_version") != 1:
    raise RuntimeError("Unsupported public recovery snapshot schema")

playlists = {
    row["slug"]: row
    for row in snapshot.get("playlists", [])
    if row.get("slug") and row.get("is_public") and (row.get("video_count") or 0) > 0
}
items_by_playlist = {}
for item in snapshot.get("playlist_items", []):
    slug = item.get("playlist_slug")
    youtube_id = item.get("youtube_id")
    if slug in playlists and youtube_id:
        items_by_playlist.setdefault(slug, []).append(item)

stats = {
    "channels_created": 0,
    "channels_updated": 0,
    "slides_created": 0,
    "slides_updated": 0,
    "published_channels": 0,
    "draft_channels": 0,
    "coverage_created": 0,
    "coverage_approved": 0,
    "coverage_proposed": 0,
}
channels = {}

for sequence, slug in enumerate(sorted(playlists), start=1):
    playlist = playlists[slug]
    publish = _publication_state(playlist)
    name = _channel_name(playlist)
    course_code = _course_code(playlist)
    unit_code = playlist.get("unit_code")
    count = len(items_by_playlist.get(slug, []))
    tags = ", ".join(playlist.get("tags") or [])
    version_note = ""
    if course_code == "odoo":
        version_note = (
            "<p><strong>Recuperado como rascunho:</strong> conteúdo historicamente "
            "classificado para Odoo 18; requer revisão para Odoo 19.</p>"
        )
    academic_note = ""
    if course_code in ACADEMIC_CODES:
        academic_note = (
            "<p><strong>Fronteira académica:</strong> este curso organiza recursos "
            "de apoio ao estudo e não substitui o programa oficial nem constitui "
            "equivalência ou reconhecimento de créditos.</p>"
        )
    vals = {
        "name": name,
        "description_short": "<p>%s recursos abertos recuperados.</p>" % count,
        "description": (
            "<p>Catálogo histórico FACODI/Open2 recuperado após perda da base Odoo.</p>"
            "<p>Estado editorial histórico: %s%s%s</p>%s%s"
            % (
                escape(playlist.get("review_status") or "needs_review"),
                (" · confiança %s" % playlist.get("classification_confidence"))
                if playlist.get("classification_confidence") is not None else "",
                (" · tags: %s" % escape(tags)) if tags else "",
                version_note,
                academic_note,
            )
        ),
        "channel_type": "training",
        "enroll": "public",
        "visibility": "public",
        "is_published": publish,
        "sequence": sequence * 10,
    }
    channel, created = _upsert(_channel_xmlid(playlist), "slide.channel", vals)
    channels[slug] = channel
    stats["channels_created" if created else "channels_updated"] += 1
    stats["published_channels" if publish else "draft_channels"] += 1

for slug, playlist in playlists.items():
    channel = channels[slug]
    seen = set()
    for item in sorted(items_by_playlist.get(slug, []), key=lambda r: int(r.get("position") or 0)):
        youtube_id = item["youtube_id"]
        if youtube_id in seen:
            continue
        seen.add(youtube_id)
        title = _recovery_title(item, youtube_id)
        vals = {
            "name": title,
            "channel_id": channel.id,
            "slide_category": "video",
            "source_type": "external",
            "video_url": "https://www.youtube.com/watch?v=%s" % youtube_id,
            "description": _description(playlist, item),
            "is_published": bool(channel.is_published),
            "sequence": int(item.get("position") or 0) + 10,
        }
        _, created = _upsert(_slide_xmlid(playlist, item), "slide.slide", vals)
        stats["slides_created" if created else "slides_updated"] += 1

# Only attach academic coverage when the current canonical curriculum already
# contains the unit. Historical Open2 unit rows are deliberately never imported
# into the current academic reference.
Coverage = env["facodi.learning.curriculum.coverage"].sudo()
Unit = env["facodi.learning.curriculum.unit"].sudo()
for slug, playlist in playlists.items():
    course_code = _course_code(playlist)
    unit_code = playlist.get("unit_code")
    if course_code not in ACADEMIC_CODES or not unit_code:
        continue
    unit = Unit.search([("external_unit_code", "=", unit_code)], limit=1)
    if not unit:
        continue
    channel = channels[slug]
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
    coverage = Coverage.create(
        {
            "channel_id": channel.id,
            "curriculum_unit_id": unit.id,
            "coverage_type": "supports",
            "confidence": float(playlist.get("classification_confidence") or 0),
            "evidence": {
                "source": "Open2 public-catalog recovery snapshot",
                "snapshot": snapshot_path.name,
                "legacy_course_code": playlist.get("course_code"),
                "normalized_course_code": course_code,
                "legacy_review_status": playlist.get("review_status"),
                "boundary": snapshot.get("academic_boundary"),
            },
        }
    )
    stats["coverage_created"] += 1
    if playlist.get("review_status") == "auto_reviewed":
        coverage.action_approve()
        stats["coverage_approved"] += 1
    else:
        stats["coverage_proposed"] += 1

env.cr.commit()
print("FACODI wider public catalogue recovery complete: %s" % stats)
