"""Poland Sejm structured policy source.

The Sejm API has no keyword search. /prints returns the term's complete
print list (~3100 prints for term 10) in ONE request — `limit` is honoured
on /processes but the full prints list is small enough (1.7 MB) that one
fetch and a local title match is simpler and cheaper than paging.

Two Polish-specific lessons, both measured live 2026-07-17:
- Polish declension means STEMS, not words: "ciepł" matched 19 print
  titles (ciepło, cieplna, ciepłownictwo...), "energ" 97, "klimat" 64,
  while the full phrase "centrum danych" matched 0 (titles would say
  "centrów danych" anyway). Same lesson as Ireland/Norway/Estonia.
- The prints list arrives oldest-first. With a document cap in play the
  client must walk it newest-first, or the cap spends itself on 2023
  leftovers before reaching this year's bills.

The citation URL is the print's official PDF on api.sejm.gov.pl (the
Sejm's own domain); the process detail (same number) supplies the
lifecycle stage. `passed` is only trusted when the process is closed —
a closed process without passage may have been rejected or withdrawn,
so it gets no stage (the finished-is-not-adopted lesson from Stortinget).

License: Sejm open data (public domain per api.sejm.gov.pl terms).
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sejm.gov.pl/sejm/term{term}"

# Stems, not words (see module docstring). Specific first.
DEFAULT_TERMS = ["ciepł", "centrów danych", "centrum danych", "energ", "klimat"]
DEFAULT_TERM_OF_OFFICE = 10
DEFAULT_MAX_DOCUMENTS = 25


@register_source
class SejmSource(PolicySource):
    """Fetches Polish parliamentary prints from api.sejm.gov.pl."""

    id = "sejm"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = [t.lower() for t in (params.get("terms") or DEFAULT_TERMS)]
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        term_of_office = params.get("term", DEFAULT_TERM_OF_OFFICE)
        base = BASE_URL.format(term=term_of_office)

        results: list[CrawlResult] = []
        seen_numbers: set[str] = set()

        async with build_client() as client:
            prints = await self._list_prints(client, base)
            # Oldest-first on the wire; newest matters most under a cap.
            for print_doc in reversed(prints):
                if len(results) >= max_documents:
                    break
                if not self._matches(print_doc, terms):
                    continue
                result = await self._to_crawl_result(
                    client, base, print_doc, seen_numbers
                )
                if result:
                    results.append(result)

        return results

    async def _list_prints(self, client: httpx.AsyncClient, base: str) -> list[dict]:
        try:
            resp = await client.get(f"{base}/prints")
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Sejm prints list failed: %s", e)
            return []
        return [p for p in data if isinstance(p, dict)] if isinstance(data, list) else []

    @staticmethod
    def _matches(print_doc: dict, terms: list[str]) -> bool:
        title = (print_doc.get("title") or "").lower()
        return any(term in title for term in terms)

    async def _process_detail(
        self, client: httpx.AsyncClient, base: str, number: str
    ) -> dict:
        try:
            resp = await client.get(f"{base}/processes/{number}")
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Sejm process detail failed for %s: %s", number, e)
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _lifecycle(process: dict) -> str | None:
        """Stage from the legislative process, claimed conservatively.

        Open process -> "proposed". Closed with passed=true -> "passed"
        (the Sejm adopted it; enactment still needs Senate and President,
        so not "enacted"). Closed without passage -> None: it may have
        been rejected or withdrawn, and the analysis model can read which.
        """
        if not process:
            return None
        if not process.get("closureDate"):
            return "proposed"
        if process.get("passed") is True:
            return "passed"
        return None

    async def _to_crawl_result(
        self,
        client: httpx.AsyncClient,
        base: str,
        print_doc: dict,
        seen_numbers: set[str],
    ) -> CrawlResult | None:
        number = print_doc.get("number")
        if not number:
            return None
        number = str(number)
        if number in seen_numbers:
            return None
        seen_numbers.add(number)

        title = print_doc.get("title") or ""

        process_numbers = print_doc.get("processPrint") or [number]
        process = await self._process_detail(client, base, str(process_numbers[0]))

        meta = []
        doc_date = print_doc.get("documentDate")
        if doc_date:
            meta.append(f"Data dokumentu: {doc_date}.")
        doc_type = process.get("documentType")
        if doc_type:
            meta.append(f"Rodzaj: {doc_type}.")
        stages = [
            f"{s.get('date', '')} {s.get('stageName', '')}".strip()
            for s in (process.get("stages") or [])
            if isinstance(s, dict) and s.get("stageName")
        ]
        if stages:
            meta.append("Przebieg procesu: " + "; ".join(stages) + ".")

        attachments = print_doc.get("attachments") or []
        document_text = ""
        if attachments:
            url = f"{base}/prints/{number}/{attachments[0]}"
            document_text, _ = await fetch_document_text(client, url)
        else:
            url = f"{base}/prints/{number}"

        content = "\n\n".join(p for p in (
            title,
            " ".join(meta),
            document_text,
        ) if p and p.strip())
        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage=self._lifecycle(process),
        )
