"""Riksdagen (Swedish Parliament) structured policy source.

Queries data.riksdagen.se's open document-list API for Swedish
legislative documents (motions, propositions, committee reports, SFS
statutes) touching waste-heat reuse, then fetches each document's full
text so the pipeline can screen it like any crawled page.
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

DEFAULT_TERMS = [
    "spillvärme", "fjärrvärme", "datacenter energi", "energieffektivisering värme",
]
DEFAULT_MAX_DOCUMENTS = 25
LIST_URL = "https://data.riksdagen.se/dokumentlista/"

_DOKTYP_STAGE = {
    "mot": "proposed",
    "prop": "proposed",
    "sfs": "enacted",
    "bet": "in_committee",
}


@register_source
class RiksdagenSource(PolicySource):
    """Fetches Swedish parliamentary documents from data.riksdagen.se."""

    id = "riksdagen"

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
                for doc in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(client, doc, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(
                LIST_URL,
                params={
                    "sok": term,
                    "utformat": "json",
                    "sort": "datum",
                    "sortorder": "desc",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Riksdagen search failed for term %r: %s", term, e)
            return []

        try:
            documents = data["dokumentlista"]["dokument"]
        except (KeyError, TypeError) as e:
            logger.warning("Riksdagen response missing expected structure: %s", e)
            return []

        if isinstance(documents, dict):
            documents = [documents]
        return documents if isinstance(documents, list) else []

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, doc: dict, seen_urls: set[str]
    ) -> CrawlResult | None:
        if not isinstance(doc, dict):
            return None
        url = doc.get("dokument_url_html") or doc.get("dokument_url_text")
        if not url:
            return None
        if url.startswith("//"):
            url = "https:" + url
        if url in seen_urls:
            return None
        seen_urls.add(url)

        content, content_type = await fetch_document_text(client, url)
        if not content:
            return None

        doktyp = (doc.get("doktyp") or "").lower()
        lifecycle_stage = _DOKTYP_STAGE.get(doktyp, "unknown")

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type=content_type,
            title=doc.get("titel"),
            lifecycle_stage=lifecycle_stage,
        )
