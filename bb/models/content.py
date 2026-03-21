from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ContentItem:
    type: str                            # "module" | "file" | "folder" | "discussion" | "link" | "assignment"
    title: str
    url: str | None = None               # Blackboard view URL
    download_url: str | None = None      # Direct file download URL (bbcswebdav/*)
    size_bytes: int | None = None
    mime_type: str | None = None
    children: list[ContentItem] = field(default_factory=list)


@dataclass
class ContentTree:
    course_code: str       # "BTP200" — always uppercase
    course_bb_id: str      # "_773522_1"
    scraped_at: datetime   # timezone-aware UTC datetime — never use datetime.utcnow()
    items: list[ContentItem] = field(default_factory=list)


TYPE_ICONS: dict[str, str] = {
    "module":     "📦",
    "file":       "📄",
    "folder":     "📁",
    "discussion": "💬",
    "link":       "🔗",
    "assignment": "📝",
}


def content_item_to_dict(item: ContentItem) -> dict:
    return {
        "type": item.type,
        "title": item.title,
        "url": item.url,
        "download_url": item.download_url,
        "size_bytes": item.size_bytes,
        "mime_type": item.mime_type,
        "children": [content_item_to_dict(c) for c in item.children],
    }


def content_item_from_dict(d: dict) -> ContentItem:
    return ContentItem(
        type=d["type"],
        title=d["title"],
        url=d.get("url"),
        download_url=d.get("download_url"),
        size_bytes=d.get("size_bytes"),
        mime_type=d.get("mime_type"),
        children=[content_item_from_dict(c) for c in d.get("children", [])],
    )


def content_tree_to_dict(tree: ContentTree) -> dict:
    return {
        "course_code": tree.course_code,
        "course_bb_id": tree.course_bb_id,
        "scraped_at": tree.scraped_at.isoformat(),   # datetime → ISO string for JSON
        "items": [content_item_to_dict(i) for i in tree.items],
    }


def content_tree_from_dict(d: dict) -> ContentTree:
    return ContentTree(
        course_code=d["course_code"],
        course_bb_id=d["course_bb_id"],
        scraped_at=datetime.fromisoformat(d["scraped_at"]),   # ISO string → datetime
        items=[content_item_from_dict(i) for i in d.get("items", [])],
    )
