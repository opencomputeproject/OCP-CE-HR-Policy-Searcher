"""South Africa PMG (Parliamentary Monitoring Group) structured policy source.

Two feeds from one API, both newest-first with per_page capped at 50:
- /call-for-comment/ — open comment windows, the class of early signal
  this project prizes (the same class missed on the EUR 1B clean heat
  auction). An OPEN window maps to lifecycle "consultation" with the
  deadline folded into the content; a closed one claims nothing.
- /bill/ — bills from draft to assent. Assent date -> "enacted".

Honesty note on citations: South Africa's Parliament has no open API, and
PMG — a 30-year-old parliamentary monitoring NGO whose record parliament
itself references — is the de facto structured record. Its pages carry the
official bill PDFs. This is the one source where the citation URL is not a
government domain; the config note says so out loud.

Matching is client-side (no server-side search) against title AND body:
CFC titles are terse ("Gas Bill") while the body carries the substance.

License: PMG content is CC BY (attribution) per pmg.org.za terms.
"""

import logging
from datetime import date

import httpx
from bs4 import BeautifulSoup

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

API_BASE = "https://api.pmg.org.za"
CFC_URL = f"{API_BASE}/call-for-comment/"
BILL_URL = f"{API_BASE}/bill/"
PUBLIC_CFC_URL = "https://pmg.org.za/call-for-comment/{id}/"
PUBLIC_BILL_URL = "https://pmg.org.za/bill/{id}/"

# English titles; broad single words per the recurring lesson (Ireland,
# Norway, Estonia, Poland): specific domain phrases match nothing in
# terse legislative titles.
DEFAULT_TERMS = ["energy", "heat", "electricity", "gas", "climate", "data centre"]
DEFAULT_MAX_DOCUMENTS = 25
DEFAULT_MAX_PAGES = 3
PER_PAGE = 50  # server-side maximum


def _strip_html(html: str) -> str:
    if not html:
        return ""
    try:
        return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("PMG body parse failed: %s", e)
        return ""


def _is_open_window(end_date) -> bool:
    """True only when the comment deadline is verifiably in the future."""
    if not isinstance(end_date, str):
        return False
    try:
        return date.fromisoformat(end_date[:10]) >= date.today()
    except ValueError:
        return False


@register_source
class PMGSource(PolicySource):
    """Fetches SA bills and comment windows from the PMG API."""

    id = "pmg"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = [t.lower() for t in (params.get("terms") or DEFAULT_TERMS)]
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        max_pages = params.get("max_pages", DEFAULT_MAX_PAGES)

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()

        async with build_client() as client:
            # Comment windows first: they are the early signal, and the
            # shared cap should spend itself there before historic bills.
            for cfc in await self._pages(client, CFC_URL, max_pages):
                if len(results) >= max_documents:
                    break
                result = self._cfc_result(cfc, terms, seen_urls)
                if result:
                    results.append(result)

            for bill in await self._pages(client, BILL_URL, max_pages):
                if len(results) >= max_documents:
                    break
                result = self._bill_result(bill, terms, seen_urls)
                if result:
                    results.append(result)

        return results

    async def _pages(
        self, client: httpx.AsyncClient, url: str, max_pages: int
    ) -> list[dict]:
        items: list[dict] = []
        next_url: str | None = f"{url}?per_page={PER_PAGE}"
        pages = 0
        while next_url and pages < max_pages:
            try:
                resp = await client.get(next_url)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("PMG page fetch failed (%s): %s", next_url, e)
                break
            if not isinstance(data, dict):
                break
            batch = data.get("results")
            if isinstance(batch, list):
                items.extend(i for i in batch if isinstance(i, dict))
            next_url = data.get("next")
            pages += 1
        return items

    @staticmethod
    def _matches(terms: list[str], *haystacks: str) -> bool:
        text = " ".join(h for h in haystacks if h).lower()
        return any(term in text for term in terms)

    def _cfc_result(
        self, cfc: dict, terms: list[str], seen_urls: set[str]
    ) -> CrawlResult | None:
        cfc_id = cfc.get("id")
        if cfc_id is None:
            return None

        title = cfc.get("title") or ""
        body = _strip_html(cfc.get("body") or "")
        if not self._matches(terms, title, body):
            return None

        url = PUBLIC_CFC_URL.format(id=cfc_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        # The deadline is the reason an open window matters; put it where
        # the analysis model will read it (same pattern as gov.uk).
        window_parts = []
        if cfc.get("start_date"):
            window_parts.append(f"Comments open: {cfc['start_date']}")
        if cfc.get("end_date"):
            window_parts.append(f"Comments close: {cfc['end_date']}")
        window = ". ".join(window_parts)

        content = "\n\n".join(p for p in (
            f"Call for comment: {title}" if title else "",
            window,
            body,
        ) if p and p.strip())
        if not content:
            return None

        # Open window -> consultation. Closed or undated -> the bill
        # behind it may be anywhere in the pipeline; claim nothing.
        stage = "consultation" if _is_open_window(cfc.get("end_date")) else None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage=stage,
        )

    def _bill_result(
        self, bill: dict, terms: list[str], seen_urls: set[str]
    ) -> CrawlResult | None:
        bill_id = bill.get("id")
        if bill_id is None:
            return None

        title = bill.get("title") or ""
        if not self._matches(terms, title):
            return None

        url = PUBLIC_BILL_URL.format(id=bill_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        meta = []
        if bill.get("year"):
            meta.append(f"Year: {bill['year']}.")
        bill_type = (bill.get("type") or {}).get("name")
        if bill_type:
            meta.append(f"Type: {bill_type}.")
        if bill.get("date_of_introduction"):
            meta.append(f"Introduced: {bill['date_of_introduction']}.")
        if bill.get("date_of_assent"):
            meta.append(f"Assented: {bill['date_of_assent']}.")
        if bill.get("introduced_by"):
            meta.append(f"Introduced by: {bill['introduced_by']}.")

        content = "\n\n".join(p for p in (title, " ".join(meta)) if p and p.strip())
        if not content:
            return None

        stage = "enacted" if bill.get("date_of_assent") else "proposed"

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage=stage,
        )
