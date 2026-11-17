import zipfile
from unittest.mock import patch

import pytest

from bb.text_extract import UnsupportedFile, extract_pages

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _docx(path, paras):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


def _pptx(path, slides):
    with zipfile.ZipFile(path, "w") as z:
        for i, text in enumerate(slides, start=1):
            z.writestr(
                f"ppt/slides/slide{i}.xml",
                f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:sld>',
            )


@pytest.fixture(autouse=True)
def bb_dir(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        yield tmp_path


def test_docx_paragraphs(tmp_path):
    f = tmp_path / "files" / "BTP200" / "notes.docx"
    f.parent.mkdir(parents=True)
    _docx(f, ["Intro", "Recursion calls itself"])
    assert extract_pages(f) == ["Intro\nRecursion calls itself"]


def test_pptx_slides_in_numeric_order(tmp_path):
    f = tmp_path / "deck.pptx"
    _pptx(f, [f"Slide {i}" for i in range(1, 12)])  # slide10/11 must sort after slide2
    pages = extract_pages(f)
    assert pages[1] == "Slide 2" and pages[9] == "Slide 10" and len(pages) == 11


def test_txt_and_md(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# Week 3\nNormalization")
    assert extract_pages(f) == ["# Week 3\nNormalization"]


def test_docx_with_dtd_is_rejected(tmp_path):
    f = tmp_path / "bomb.docx"
    xml = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
           f'<w:document xmlns:w="{W}"><w:body/></w:document>')
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("word/document.xml", xml)
    with pytest.raises(ValueError, match="DTD"):
        extract_pages(f)


def test_unsupported(tmp_path):
    f = tmp_path / "a.zip"
    f.write_bytes(b"PK")
    with pytest.raises(UnsupportedFile):
        extract_pages(f)


def test_result_is_cached_until_file_changes(tmp_path):
    f = tmp_path / "files" / "BTP200" / "a.pdf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"%PDF")
    with patch("bb.text_extract._pdf_pages", return_value=["one"]) as pdf:
        assert extract_pages(f) == ["one"]
        assert extract_pages(f) == ["one"]
    assert pdf.call_count == 1
    assert (tmp_path / "text" / "BTP200" / "a.pdf.json").exists()
