"""
Tests for bb/models/content.py — ContentItem, ContentTree, TYPE_ICONS,
and the four serialization helpers.

Strategy:
- Pure functions / dataclasses — no DB, no filesystem, no mocks needed
- Roundtrip tests are the strongest signal: data that goes in must come back out unchanged

Success criteria:
- ContentItem: required fields, optional fields default to None, children defaults to []
- ContentTree: required fields, items defaults to []
- TYPE_ICONS: dict, contains all 6 expected type keys
- content_item_to_dict: produces dict with correct keys; children serialized recursively
- content_item_from_dict: reconstructs ContentItem; handles missing optional keys via .get
- content_tree_to_dict: scraped_at serialized as ISO string (not datetime); items serialized
- content_tree_from_dict: scraped_at deserialized as datetime object (timezone-aware)
- Roundtrip ContentItem (flat + nested children)
- Roundtrip ContentTree preserves all fields
"""
from datetime import datetime, timezone

import pytest

from bb.models.content import (
    TYPE_ICONS,
    ContentItem,
    ContentTree,
    content_item_from_dict,
    content_item_to_dict,
    content_tree_from_dict,
    content_tree_to_dict,
)

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ContentItem — dataclass defaults
# ---------------------------------------------------------------------------


def test_content_item_requires_type_and_title():
    item = ContentItem(type="file", title="Lab 1.pdf")
    assert item.type == "file"
    assert item.title == "Lab 1.pdf"


def test_content_item_url_defaults_to_none():
    item = ContentItem(type="file", title="x")
    assert item.url is None


def test_content_item_download_url_defaults_to_none():
    item = ContentItem(type="file", title="x")
    assert item.download_url is None


def test_content_item_size_bytes_defaults_to_none():
    item = ContentItem(type="file", title="x")
    assert item.size_bytes is None


def test_content_item_mime_type_defaults_to_none():
    item = ContentItem(type="file", title="x")
    assert item.mime_type is None


def test_content_item_children_defaults_to_empty_list():
    item = ContentItem(type="module", title="Week 1")
    assert item.children == []


def test_content_item_children_are_independent_per_instance():
    """Mutable default — field(default_factory=list) must give each instance its own list."""
    a = ContentItem(type="module", title="A")
    b = ContentItem(type="module", title="B")
    a.children.append(ContentItem(type="file", title="child"))
    assert b.children == []


# ---------------------------------------------------------------------------
# ContentTree — dataclass defaults
# ---------------------------------------------------------------------------


def test_content_tree_requires_code_id_and_scraped_at():
    tree = ContentTree(course_code="BTP200", course_bb_id="_773522_1", scraped_at=NOW)
    assert tree.course_code == "BTP200"
    assert tree.course_bb_id == "_773522_1"
    assert tree.scraped_at == NOW


def test_content_tree_items_defaults_to_empty_list():
    tree = ContentTree(course_code="BTP200", course_bb_id="_773522_1", scraped_at=NOW)
    assert tree.items == []


def test_content_tree_scraped_at_is_datetime():
    tree = ContentTree(course_code="BTP200", course_bb_id="_773522_1", scraped_at=NOW)
    assert isinstance(tree.scraped_at, datetime)


# ---------------------------------------------------------------------------
# TYPE_ICONS
# ---------------------------------------------------------------------------


def test_type_icons_is_dict():
    assert isinstance(TYPE_ICONS, dict)


def test_type_icons_has_module():
    assert "module" in TYPE_ICONS


def test_type_icons_has_file():
    assert "file" in TYPE_ICONS


def test_type_icons_has_folder():
    assert "folder" in TYPE_ICONS


def test_type_icons_has_discussion():
    assert "discussion" in TYPE_ICONS


def test_type_icons_has_link():
    assert "link" in TYPE_ICONS


def test_type_icons_has_assignment():
    assert "assignment" in TYPE_ICONS


def test_type_icons_values_are_strings():
    assert all(isinstance(v, str) for v in TYPE_ICONS.values())


# ---------------------------------------------------------------------------
# content_item_to_dict
# ---------------------------------------------------------------------------


def test_content_item_to_dict_returns_dict():
    item = ContentItem(type="file", title="notes.pdf")
    assert isinstance(content_item_to_dict(item), dict)


