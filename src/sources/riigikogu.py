"""Estonia Riigikogu structured policy source.

The Riigikogu documents API is the rare keyless source with a working
server-side title filter (verified live 2026-07-17: a nonsense title
returns totalElements=0). Two operational facts shape this client:

- Estonian inflects. "kaugküte" (district heating, nominative) matched 0
  titles while the stem "kaugküt" matched 61, because titles use the
  genitive "kaugkütte". The filter is substring-based, so defaults are
  stems, not dictionary forms.
- The API rate-limits aggressively (429 at 2 requests/second per the
  catalog probe), so consecutive requests are spaced.

Citations prefer the document's PUBLIC PDF download (an official
riigikogu.ee URL serving the actual document); documents without one fall
back to the document API URL.

License: Riigikogu open data terms.
"""

import asyncio
import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

LIST_URL = "https://api.riigikogu.ee/api/documents"
DOCUMENT_URL = "https://api.riigikogu.ee/api/documents/{uuid}"

# Stems, not dictionary forms (see module docstring). Measured 2026-07-17:
# soojus 35 (heat; also catches heitsoojus/soojusenergia), kaugküt 61,
# andmekeskus 1, energia 1428 (broad; listed last so the cap spends itself
# on the specific terms first).
DEFAULT_TERMS = ["soojus", "kaugküt", "andmekeskus", "energia"]
DEFAULT_MAX_DOCUMENTS = 25
PER_TERM_RECORDS = 25

# 429 observed at 2 req/s; stay well under it, never burst.
REQUEST_SPACING_SECONDS = 1.0


@register_source
class RiigikoguSource(PolicySource):
    """Fetches Estonian parliamentary documents from api.riigikogu.ee."""

    id = "riigikogu"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)

        results: list[CrawlResult] = []
        seen_uuids: set[str] = set()
        self._request_count = 0

        async with build_client() as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                for doc in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(client, doc, seen_uuids)
                    if result:
                        results.append(result)

        return results

    async def _spaced(self):
        """Space every request after the first; the API 429s at 2 req/s."""
        if self._request_count:
            await asyncio.sleep(REQUEST_SPACING_SECONDS)
        self._request_count += 1

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        await self._spaced()
        try:
            resp = await client.get(
                LIST_URL,
                params={"title": term, "size": PER_TERM_RECORDS},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Riigikogu search failed for %r: %s", term, e)
            return []

        embedded = data.get("_embedded") if isinstance(data, dict) else None
        docs = embedded.get("content") if isinstance(embedded, dict) else None
        return [d for d in docs if isinstance(d, dict)] if isinstance(docs, list) else []

    async def _detail(self, client: httpx.AsyncClient, uuid: str) -> dict:
        await self._spaced()
        try:
            resp = await client.get(DOCUMENT_URL.format(uuid=uuid))
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Riigikogu detail failed for %s: %s", uuid, e)
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _public_pdf_url(detail: dict) -> str:
        """Download URL of the first PUBLIC PDF, or "".

        Restricted files would give readers a dead link, and .asice
        containers (signed envelopes) are not readable documents.
        """
        for file in detail.get("files") or []:
            if not isinstance(file, dict):
                continue
            if (file.get("fileExtension") or "").lower() != "pdf":
                continue
            if file.get("accessRestrictionType") != "PUBLIC":
                continue
            href = ((file.get("_links") or {}).get("download") or {}).get("href")
            if href:
                return href
        return ""

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, doc: dict, seen_uuids: set[str]
    ) -> CrawlResult | None:
        uuid = doc.get("uuid")
        if not uuid or not isinstance(uuid, str):
            return None
        if uuid in seen_uuids:
            return None
        seen_uuids.add(uuid)

        detail = await self._detail(client, uuid)
        title = detail.get("title") or doc.get("title") or ""

        meta = []
        created = (detail.get("created") or doc.get("created") or "")[:10]
        if created:
            meta.append(f"Loodud: {created}.")
        doc_type = detail.get("documentType") or doc.get("documentType")
        if doc_type:
            meta.append(f"Dokumendi liik: {doc_type}.")
        committee = (detail.get("committee") or {}).get("name")
        if committee:
            meta.append(f"Komisjon: {committee}.")
        volume = (detail.get("volume") or {}).get("title")
        if volume:
            meta.append(f"Toimik: {volume}.")

        pdf_url = self._public_pdf_url(detail)
        document_text = ""
        if pdf_url:
            await self._spaced()
            document_text, _ = await fetch_document_text(client, pdf_url)

        url = pdf_url or DOCUMENT_URL.format(uuid=uuid)

        content = "\n\n".join(p for p in (
            title,
            " ".join(meta),
            document_text,
        ) if p and p.strip())
        if not content:
            return None

        # The documents index mixes bills, EU positions, letters and
        # statements; documentType does not map cleanly onto a bill
        # pipeline, so claim no stage and let the analysis model read.
        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage=None,
        )
