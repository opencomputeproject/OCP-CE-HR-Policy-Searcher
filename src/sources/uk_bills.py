"""UK Parliament Bills structured policy source.

Queries the Bills API (bills-api.parliament.uk) for bills related to
heat networks, waste heat, and data centre energy, then fetches the
official bill page on bills.parliament.uk for its full text.
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

# The Bills API SearchTerm matches phrases strictly, so multi-word phrases
# like "heat networks" return nothing. Include the broad single word "heat"
# (surfaces heating/heat-network bills) alongside the specific phrases.
DEFAULT_TERMS = ["heat", "waste heat", "district heating", "data centre energy"]
DEFAULT_MAX_DOCUMENTS = 25
MIN_CONTENT_LENGTH = 200
SEARCH_URL = "https://bills-api.parliament.uk/api/v1/Bills"
BILL_PAGE_URL = "https://bills.parliament.uk/bills/{bill_id}"


def _lifecycle_from_stage(stage_description: str) -> str:
    stage = stage_description or ""
    if "Royal Assent" in stage:
        return "enacted"
    if "Committee" in stage:
        return "in_committee"
    return "proposed"


@register_source
class UKBillsSource(PolicySource):
    """Fetches UK parliamentary bills from bills-api.parliament.uk."""

    id = "uk_bills"

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()

        async with build_client() as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                for item in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(client, item, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(
                SEARCH_URL,
                params={"SearchTerm": term, "SortOrder": "DateUpdatedDescending"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("UK Bills search failed for term %r: %s", term, e)
            return []

        items = data.get("items") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, item: dict, seen_urls: set[str]
    ) -> CrawlResult | None:
        if not isinstance(item, dict):
            return None
        bill_id = item.get("billId")
        if bill_id is None:
            return None
        url = BILL_PAGE_URL.format(bill_id=bill_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        short_title = item.get("shortTitle") or ""
        current_stage = item.get("currentStage") or {}
        stage_description = current_stage.get("description") or ""
        lifecycle_stage = _lifecycle_from_stage(stage_description)

        content, content_type = await fetch_document_text(client, url)
        if len(content) < MIN_CONTENT_LENGTH:
            fallback = f"{short_title}\n\nCurrent stage: {stage_description}".strip()
            if len(fallback) > len(content):
                content, content_type = fallback, "text/plain"

        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type=content_type,
            title=short_title,
            lifecycle_stage=lifecycle_stage,
        )