def test_content_item_to_dict_has_all_keys():
    d = content_item_to_dict(ContentItem(type="file", title="x"))
    for key in ("type", "title", "url", "download_url", "size_bytes", "mime_type", "children"):
        assert key in d


def test_content_item_to_dict_type_value():
    d = content_item_to_dict(ContentItem(type="file", title="x"))
    assert d["type"] == "file"


def test_content_item_to_dict_title_value():
    d = content_item_to_dict(ContentItem(type="file", title="Lecture Slides"))
    assert d["title"] == "Lecture Slides"


def test_content_item_to_dict_none_optionals_serialize_as_none():
    d = content_item_to_dict(ContentItem(type="file", title="x"))
    assert d["url"] is None
    assert d["download_url"] is None
    assert d["size_bytes"] is None
    assert d["mime_type"] is None


def test_content_item_to_dict_children_is_list():
    d = content_item_to_dict(ContentItem(type="module", title="Week 1"))
    assert isinstance(d["children"], list)


def test_content_item_to_dict_children_serialized_recursively():
    child = ContentItem(type="file", title="Lab 1.pdf")
    parent = ContentItem(type="module", title="Week 1", children=[child])
    d = content_item_to_dict(parent)
    assert len(d["children"]) == 1
    assert d["children"][0]["title"] == "Lab 1.pdf"


# ---------------------------------------------------------------------------
# content_item_from_dict
# ---------------------------------------------------------------------------


def test_content_item_from_dict_returns_content_item():
    d = {"type": "file", "title": "x"}
    assert isinstance(content_item_from_dict(d), ContentItem)


def test_content_item_from_dict_reads_type_and_title():
    item = content_item_from_dict({"type": "discussion", "title": "Forum"})
    assert item.type == "discussion"
    assert item.title == "Forum"


def test_content_item_from_dict_optional_fields_default_to_none():
    item = content_item_from_dict({"type": "file", "title": "x"})
    assert item.url is None
    assert item.download_url is None
    assert item.size_bytes is None
    assert item.mime_type is None


def test_content_item_from_dict_children_default_empty():
    item = content_item_from_dict({"type": "module", "title": "W1"})
    assert item.children == []


def test_content_item_from_dict_deserializes_children():
    d = {
        "type": "module",
        "title": "Week 1",
        "children": [{"type": "file", "title": "notes.pdf"}],
    }
    item = content_item_from_dict(d)
    assert len(item.children) == 1
    assert isinstance(item.children[0], ContentItem)
    assert item.children[0].title == "notes.pdf"


# ---------------------------------------------------------------------------
# content_item roundtrip
# ---------------------------------------------------------------------------


def test_content_item_roundtrip_flat():
    original = ContentItem(
        type="file",
        title="Syllabus.pdf",
        url="/ultra/courses/_1_1/file",
        download_url="/bbcswebdav/file.pdf",
        size_bytes=1024,
        mime_type="application/pdf",
    )
    result = content_item_from_dict(content_item_to_dict(original))
    assert result.type == original.type
    assert result.title == original.title
    assert result.url == original.url
    assert result.download_url == original.download_url
    assert result.size_bytes == original.size_bytes
    assert result.mime_type == original.mime_type


def test_content_item_roundtrip_nested_children():
    grandchild = ContentItem(type="file", title="slide.pptx")
    child = ContentItem(type="folder", title="Slides", children=[grandchild])
    parent = ContentItem(type="module", title="Week 1", children=[child])

    result = content_item_from_dict(content_item_to_dict(parent))
    assert len(result.children) == 1
    assert result.children[0].title == "Slides"
    assert len(result.children[0].children) == 1
    assert result.children[0].children[0].title == "slide.pptx"


# ---------------------------------------------------------------------------
# content_tree_to_dict
# ---------------------------------------------------------------------------


def test_content_tree_to_dict_returns_dict():
    tree = ContentTree(course_code="BTP200", course_bb_id="_1_1", scraped_at=NOW)
    assert isinstance(content_tree_to_dict(tree), dict)


