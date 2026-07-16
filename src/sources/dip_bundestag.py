"""DIP (Bundestag) structured policy source — German federal legislation.

Searches the Bundestag's Dokumentations- und Informationssystem (DIP) for
"Vorgänge" (legislative proceedings) and cites the official
dip.bundestag.de detail page. Disabled entirely (returns []) until
DIP_API_KEY is set.
"""

import logging
import os

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import TIMEOUT_SECONDS, USER_AGENT
from .base import PolicySource

logger = logging.getLogger(__name__)

API_KEY_ENV = "DIP_API_KEY"
VORGANG_URL = "https://search.dip.bundestag.de/api/v1/vorgang"
DETAIL_URL = "https://dip.bundestag.de/vorgang/{vorgang_id}"
DEFAULT_TERMS = ["Abwärme", "Wärmeplanung", "Energieeffizienzgesetz", "Rechenzentren"]
DEFAULT_MAX_DOCUMENTS = 25


def _lifecycle_from_beratungsstand(beratungsstand: str) -> str:
    text = (beratungsstand or "").lower()
    if "verkündet" in text or "abgeschlossen" in text:
        return "enacted"
    if "ausschuss" in text:
        return "in_committee"
    return "proposed"


@register_source
class DipBundestagSource(PolicySource):
    """Fetches German federal legislative proceedings from search.dip.bundestag.de."""

    id = "dip"
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
            headers={"User-Agent": USER_AGENT, "Authorization": f"ApiKey {api_key}"},
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
        try:
            resp = await client.get(
                VORGANG_URL, params={"f.titel": term, "sort": "datum desc"}
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("DIP search failed for term %r: %s", term, e)
            return []

        items = data.get("documents") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    def _to_crawl_result(self, item: dict, seen_urls: set[str]) -> CrawlResult | None:
        if not isinstance(item, dict):
            return None
        vorgang_id = item.get("id")
        if not vorgang_id:
            return None
        url = DETAIL_URL.format(vorgang_id=vorgang_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        titel = item.get("titel") or ""
        vorgangstyp = item.get("vorgangstyp") or ""
        beratungsstand = item.get("beratungsstand") or ""
        content = " ".join(part for part in (titel, vorgangstyp, beratungsstand) if part)
        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            title=titel,
            lifecycle_stage=_lifecycle_from_beratungsstand(beratungsstand),
        )
