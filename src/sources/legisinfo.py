"""LEGISinfo (Parliament of Canada) structured policy source.

Fetches the full current-session bill list from parl.ca/legisinfo and
filters client-side for bills touching heat, energy efficiency, or data
centre energy — the list endpoint carries no server-side search, and no
document text, so content is built from the title and stage fields it
does provide; the pipeline's screening stage handles the rest.
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

DEFAULT_TERMS = ["heat", "energy efficiency", "data centre", "district energy"]
DEFAULT_MAX_DOCUMENTS = 25
LIST_URL = "https://www.parl.ca/legisinfo/en/bills/json"
FALLBACK_URL = "https://www.parl.ca/legisinfo/en/bills"


def _lifecycle_from_stage(stage_name: str) -> str:
    stage = stage_name or ""
    if "Royal Assent" in stage:
        return "enacted"
    if "Committee" in stage:
        return "in_committee"
    return "proposed"


def _bill_url(bill: dict) -> str:
    parliament = bill.get("ParliamentNumber") or bill.get("parliamentNumber")
    session = bill.get("SessionNumber") or bill.get("session")
    number = (
        bill.get("NumberCode")
        or bill.get("BillNumberFormatted")
        or bill.get("number")
    )
    if not (parliament and session and number):
        return FALLBACK_URL
    return f"https://www.parl.ca/legisinfo/en/bill/{parliament}-{session}/{str(number).lower()}"


@register_source
class LegisInfoSource(PolicySource):
    """Fetches Canadian federal bills from parl.ca/legisinfo."""

    id = "legisinfo"

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = [t.lower() for t in (params.get("terms") or DEFAULT_TERMS)]
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)

        async with build_client() as client:
            bills = await self._list_bills(client)

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()
        for bill in bills:
            if len(results) >= max_documents:
                break
            result = self._to_crawl_result(bill, terms, seen_urls)
            if result:
                results.append(result)
        return results

    async def _list_bills(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(LIST_URL)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("LEGISinfo bill list fetch failed: %s", e)
            return []
        return data if isinstance(data, list) else []

    def _to_crawl_result(
        self, bill: dict, terms: list[str], seen_urls: set[str]
    ) -> CrawlResult | None:
        if not isinstance(bill, dict):
            return None
        # Live payload uses language-suffixed fields (LongTitleEn);
        # keep the unsuffixed names as fallbacks.
        long_title = bill.get("LongTitleEn") or bill.get("LongTitle") or ""
        short_title = bill.get("ShortTitleEn") or bill.get("ShortTitle") or ""
        haystack = f"{long_title} {short_title}".lower()
        if not any(term in haystack for term in terms):
            return None

        url = _bill_url(bill)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        stage_name = (
            bill.get("CurrentStatusEn")
            or bill.get("LatestCompletedMajorStageName")
            or bill.get("latestCompletedMajorStageName")
            or ""
        )
        lifecycle_stage = _lifecycle_from_stage(stage_name)
        content = f"{long_title or short_title}\n\nStage: {stage_name}".strip()
        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=short_title or long_title,
            lifecycle_stage=lifecycle_stage,
        )
