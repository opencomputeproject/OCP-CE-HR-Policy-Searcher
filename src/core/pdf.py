"""PDF text extraction for the crawler.

Laws, statutes, and regulations are overwhelmingly published as PDFs.
Before this module existed the crawler dropped every PDF link, making
the highest-value documents on legislative sites invisible.
"""

import io
import logging
from urllib.parse import urlparse

from pypdf import PdfReader

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 25 * 1024 * 1024  # statutes are big; scanned archives are bigger
MAX_PDF_PAGES = 200


class PDFExtractionError(Exception):
    """PDF could not be parsed into usable text."""


def looks_like_pdf(url: str, content_type: str) -> bool:
    """Decide whether a response should go through PDF extraction."""
    if "application/pdf" in (content_type or "").lower():
        return True
    return urlparse(url).path.lower().endswith(".pdf")


def extract_pdf_text(
    data: bytes,
    max_bytes: int = MAX_PDF_BYTES,
    max_pages: int = MAX_PDF_PAGES,
) -> str:
    """Extract plain text from PDF bytes.

    Raises:
        PDFExtractionError: on oversized, corrupt, or textless PDFs.
    """
    if not data:
        raise PDFExtractionError("Empty PDF response")
    if len(data) > max_bytes:
        raise PDFExtractionError(
            f"PDF too large: {len(data)} bytes (limit {max_bytes})"
        )

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages[:max_pages]
        if len(reader.pages) > max_pages:
            logger.info(
                "PDF has %d pages; extracting first %d",
                len(reader.pages), max_pages,
            )
        text = "\n".join(page.extract_text() or "" for page in pages)
    except PDFExtractionError:
        raise
    except Exception as e:
        raise PDFExtractionError(f"Failed to parse PDF: {e}") from e

    if not text.strip():
        raise PDFExtractionError(
            "PDF contained no extractable text (likely scanned images)"
        )
    return text
