"""Ireland Oireachtas structured policy source.

Queries api.oireachtas.ie for bills and fetches the official bill page on
oireachtas.ie for full text. Ireland is a top EU data-centre market, so
its heat and energy legislation matters disproportionately here.

Unlike LegiScan or the UK Bills API, the Oireachtas API has NO full-text
search: it filters only by status and date. So this source pages through
bills by status and matches terms against the titles locally. That is
cheap (a few hundred bills) but means a bill whose title never says
"heat" is invisible to us — an accepted limit of the upstream API.
"""

import logging
import re

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

# Deliberately BROAD single words, not our domain phrases.
#
# Measured against all 1024 Current+Enacted bills (2026-07-17): "waste heat"
# matched 0, "data centre" matched 0, "heat" matched 2 — but "energy" matched
# 24, including "Prevention of Energy Wastage Bill 2026" and "Energy Poverty
# Reduction (Use of Surplus Renewable Energy) Bill 2025". Both are squarely
# on-topic and contain none of our usual phrases. Since this API has no
# full-text search we only ever see titles, so the source casts wide and the
# keyword + screening gates downstream do the precision work.
# Irish English: "centre", never "center".
DEFAULT_TERMS = [
    "heat",
    "energy",
    "thermal",
    "cooling",
    "data centre",
]
DEFAULT_MAX_DOCUMENTS = 25
DEFAULT_STATUSES = ["Current", "Enacted"]
# The API caps page size; 250 keeps the whole Current set to ~2 requests.
PAGE_SIZE = 250
MAX_PAGES = 4
MIN_CONTENT_LENGTH = 200

SEARCH_URL = "https://api.oireachtas.ie/v1/legislation"
BILL_PAGE_URL = "https://www.oireachtas.ie/en/bills/bill/{year}/{number}/"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str) -> str:
    """longTitleEn arrives wrapped in <p> tags; keep the words only."""
    return _TAG_RE.sub(" ", value or "").strip()


def _lifecycle_from(status: str, stage: str) -> str:
    if (status or "").lower() == "enacted":
        return "enacted"
    if "committee" in (stage or "").lower():
        return "in_committee"
    return "proposed"


@register_source
class OireachtasSource(PolicySource):
    """Fetches Irish bills from api.oireachtas.ie."""

    id = "oireachtas"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = [t.lower() for t in (params.get("terms") or DEFAULT_TERMS)]
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        statuses = params.get("bill_statuses") or DEFAULT_STATUSES

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()

        async with build_client() as client:
            for status in statuses:
                if len(results) >= max_documents:
                    break
                for bill in await self._list_bills(client, status):
                    if len(results) >= max_documents:
                        break
                    if not self._matches(bill, terms):
                        continue
                    result = await self._to_crawl_result(client, bill, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _list_bills(self, client: httpx.AsyncClient, status: str) -> list[dict]:
        """Page through bills of one status. Never raises."""
        bills: list[dict] = []
        for page in range(MAX_PAGES):
            try:
                resp = await client.get(
                    SEARCH_URL,
                    params={
                        "bill_status": status,
                        "limit": PAGE_SIZE,
                        "skip": page * PAGE_SIZE,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("Oireachtas list failed (status=%s): %s", status, e)
                return bills

            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list) or not results:
                return bills

            for entry in results:
                bill = entry.get("bill") if isinstance(entry, dict) else None
                if isinstance(bill, dict):
                    bills.append(bill)

            if len(results) < PAGE_SIZE:
                return bills
        return bills

    @staticmethod
    def _matches(bill: dict, terms: list[str]) -> bool:
        haystack = " ".join([
            bill.get("shortTitleEn") or "",
            _strip_html(bill.get("longTitleEn") or ""),
        ]).lower()
        return any(term in haystack for term in terms)

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, bill: dict, seen_urls: set[str]
    ) -> CrawlResult | None:
        number, year = bill.get("billNo"), bill.get("billYear")
        if not number or not year:
            return None

        url = BILL_PAGE_URL.format(year=year, number=number)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        short_title = bill.get("shortTitleEn") or ""
        long_title = _strip_html(bill.get("longTitleEn") or "")
        stage = ((bill.get("mostRecentStage") or {}).get("event") or {}).get("showAs") or ""
        status = bill.get("status") or ""

        content, content_type = await fetch_document_text(client, url)
        if len(content) < MIN_CONTENT_LENGTH:
            fallback = "\n\n".join(p for p in (
                short_title, long_title, f"Status: {status}. Stage: {stage}."
            ) if p.strip())
            if len(fallback) > len(content):
                content, content_type = fallback, "text/plain"

        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type=content_type,
            title=short_title or long_title[:120],
            lifecycle_stage=_lifecycle_from(status, stage),
        )
