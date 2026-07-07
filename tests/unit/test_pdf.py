"""Tests for PDF text extraction (src/core/pdf.py)."""

import pytest

from src.core.pdf import PDFExtractionError, extract_pdf_text, looks_like_pdf


def _minimal_pdf(text: str = "Hello Policy") -> bytes:
    """Assemble a minimal valid single-page PDF with computed xref offsets."""
    header = b"%PDF-1.4\n"
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
        b"",  # placeholder for content stream, built below
        (
            b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
            b"\nendobj\n"
        ),
    ]
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects[3] = (
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n"
    )

    body = b""
    offsets = []
    for obj in objects:
        offsets.append(len(header) + len(body))
        body += obj

    xref_pos = len(header) + len(body)
    xref = b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode() + b"\n%%EOF\n"
    )
    return header + body + xref + trailer


class TestExtractPdfText:
    def test_extracts_text_from_valid_pdf(self):
        text = extract_pdf_text(_minimal_pdf("Hello Policy"))
        assert "Hello Policy" in text

    def test_corrupt_bytes_raise(self):
        with pytest.raises(PDFExtractionError):
            extract_pdf_text(b"this is not a pdf at all")

    def test_empty_bytes_raise(self):
        with pytest.raises(PDFExtractionError):
            extract_pdf_text(b"")

    def test_oversized_pdf_rejected(self):
        pdf = _minimal_pdf()
        with pytest.raises(PDFExtractionError, match="too large"):
            extract_pdf_text(pdf, max_bytes=10)


class TestLooksLikePdf:
    def test_by_content_type(self):
        assert looks_like_pdf("https://a.gov/doc", "application/pdf; charset=x")

    def test_by_url_extension(self):
        assert looks_like_pdf("https://a.gov/statute.PDF", "")

    def test_html_is_not_pdf(self):
        assert not looks_like_pdf("https://a.gov/page", "text/html")
