"""DIP (Bundestag) structured policy source — German federal legislation.

Searches the Bundestag's Dokumentations- und Informationssystem (DIP) for
"Vorgänge" (legislative proceedings) and cites the underlying document PDF
when one is found, falling back to the official dip.bundestag.de detail
page. Disabled entirely (returns []) until DIP_API_KEY is set.

Document-type allow-list (added 2026-09-02, WP-3): the reviewer removed 18
of the tool's DIP rows as "not a policy", all of them parliamentary
questions. DIP's own `vorgangstyp` field already says this, so a vorgang
whose type is not in DEFAULT_DOCUMENT_TYPES is dropped before any page is
fetched or any model is called, and counted in `dropped_doc_type`. Recorded
live 2026-09-02 against `f.titel=Abwärme`/`f.titel=Rechenzentrum`:
vorgangstyp values seen were `Fragestunde` (25), `Schriftliche Frage` (11),
`Kleine Anfrage` (2), all excluded by default. DIP's legislative vocabulary
also includes `Gesetzgebung`, `Rechtsverordnung`, `Verordnung`, `Antrag`,
`Entschließungsantrag`, `Unterrichtung`; only the first four are kept by
default (`Entschließungsantrag`/`Unterrichtung` were not seen live and are
left for an explicit `document_types` override).

Document URL (same date): the case-overview page alone was flagged by the
reviewer as "link is for a general website". For each kept vorgang, one
extra call to `.../api/v1/vorgangsposition?f.vorgang=<id>` fetches the
linked document; its first item's `fundstelle.pdf_url` becomes the citation
URL when present (recorded live: `fundstelle.pdf_url` such as
`https://dserver.bundestag.de/btd/20/115/2011501.pdf`). The vorgang detail
page is always kept as referenced context in the content text, and is the
fallback URL when no pdf_url exists.
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
VORGANGSPOSITION_URL = "https://search.dip.bundestag.de/api/v1/vorgangsposition"
DETAIL_URL = "https://dip.bundestag.de/vorgang/{vorgang_id}"
DEFAULT_TERMS = ["Abwärme", "Wärmeplanung", "Energieeffizienzgesetz", "Rechenzentren"]
DEFAULT_MAX_DOCUMENTS = 25
# DIP's own vorgangstyp vocabulary for law-changing proceedings. Excludes
# parliamentary questions (Kleine Anfrage, Schriftliche Frage, Fragestunde);
# see module docstring.
DEFAULT_DOCUMENT_TYPES = ["Gesetzgebung", "Rechtsverordnung", "Verordnung", "Antrag"]


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
        self.dropped_doc_type = 0
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            logger.info("source disabled: %s not set", API_KEY_ENV)
            return []

        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        document_types = params.get("document_types") or DEFAULT_DOCUMENT_TYPES

        results: list[CrawlResult] = []
        seen_vorgang_ids: set[str] = set()
        seen_urls: set[str] = set()

        async with httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Authorization": f"ApiKey {api_key}"},
        ) as client:
            for term in terms:
                # max_documents counts KEPT vorgänge only: len(results)
                # only grows on a kept item, so a run of dropped questions
                # never exhausts the cap.
                if len(results) >= max_documents:
                    break
                for item in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(
                        client, item, seen_vorgang_ids, seen_urls, document_types,
                    )
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

    async def _document_pdf_url(self, client: httpx.AsyncClient, vorgang_id: str) -> str:
        """The linked document's official PDF, or "" when none is found.

        One extra call per kept vorgang to `.../vorgangsposition`; never
        raises. Any failure just falls back to the vorgang detail page.
        """
        try:
            resp = await client.get(VORGANGSPOSITION_URL, params={"f.vorgang": vorgang_id})
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("DIP vorgangsposition fetch failed for %s: %s", vorgang_id, e)
            return ""

        items = data.get("documents") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            return ""
        first = items[0]
        if not isinstance(first, dict):
            return ""
        fundstelle = first.get("fundstelle")
        if not isinstance(fundstelle, dict):
            return ""
        pdf_url = fundstelle.get("pdf_url")
        return pdf_url if isinstance(pdf_url, str) else ""

    async def _to_crawl_result(
        self,
        client: httpx.AsyncClient,
        item: dict,
        seen_vorgang_ids: set[str],
        seen_urls: set[str],
        document_types: list[str],
    ) -> CrawlResult | None:
        if not isinstance(item, dict):
            return None
        vorgang_id = item.get("id")
        if not vorgang_id or vorgang_id in seen_vorgang_ids:
            return None
        seen_vorgang_ids.add(vorgang_id)

        titel = item.get("titel") or ""
        vorgangstyp = item.get("vorgangstyp") or ""
        if vorgangstyp not in document_types:
            self.dropped_doc_type += 1
            logger.debug(
                "DIP dropped by document-type allow-list: type=%r title=%r",
                vorgangstyp, titel,
            )
            return None

        beratungsstand = item.get("beratungsstand") or ""
        detail_url = DETAIL_URL.format(vorgang_id=vorgang_id)
        pdf_url = await self._document_pdf_url(client, vorgang_id)
        url = pdf_url or detail_url
        if url in seen_urls:
            return None
        seen_urls.add(url)

        body = " ".join(part for part in (titel, vorgangstyp, beratungsstand) if part)
        # The vorgang page is kept as referenced context even when the PDF
        # is the citation URL: "link is for a general website" was the
        # reviewer's complaint about the overview page being the ONLY link,
        # not about it being mentioned at all.
        content = f"{body}\nVorgang: {detail_url}".strip()

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            title=titel,
            lifecycle_stage=_lifecycle_from_beratungsstand(beratungsstand),
        )
