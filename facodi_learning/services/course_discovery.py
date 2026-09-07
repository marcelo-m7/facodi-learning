import json


_SECRET_KEY_FRAGMENTS = (
    "token",
    "authorization",
    "cookie",
    "password",
    "secret",
    "api_key",
    "apikey",
)


def _normalized_key(value):
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _is_secret_key(key):
    normalized = _normalized_key(key)
    return any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS)


def _sanitize_metadata(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _sanitize_metadata(item)
            for key, item in value.items()
            if not _is_secret_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata(item) for item in value]
    raise ValueError("Discovery metadata must be JSON serializable.")


def _clean_required_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Discovery {field_name} must be a non-empty string.")
    return value.strip()


def _clean_optional_text(value, field_name):
    if value in (None, False, ""):
        return False
    if not isinstance(value, str):
        raise ValueError(f"Discovery {field_name} must be text when supplied.")
    return value.strip() or False


def normalize_discovery_item(provider, item):
    """Return one strict, secret-free core course-candidate payload."""
    provider = _clean_required_text(provider, "provider")
    if not isinstance(item, dict):
        raise ValueError("Discovery items must be dictionaries.")

    external_id = _clean_required_text(item.get("external_id"), "external_id")
    name = _clean_required_text(item.get("name"), "name")

    raw_duration = item.get("duration_minutes")
    if raw_duration in (None, False, ""):
        duration_minutes = 0
    else:
        if isinstance(raw_duration, bool):
            raise ValueError("Discovery duration_minutes must be a non-negative number.")
        try:
            duration_minutes = int(raw_duration)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Discovery duration_minutes must be a non-negative number."
            ) from error
        if duration_minutes < 0:
            raise ValueError("Discovery duration_minutes must be non-negative.")

    metadata = _sanitize_metadata(item.get("metadata") or {})
    if not isinstance(metadata, dict):
        raise ValueError("Discovery metadata must be a dictionary.")
    try:
        metadata = json.loads(json.dumps(metadata, ensure_ascii=False))
    except (TypeError, ValueError) as error:
        raise ValueError("Discovery metadata must be JSON serializable.") from error

    return {
        "provider": provider,
        "external_id": external_id,
        "source_url": _clean_optional_text(item.get("source_url"), "source_url"),
        "name": name,
        "description": _clean_optional_text(item.get("description"), "description"),
        "institution": _clean_optional_text(item.get("institution"), "institution"),
        "language": _clean_optional_text(item.get("language"), "language"),
        "level": _clean_optional_text(item.get("level"), "level"),
        "duration_minutes": duration_minutes,
        "license_name": _clean_optional_text(item.get("license_name"), "license_name"),
        "metadata": metadata,
    }