def test_content_tree_to_dict_has_required_keys():
    d = content_tree_to_dict(ContentTree(course_code="BTP200", course_bb_id="_1_1", scraped_at=NOW))
    for key in ("course_code", "course_bb_id", "scraped_at", "items"):
        assert key in d


def test_content_tree_to_dict_scraped_at_is_string():
    """scraped_at must be serialized to an ISO string — not a datetime object."""
    d = content_tree_to_dict(ContentTree(course_code="BTP200", course_bb_id="_1_1", scraped_at=NOW))
    assert isinstance(d["scraped_at"], str)


def test_content_tree_to_dict_scraped_at_is_isoformat():
    d = content_tree_to_dict(ContentTree(course_code="BTP200", course_bb_id="_1_1", scraped_at=NOW))
    # Must be parseable back to datetime
    parsed = datetime.fromisoformat(d["scraped_at"])
    assert isinstance(parsed, datetime)


def test_content_tree_to_dict_items_is_list():
    d = content_tree_to_dict(ContentTree(course_code="BTP200", course_bb_id="_1_1", scraped_at=NOW))
    assert isinstance(d["items"], list)


def test_content_tree_to_dict_items_serialized():
    item = ContentItem(type="file", title="Lab 1")
    tree = ContentTree(course_code="BTP200", course_bb_id="_1_1", scraped_at=NOW, items=[item])
    d = content_tree_to_dict(tree)
    assert len(d["items"]) == 1
    assert d["items"][0]["title"] == "Lab 1"


# ---------------------------------------------------------------------------
# content_tree_from_dict
# ---------------------------------------------------------------------------


def test_content_tree_from_dict_returns_content_tree():
    d = {
        "course_code": "BTP200",
        "course_bb_id": "_1_1",
        "scraped_at": NOW.isoformat(),
        "items": [],
    }
    assert isinstance(content_tree_from_dict(d), ContentTree)


def test_content_tree_from_dict_scraped_at_is_datetime():
    d = {
        "course_code": "BTP200",
        "course_bb_id": "_1_1",
        "scraped_at": NOW.isoformat(),
        "items": [],
    }
    tree = content_tree_from_dict(d)
    assert isinstance(tree.scraped_at, datetime)


def test_content_tree_from_dict_scraped_at_is_timezone_aware():
    d = {
        "course_code": "BTP200",
        "course_bb_id": "_1_1",
        "scraped_at": NOW.isoformat(),
        "items": [],
    }
    tree = content_tree_from_dict(d)
    assert tree.scraped_at.tzinfo is not None


def test_content_tree_from_dict_items_default_empty():
    d = {
        "course_code": "BTP200",
        "course_bb_id": "_1_1",
        "scraped_at": NOW.isoformat(),
    }
    tree = content_tree_from_dict(d)
    assert tree.items == []


# ---------------------------------------------------------------------------
# ContentTree roundtrip
# ---------------------------------------------------------------------------


def test_content_tree_roundtrip_preserves_course_code():
    original = ContentTree(course_code="BTP200", course_bb_id="_773522_1", scraped_at=NOW)
    result = content_tree_from_dict(content_tree_to_dict(original))
    assert result.course_code == "BTP200"


def test_content_tree_roundtrip_preserves_bb_id():
    original = ContentTree(course_code="BTP200", course_bb_id="_773522_1", scraped_at=NOW)
    result = content_tree_from_dict(content_tree_to_dict(original))
    assert result.course_bb_id == "_773522_1"


def test_content_tree_roundtrip_preserves_scraped_at_value():
    original = ContentTree(course_code="BTP200", course_bb_id="_1_1", scraped_at=NOW)
    result = content_tree_from_dict(content_tree_to_dict(original))
    # Compare at second precision (isoformat truncates microseconds in some formats)
    assert abs((result.scraped_at - original.scraped_at).total_seconds()) < 1


def test_content_tree_roundtrip_preserves_items():
    item = ContentItem(type="file", title="Lab 1.pdf", url="/ultra/file")
    original = ContentTree(
        course_code="BTP200", course_bb_id="_1_1", scraped_at=NOW, items=[item]
    )
    result = content_tree_from_dict(content_tree_to_dict(original))
    assert len(result.items) == 1
    assert result.items[0].title == "Lab 1.pdf"
    assert result.items[0].url == "/ultra/file"
