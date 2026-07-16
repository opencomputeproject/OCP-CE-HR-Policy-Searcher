"""GovInfo structured policy source — US federal bill full text (GPO).

Searches the govinfo.gov Search API's BILLS collection and cites the
official govinfo.gov package detail page for each hit. Disabled entirely
(returns []) until GOVINFO_API_KEY is set.
"""

import logging
import os

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import TIMEOUT_SECONDS, USER_AGENT
from .base import PolicySource

logger = logging.getLogger(__name__)

API_KEY_ENV = "GOVINFO_API_KEY"
SEARCH_URL = "https://api.govinfo.gov/search"
DETAILS_URL = "https://www.govinfo.gov/app/details/{package_id}"
DEFAULT_TERMS = ['"waste heat"', '"district heating"', '"data center" energy']
DEFAULT_MAX_DOCUMENTS = 25
PAGE_SIZE = 25


@register_source
class GovinfoSource(PolicySource):
    """Fetches US federal bill text from api.govinfo.gov's BILLS collection."""

    id = "govinfo"
    api_key_env = API_KEY_ENV

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            logger.info("source disabled: %s not set", API_KEY_ENV)
            return []

        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "X-Api-Key": api_key},
        ) as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                for item in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = self._to_crawl_result(item, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        body = {
            "query": f"collection:BILLS AND ({term})",
            "pageSize": PAGE_SIZE,
            "offsetMark": "*",
            "sorts": [{"field": "publishdate", "sortOrder": "DESC"}],
        }
        try:
            resp = await client.post(SEARCH_URL, json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("GovInfo search failed for term %r: %s", term, e)
            return []

        items = data.get("results") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    def _to_crawl_result(self, item: dict, seen_urls: set[str]) -> CrawlResult | None:
        if not isinstance(item, dict):
            return None
        package_id = item.get("packageId")
        if not package_id:
            return None
        url = DETAILS_URL.format(package_id=package_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        title = item.get("title", "")
        date_issued = item.get("dateIssued", "")
        summary = item.get("summary", "")
        content = " ".join(part for part in (title, date_issued, summary) if part)
        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            title=title,
            lifecycle_stage="proposed",
        )
