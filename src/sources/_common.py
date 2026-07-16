"""Shared HTTP client and document-text extraction for structured sources.

Every structured source fetches its result list from a JSON/XML/OData API
and then, where the API doesn't already carry full text, needs to pull the
underlying HTML or PDF document. This module centralizes that plumbing so
each client file stays focused on its own API shape.
"""

import logging

import httpx
from bs4 import BeautifulSoup

from ..core.pdf import PDFExtractionError, extract_pdf_text, looks_like_pdf

logger = logging.getLogger(__name__)

USER_AGENT = "OCP-PolicyPulse/1.0"
TIMEOUT_SECONDS = 30.0


def build_client() -> httpx.AsyncClient:
    """Create a per-fetch httpx client with the shared timeout/headers."""
    return httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


async def fetch_document_text(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """Fetch a document and extract its plain text.

    Handles both HTML (crude tag stripping via BeautifulSoup) and PDF
    (via src.core.pdf) documents. Never raises: any failure yields
    ("", "") so callers can fall back to metadata-only content.
    """
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch document %s: %s", url, e)
        return "", ""

    content_type_header = resp.headers.get("content-type", "")
    if looks_like_pdf(url, content_type_header):
        try:
            text = extract_pdf_text(resp.content)
        except PDFExtractionError as e:
            logger.warning("Failed to extract PDF text from %s: %s", url, e)
            return "", ""
        return text, "application/pdf"

    try:
        soup = BeautifulSoup(resp.text, "lxml")
        text = soup.get_text(separator=" ", strip=True)
    except Exception as e:
        logger.warning("Failed to parse HTML from %s: %s", url, e)
        return "", ""
    return text, "text/html"
