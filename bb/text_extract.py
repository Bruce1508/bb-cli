"""Extract plain text from downloaded course files — one string per page or slide.

PDF via pdfplumber. DOCX/PPTX are zipped XML, so stdlib zipfile + ElementTree is enough.
Results are cached in ~/.bb/text/ keyed by file mtime, because PDF parsing is slow and
search_file_text reads every file.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pdfplumber

import bb.config as _config_module

SUPPORTED = {".pdf", ".docx", ".pptx", ".txt", ".md"}
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_MAX_XML_BYTES = 20_000_000  # refuse zip-bomb-sized XML parts
_SLIDE_RE = re.compile(r"ppt/slides/slide(\d+)\.xml")


class UnsupportedFile(Exception):
    """File type we cannot extract text from."""


def _read_xml(z: zipfile.ZipFile, name: str) -> ET.Element:
    if z.getinfo(name).file_size > _MAX_XML_BYTES:
        raise ValueError(f"{name} too large")
    data = z.read(name)
    # Valid OOXML never has a DTD. Refusing one blocks entity-expansion (billion laughs)
    # without adding defusedxml; stdlib ElementTree already ignores external entities (no XXE).
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError(f"{name} contains a DTD")
    return ET.fromstring(data)


def _paragraphs(root: ET.Element, ns: str) -> str:
    paras = ("".join(t.text or "" for t in p.iter(f"{ns}t")) for p in root.iter(f"{ns}p"))
    return "\n".join(p for p in paras if p)


def _pdf_pages(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def _docx_pages(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        root = _read_xml(z, "word/document.xml")
    return [_paragraphs(root, _W)]  # DOCX has no fixed pages — one "page"


def _pptx_pages(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        slides = sorted(
            (int(m.group(1)), n) for n in z.namelist() if (m := _SLIDE_RE.fullmatch(n))
        )
        return [_paragraphs(_read_xml(z, n), _A) for _, n in slides]


def _cache_file(path: Path) -> Path:
    bb_dir = _config_module.BB_DIR
    try:
        rel = path.resolve().relative_to((bb_dir / "files").resolve())
    except ValueError:
        rel = Path(path.name)
    return bb_dir / "text" / rel.parent / (rel.name + ".json")


def extract_pages(path: Path) -> list[str]:
    """Return the text of each page/slide. Raises UnsupportedFile for other file types."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise UnsupportedFile(suffix or "no extension")

    cache = _cache_file(path)
    mtime = path.stat().st_mtime
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached["mtime"] == mtime:
            return cached["pages"]
    except (OSError, ValueError, KeyError):
        pass

    if suffix == ".pdf":
        pages = _pdf_pages(path)
    elif suffix == ".docx":
        pages = _docx_pages(path)
    elif suffix == ".pptx":
        pages = _pptx_pages(path)
    else:
        pages = [path.read_text(encoding="utf-8", errors="replace")]

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"mtime": mtime, "pages": pages}), encoding="utf-8")
    except OSError:
        pass  # cache is an optimisation; never fail a read because of it
    return pages
