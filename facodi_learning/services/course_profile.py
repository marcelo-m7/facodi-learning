from collections import Counter, defaultdict

from odoo.tools import html2plaintext


COURSE_PROFILE_VERSION = "course-profile-v1"
COURSE_CATEGORIES = ("article", "document", "infographic", "quiz", "video")


def _plain_text(value):
    if not value:
        return ""
    return " ".join(html2plaintext(value).split())


def _ordered_content(slides):
    return slides.sorted(key=lambda slide: (slide.sequence, slide.id))


def _ordered_tags(tags):
    return tags.sorted(key=lambda tag: ((tag.name or "").casefold(), tag.id))


def _course_tags(channel):
    tags = channel.tag_ids.sorted(
        key=lambda tag: (tag.group_sequence, tag.sequence, tag.id)
    )
    return [
        {
            "id": tag.id,
            "name": tag.name or "",
            "group_id": tag.group_id.id,
            "group_name": tag.group_id.name or "",
        }
        for tag in tags
    ]


def _sections_and_contents(channel):
    sections = channel.slide_category_ids.sorted(
        key=lambda slide: (slide.sequence, slide.id)
    )
    contents = _ordered_content(channel.slide_content_ids)
    content_by_section = defaultdict(list)
    category_counts = Counter({category: 0 for category in COURSE_CATEGORIES})

    normalized_contents = []
    for slide in contents:
        category_counts[slide.slide_category] += 1
        content_by_section[slide.category_id.id].append(slide.id)
        tags = _ordered_tags(slide.tag_ids)
        normalized_contents.append(
            {
                "id": slide.id,
                "name": slide.name or "",
                "sequence": slide.sequence,
                "section_id": slide.category_id.id or False,
                "slide_category": slide.slide_category,
                "slide_type": slide.slide_type or False,
                "completion_time": float(slide.completion_time or 0.0),
                "tag_ids": tags.ids,
                "tag_names": [tag.name or "" for tag in tags],
            }
        )

    normalized_sections = [
        {
            "id": section.id,
            "name": section.name or "",
            "sequence": section.sequence,
            "content_ids": content_by_section.get(section.id, []),
            "duration": float(section.completion_time or 0.0),
        }
        for section in sections
    ]
    return normalized_sections, normalized_contents, dict(category_counts)


def build_course_profile(channel):
    channel.ensure_one()
    channel.check_access("read")

    sections, contents, category_counts = _sections_and_contents(channel)

    return {
        "schema_version": COURSE_PROFILE_VERSION,
        "channel": {
            "id": channel.id,
            "name": channel.name or "",
            "channel_type": channel.channel_type,
            "active": bool(channel.active),
            "website_id": channel.website_id.id or False,
            "website_published": bool(channel.website_published),
            "visibility": channel.visibility,
            "enroll": channel.enroll,
            "description": _plain_text(channel.description),
            "short_description": _plain_text(channel.description_short),
            "detailed_description": _plain_text(channel.description_html),
        },
        "course_tags": _course_tags(channel),
        "prerequisite_channel_ids": sorted(channel.prerequisite_channel_ids.ids),
        "structure": {
            "section_count": len(sections),
            "content_count": len(contents),
            "total_duration": float(channel.total_time or 0.0),
            "category_counts": {
                category: category_counts.get(category, 0)
                for category in COURSE_CATEGORIES
            },
        },
        "sections": sections,
        "contents": contents,
        "analysis": {"analyzed_content_count": 0, "detected_languages": []},
        "approved_content_relations": {"outgoing": [], "incoming": []},
    }
