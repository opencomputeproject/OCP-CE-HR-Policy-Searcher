"""Austria RIS (Rechtsinformationssystem) OGD Bundesrecht structured source.

RIS is Austria's official legal information system; the OGD (Open
Government Data) v2.6 API exposes `Bundesrecht` — enacted federal law plus
the Bundesgesetzblatt (official gazette) — with a genuine server-side
full-text filter over `Suchworte=`. No auth required.

Verified live 2026-07-24 (see 20260724_Source_API_Research_Wave3.md):
  Suchworte=zzznonsensexyz123qqq -> 0 hits (filter confirmed genuine,
  not the Retsinformation/Diavgeia silent no-op trap).
  Suchworte=Fernwärme -> 103, Abwärme -> 28, Rechenzentrum -> 8,
  Energieeffizienz -> 150. Baseline (no filter) -> 18,821.

Scope note: Bundesrecht is enacted law, so earliness is at promulgation,
not at bill introduction — complements (does not replace) Austria's
Parlament Filter API, which tracks bills at introduction and remains
unbuilt. lifecycle_stage is always "enacted" for this source.

License: CC BY 4.0 (data.bka.gv.at open data terms).
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"

# Measured live 2026-07-24 against the real Bundesrecht corpus (18,821 docs
# baseline): all four terms return real, nonzero, on-topic hits.
DEFAULT_TERMS = ["Fernwärme", "Abwärme", "Rechenzentrum", "Energieeffizienz"]
DEFAULT_MAX_DOCUMENTS = 25


@register_source
class RisAustriaSource(PolicySource):
    """Fetches Austrian enacted federal law from the RIS OGD Bundesrecht API."""

    id = "ris_austria"
    api_key_env = None

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
                for reference in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(client, reference, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(SEARCH_URL, params={"Suchworte": term})
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("RIS Austria search failed for term %r: %s", term, e)
            return []

        try:
            document_results = data["OgdSearchResult"]["OgdDocumentResults"]
        except (KeyError, TypeError) as e:
            logger.warning("RIS Austria response missing expected structure: %s", e)
            return []

        if not isinstance(document_results, dict):
            return []

        references = document_results.get("OgdDocumentReference")
        if isinstance(references, dict):
            references = [references]
        if not isinstance(references, list):
            return []
        return [r for r in references if isinstance(r, dict)]

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, reference: dict, seen_urls: set[str]
    ) -> CrawlResult | None:
        try:
            metadaten = reference["Data"]["Metadaten"]
        except (KeyError, TypeError):
            return None
        if not isinstance(metadaten, dict):
            return None

        allgemein = metadaten.get("Allgemein") or {}
        bundesrecht = metadaten.get("Bundesrecht") or {}
        if not isinstance(allgemein, dict) or not isinstance(bundesrecht, dict):
            return None

        url = allgemein.get("DokumentUrl")
        if not url or not isinstance(url, str):
            return None
        if url in seen_urls:
            return None
        seen_urls.add(url)

        title = (bundesrecht.get("Kurztitel") or bundesrecht.get("Titel") or "").strip()

        bgbl = bundesrecht.get("BgblAuth") or {}
        meta = []
        if isinstance(bgbl, dict):
            ausgabedatum = bgbl.get("Ausgabedatum")
            if ausgabedatum:
                meta.append(f"Ausgabedatum: {ausgabedatum}.")
            bgblnummer = bgbl.get("Bgblnummer")
            if bgblnummer:
                meta.append(f"BGBl. Nr.: {bgblnummer}.")
        eli = bundesrecht.get("Eli")
        if eli:
            meta.append(f"ELI: {eli}.")

        document_text, _ = await fetch_document_text(client, url)

        content = "\n\n".join(p for p in (
            title,
            " ".join(meta),
            document_text,
        ) if p and p.strip())
        if not content:
            return None

        # Bundesrecht is enacted federal law (post-promulgation) — every
        # document from this source claims "enacted".
        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/html",
            title=title or None,
            lifecycle_stage="enacted",
        )
