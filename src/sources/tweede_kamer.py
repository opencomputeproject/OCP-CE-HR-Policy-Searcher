"""Netherlands Tweede Kamer structured policy source.

The Dutch parliament publishes an OData v4 service (gegevensmagazijn) with
SERVER-SIDE keyword search — the only keyless source probed that can filter
by subject upstream, so unlike the Oireachtas client this one does not have
to page the whole corpus and match locally.

Citation note: the tweedekamer.nl website addresses its pages by an internal
id we cannot derive from this API (every guessed pattern 404s). The service's
own `Document({id})/resource` endpoint serves the official PDF from the
parliament's own domain, so that is the citation of record here — the
primary document, not an aggregator's copy of it.

License: CC0 per opendata.tweedekamer.nl.
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

ODATA_BASE = "https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0"
ZAAK_URL = f"{ODATA_BASE}/Zaak"
DOCUMENT_RESOURCE_URL = f"{ODATA_BASE}/Document({{document_id}})/resource"

# Dutch corpus: English terms match nothing.
DEFAULT_TERMS = ["restwarmte", "warmtenet", "datacenter", "warmtewet"]

# Things that change the law. "Schriftelijke vragen" (written questions) and
# "Brief regering" (government letters) dominate the raw results but are
# commentary, not policy — including them by default would flood the library.
DEFAULT_SOORTEN = ["Wetgeving", "Motie", "Amendement", "Initiatiefnota"]

DEFAULT_MAX_DOCUMENTS = 25
PAGE_SIZE = 50
MIN_CONTENT_LENGTH = 200


def _escape(term: str) -> str:
    """OData string literals escape a single quote by doubling it."""
    return term.replace("'", "''")


@register_source
class TweedeKamerSource(PolicySource):
    """Fetches Dutch parliamentary cases from the gegevensmagazijn OData API."""

    id = "tweede_kamer"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        soorten = params.get("soorten") or DEFAULT_SOORTEN

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()

        async with build_client() as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                for zaak in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    if (zaak.get("Soort") or "") not in soorten:
                        continue
                    result = await self._to_crawl_result(client, zaak, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(
                ZAAK_URL,
                params={
                    "$filter": f"contains(Onderwerp,'{_escape(term)}')",
                    "$expand": "Document",
                    "$orderby": "GestartOp desc",
                    "$top": PAGE_SIZE,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Tweede Kamer search failed for %r: %s", term, e)
            return []

        value = data.get("value") if isinstance(data, dict) else None
        return value if isinstance(value, list) else []

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, zaak: dict, seen_urls: set[str]
    ) -> CrawlResult | None:
        documents = zaak.get("Document") or []
        if not isinstance(documents, list) or not documents:
            return None
        document = documents[0]
        if not isinstance(document, dict):
            return None
        document_id = document.get("Id")
        if not document_id:
            return None

        url = DOCUMENT_RESOURCE_URL.format(document_id=document_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        onderwerp = zaak.get("Onderwerp") or ""
        titel = zaak.get("Titel") or ""
        soort = zaak.get("Soort") or ""
        nummer = zaak.get("Nummer") or ""

        content, content_type = await fetch_document_text(client, url)
        if len(content) < MIN_CONTENT_LENGTH:
            fallback = "\n\n".join(p for p in (
                onderwerp, titel, f"Soort: {soort}. Nummer: {nummer}.",
            ) if p.strip())
            if len(fallback) > len(content):
                content, content_type = fallback, "text/plain"

        if not content:
            return None

        # `Afgedaan` means the case is closed, NOT that it became law — a
        # motion can be closed by rejection. Since a source-declared stage
        # overrides the analysis model, only claim a stage we actually know.
        lifecycle_stage = None if zaak.get("Afgedaan") else "proposed"

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type=content_type,
            title=onderwerp[:200] or titel[:200],
            lifecycle_stage=lifecycle_stage,
        )
