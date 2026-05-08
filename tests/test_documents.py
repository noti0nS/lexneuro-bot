from io import BytesIO
from zipfile import ZipFile

import pytest
from docx import Document as DocxDocument
from odf.opendocument import OpenDocumentText
from odf.text import P, H

from src.helpers.documents import DocxProcessor, OdtProcessor, get_processor


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    doc = DocxDocument()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_odt_bytes(paragraphs: list[str]) -> bytes:
    doc = OpenDocumentText()
    for text in paragraphs:
        doc.text.addElement(P(text=text))  # pyright: ignore[reportAttributeAccessIssue]
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestGetProcessor:
    def test_docx_key(self) -> None:
        assert isinstance(get_processor("docx"), DocxProcessor)

    def test_odt_key(self) -> None:
        assert isinstance(get_processor("odt"), OdtProcessor)

    def test_dotted_ext(self) -> None:
        assert isinstance(get_processor(".docx"), DocxProcessor)
        assert isinstance(get_processor(".odt"), OdtProcessor)

    def test_uppercase(self) -> None:
        assert isinstance(get_processor("DOCX"), DocxProcessor)
        assert isinstance(get_processor("ODT"), OdtProcessor)

    def test_unsupported(self) -> None:
        with pytest.raises(ValueError, match="unsupported_document_format"):
            get_processor("txt")


class TestDocxProcessor:
    def test_extract_text(self) -> None:
        docx_bytes = _make_docx_bytes(["Hello world", "Second paragraph"])
        result = DocxProcessor().extract_text(docx_bytes)
        assert result == "Hello world\n\nSecond paragraph"

    def test_extract_text_strips_whitespace(self) -> None:
        docx_bytes = _make_docx_bytes(["  spaced  "])
        result = DocxProcessor().extract_text(docx_bytes)
        assert result == "spaced"

    def test_extract_text_empty_paragraphs_skipped(self) -> None:
        docx_bytes = _make_docx_bytes(["", "visible", "   "])
        result = DocxProcessor().extract_text(docx_bytes)
        assert result == "visible"

    def test_extract_text_invalid_zip(self) -> None:
        with pytest.raises(ValueError, match="invalid_docx"):
            DocxProcessor().extract_text(b"not a zip")

    def test_extract_text_missing_document_xml(self) -> None:
        buf = BytesIO()
        with ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        with pytest.raises(ValueError, match="invalid_docx"):
            DocxProcessor().extract_text(buf.getvalue())

    def test_extension(self) -> None:
        assert DocxProcessor.extension == ".docx"


class TestOdtProcessor:
    def test_extract_text(self) -> None:
        odt_bytes = _make_odt_bytes(["Hello world", "Second paragraph"])
        result = OdtProcessor().extract_text(odt_bytes)
        assert result == "Hello world\n\nSecond paragraph"

    def test_extract_text_strips_whitespace(self) -> None:
        odt_bytes = _make_odt_bytes(["  spaced  "])
        result = OdtProcessor().extract_text(odt_bytes)
        assert result == "spaced"

    def test_extract_text_empty_paragraphs_skipped(self) -> None:
        odt_bytes = _make_odt_bytes(["", "visible", "   "])
        result = OdtProcessor().extract_text(odt_bytes)
        assert result == "visible"

    def test_extract_text_invalid_zip(self) -> None:
        with pytest.raises(ValueError, match="invalid_odt"):
            OdtProcessor().extract_text(b"not a zip")

    def test_extract_text_missing_content_xml(self) -> None:
        buf = BytesIO()
        with ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        with pytest.raises(ValueError, match="invalid_odt"):
            OdtProcessor().extract_text(buf.getvalue())

    def test_extract_text_with_headings(self) -> None:
        doc = OpenDocumentText()
        doc.text.addElement(P(text="A paragraph"))  # pyright: ignore[reportAttributeAccessIssue]
        doc.text.addElement(H(outlinelevel="1", text="A heading"))  # pyright: ignore[reportAttributeAccessIssue]
        buf = BytesIO()
        doc.save(buf)
        result = OdtProcessor().extract_text(buf.getvalue())
        assert "A paragraph" in result
        assert "A heading" in result

    def test_extension(self) -> None:
        assert OdtProcessor.extension == ".odt"
