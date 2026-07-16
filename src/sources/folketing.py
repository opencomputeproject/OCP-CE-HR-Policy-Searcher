"""Folketing (Danish Parliament) structured policy source.

Queries the Folketing's OData API (oda.ft.dk) for parliamentary cases
(Sag) whose title matches waste-heat or district-heating terms. The
list endpoint carries a summary (resume) but no full document text, so
content is built from the title and summary.
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

DEFAULT_TERMS = ["overskudsvarme", "fjernvarme", "varmeforsyning", "datacenter"]
DEFAULT_MAX_DOCUMENTS = 25
SAG_URL = "https://oda.ft.dk/api/Sag"
CASE_PAGE_URL = "https://www.ft.dk/samling/oversigt/sag.htm?sagId={sag_id}"


@register_source
class FolketingSource(PolicySource):
    """Fetches Danish parliamentary cases from oda.ft.dk."""

    id = "folketing"

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
                for case in await self._search(client, term, max_documents):
                    if len(results) >= max_documents:
                        break
                    result = self._to_crawl_result(case, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _search(
        self, client: httpx.AsyncClient, term: str, top: int
    ) -> list[dict]:
        filter_expr = f"substringof('{term}',titel)"
        try:
            resp = await client.get(
                SAG_URL,
                params={
                    "$filter": filter_expr,
                    "$orderby": "opdateringsdato desc",
                    "$top": top,
                    "$format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Folketing search failed for term %r: %s", term, e)
            return []

        value = data.get("value") if isinstance(data, dict) else None
        return value if isinstance(value, list) else []

    def _to_crawl_result(self, case: dict, seen_urls: set[str]) -> CrawlResult | None:
        if not isinstance(case, dict):
            return None
        sag_id = case.get("id")
        if sag_id is None:
            return None
        url = CASE_PAGE_URL.format(sag_id=sag_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        titel = case.get("titel") or ""
        resume = case.get("resume") or ""
        content = f"{titel}\n\n{resume}".strip()
        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=titel,
            lifecycle_stage="proposed",
        )
