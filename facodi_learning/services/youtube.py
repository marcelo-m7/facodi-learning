import html
import json
import math
import re
import urllib.parse
import urllib.request


YOUTUBE_BASE_URL = "https://www.youtube.com"
_YOUTUBE_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
_INITIAL_DATA_MARKERS = ("var ytInitialData =", 'window["ytInitialData"] =')
_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
_BROWSE_ID_RE = re.compile(r'"browseId":"(UC[A-Za-z0-9_-]+)"')
_CANONICAL_BASE_URL_RE = re.compile(r'"canonicalBaseUrl":"([^"]+)"')
_HTML_LANG_RE = re.compile(r'<html[^>]*\blang="([^"]+)"', re.I)
_TITLE_RE = re.compile(r'<title>(.*?)</title>', re.I | re.S)
_OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"', re.I)
_META_DESCRIPTION_RE = re.compile(r'<meta name="description" content="([^"]*)"', re.I)
_META_SHORT_DESCRIPTION_RE = re.compile(r'"shortDescription":"([^"]*)"', re.I)
_LENGTH_SECONDS_RE = re.compile(r'"lengthSeconds":"(\d+)"')
_PUBLISH_DATE_RE = re.compile(r'"publishDate":"([^"]+)"')
_UPLOAD_DATE_RE = re.compile(r'"uploadDate":"([^"]+)"')


def fetch_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": _YOUTUBE_USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def _extract_json_blob(text, marker):
    marker_index = text.find(marker)
    if marker_index == -1:
        return None
    start = text.find("{", marker_index)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _load_initial_data(html_text):
    for marker in _INITIAL_DATA_MARKERS:
        blob = _extract_json_blob(html_text, marker)
        if blob:
            return json.loads(blob)
    raise ValueError("Unable to extract YouTube initial data.")


def _normalize_text(value):
    if not value:
        return False
    value = html.unescape(str(value))
    value = " ".join(value.split())
    return value or False


def _normalized_first_match(pattern, text):
    match = pattern.search(text or "")
    return _normalize_text(match.group(1)) if match else False


def _find_first_dict_with_key(value, key):
    if isinstance(value, dict):
        if key in value:
            return value
        for child in value.values():
            found = _find_first_dict_with_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_first_dict_with_key(child, key)
            if found is not None:
                return found
    return None


def _text_from_renderer(value):
    if isinstance(value, dict):
        if isinstance(value.get("simpleText"), str):
            return _normalize_text(value["simpleText"])
        runs = value.get("runs")
        if isinstance(runs, list):
            parts = [
                run.get("text")
                for run in runs
                if isinstance(run, dict) and isinstance(run.get("text"), str)
            ]
            return _normalize_text("".join(parts)) if parts else False
    if isinstance(value, str):
        return _normalize_text(value)
    return False


def _channel_context(seed_url, html_text, initial_data):
    channel_metadata = _find_first_dict_with_key(initial_data, "channelMetadataRenderer")
    browse_id = _normalized_first_match(_BROWSE_ID_RE, html_text)
    canonical_base_url = _normalized_first_match(_CANONICAL_BASE_URL_RE, html_text)
    title = False
    description = False
    author_url = False
    if channel_metadata:
        title = _text_from_renderer(channel_metadata.get("title"))
        description = _text_from_renderer(channel_metadata.get("description"))
        author_url = _normalize_text(channel_metadata.get("vanityChannelUrl"))
        browse_id = browse_id or _normalize_text(channel_metadata.get("externalId"))
        canonical_base_url = (
            canonical_base_url
            or _normalize_text(channel_metadata.get("vanityChannelUrl"))
        )
    if not title:
        title = _normalized_first_match(_TITLE_RE, html_text)
        if title and title.endswith(" - YouTube"):
            title = title[: -len(" - YouTube")]
    return {
        "channel_id": browse_id,
        "channel_handle": canonical_base_url,
        "title": title,
        "description": description,
        "author_url": author_url,
        "language": _normalized_first_match(_HTML_LANG_RE, html_text),
        "seed_url": seed_url,
    }


def _unique_video_ids(html_text):
    seen = set()
    ordered = []
    for video_id in _VIDEO_ID_RE.findall(html_text or ""):
        if video_id in seen:
            continue
        seen.add(video_id)
        ordered.append(video_id)
    return ordered


