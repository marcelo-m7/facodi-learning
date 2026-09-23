import hashlib
import json


def canonical_payload_bytes(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_payload_hash(payload):
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def curriculum_payload_diff(previous, current):
    """Return a compact, deterministic editorial diff between two payloads."""
    previous = previous or {}
    current = current or {}
    old_units = {
        row["external_unit_code"]: row for row in previous.get("units", [])
    }
    new_units = {
        row["external_unit_code"]: row for row in current.get("units", [])
    }
    shared = old_units.keys() & new_units.keys()
    changed = sorted(code for code in shared if old_units[code] != new_units[code])

    def occurrence_key(row):
        return (
            row["external_unit_code"],
            row["curricular_year"],
            row["period"],
            row.get("option_group_external_id") or "",
        )

    old_occurrences = {
        occurrence_key(row) for row in previous.get("occurrences", [])
    }
    new_occurrences = {
        occurrence_key(row) for row in current.get("occurrences", [])
    }
    return {
        "units_added": sorted(new_units.keys() - old_units.keys()),
        "units_removed": sorted(old_units.keys() - new_units.keys()),
        "units_changed": changed,
        "occurrences_added": [list(key) for key in sorted(new_occurrences - old_occurrences)],
        "occurrences_removed": [list(key) for key in sorted(old_occurrences - new_occurrences)],
    }