def _watch_url(video_id):
    return f"{YOUTUBE_BASE_URL}/watch?v={video_id}"


def _oembed_video_metadata(video_url):
    query_url = (
        f"{YOUTUBE_BASE_URL}/oembed?url="
        f"{urllib.parse.quote(video_url, safe='')}"
        "&format=json"
    )
    with urllib.request.urlopen(
        urllib.request.Request(query_url, headers={"User-Agent": _YOUTUBE_USER_AGENT}),
        timeout=30,
    ) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def fetch_youtube_video_metadata(video_url):
    watch_url = video_url.split("&", 1)[0]
    if "watch?v=" not in watch_url:
        parsed = urllib.parse.urlparse(video_url)
        video_id = urllib.parse.parse_qs(parsed.query).get("v", [False])[0]
        if not video_id:
            raise ValueError("A YouTube watch URL is required.")
        watch_url = _watch_url(video_id)
    html_text = fetch_url(watch_url)
    oembed = _oembed_video_metadata(watch_url)
    title = _normalized_first_match(_OG_TITLE_RE, html_text) or _normalize_text(
        oembed.get("title")
    )
    description = _normalized_first_match(_META_DESCRIPTION_RE, html_text)
    if not description:
        description = _normalized_first_match(_META_SHORT_DESCRIPTION_RE, html_text)
    length_match = _LENGTH_SECONDS_RE.search(html_text)
    duration_seconds = int(length_match.group(1)) if length_match else 0
    initial_data = _load_initial_data(html_text)
    duration_label = _text_from_renderer(
        _find_first_dict_with_key(initial_data, "lengthText")
    )
    return {
        "watch_url": watch_url,
        "title": title,
        "description": description,
        "author_name": _normalize_text(oembed.get("author_name")),
        "author_url": _normalize_text(oembed.get("author_url")),
        "thumbnail_url": _normalize_text(oembed.get("thumbnail_url")),
        "duration_seconds": duration_seconds,
        "duration_minutes": int(math.ceil(duration_seconds / 60.0)) if duration_seconds else 0,
        "duration_label": duration_label,
        "published_at": _normalized_first_match(_PUBLISH_DATE_RE, html_text)
        or _normalized_first_match(_UPLOAD_DATE_RE, html_text),
    }


def discover_youtube_items(seed_url, limit=20):
    seed_url = (seed_url or "").strip()
    if not seed_url:
        raise ValueError("A YouTube seed URL is required.")
    limit = max(0, int(limit or 0))
    if not limit:
        return []

    html_text = fetch_url(seed_url)
    initial_data = _load_initial_data(html_text)
    channel = _channel_context(seed_url, html_text, initial_data)
    items = []
    for video_id in _unique_video_ids(html_text):
        if len(items) >= limit:
            break
        watch_url = _watch_url(video_id)
        video = fetch_youtube_video_metadata(watch_url)
        items.append(
            {
                "provider": "youtube",
                "external_id": video_id,
                "source_url": video["watch_url"],
                "name": video["title"] or video_id,
                "description": video.get("description") or False,
                "institution": channel.get("title") or video.get("author_name") or False,
                "language": channel.get("language") or False,
                "level": False,
                "duration_minutes": video.get("duration_minutes") or 0,
                "license_name": False,
                "metadata": {
                    "kind": "video",
                    "channel_id": channel.get("channel_id"),
                    "channel_handle": channel.get("channel_handle"),
                    "channel_title": channel.get("title"),
                    "channel_description": channel.get("description"),
                    "description": video.get("description") or False,
                    "author_name": video.get("author_name"),
                    "author_url": video.get("author_url"),
                    "thumbnail_url": video.get("thumbnail_url"),
                    "published_at": video.get("published_at"),
                    "duration_seconds": video.get("duration_seconds"),
                    "duration_label": video.get("duration_label"),
                    "seed_url": seed_url,
                },
            }
        )
    return items


def build_youtube_slide_values(source):
    metadata = dict(source.metadata or {})
    video_url = source.url or metadata.get("watch_url") or metadata.get("seed_url")
    if not video_url and source.external_id:
        video_url = _watch_url(source.external_id)
    description = metadata.get("description") or source.name or ""
    return {
        "name": source.name,
        "slide_category": "video",
        "slide_type": "youtube_video",
        "url": video_url,
        "description": description or False,
    }
