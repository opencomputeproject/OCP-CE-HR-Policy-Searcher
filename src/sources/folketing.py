"""Folketing (Danish Parliament) structured policy source.

Queries the Folketing's OData API (oda.ft.dk) for parliamentary cases
(Sag) whose title matches waste-heat or district-heating terms. The
list endpoint carries a summary (resume) but no full document text, so
content is built from the title and summary.

Document-type allow-list (added 2026-09-02, WP-3): the reviewer removed 17
of the tool's Folketing rows as "not a policy", every one a `§
20-spørgsmål` (a written question to a minister) or an `Aktstykke`
(a budget-transfer act, not law). Confirmed live 2026-09-02:
`GET https://oda.ft.dk/api/Sagstype?$format=json` lists the case-type
vocabulary (id -> type): 1 UMF-del, 2 Forespørgsel, 3 Lovforslag (bill),
4 Alm. del, 5 Beslutningsforslag (motion for a resolution), 6 Rådsmøde,
7 Kommissionsforslag, 8 Aktstykke, 9 Forslag til vedtagelse
(motion to be adopted), 10 § 20-spørgsmål, 11 Redegørelse,
12 Indkaldelse af stedfortræder, 13 Statsrevisorerne. Searching
"overskudsvarme" live returned 18 cases: typeid 10 (question) x12,
typeid 3 (bill) x5, typeid 9 (motion to be adopted) x1: the 12 questions
are exactly what the reviewer removed. A case whose `typeid` is not in
DEFAULT_DOCUMENT_TYPE_IDS is dropped before any page is fetched or any
model is called, and counted in `dropped_doc_type`.

Document URL (same date): a case-overview page alone was flagged by the
reviewer as "link is for a general website". For each kept case, the
document is resolved by expanding `SagDokument/Dokument` (one call),
preferring the Dokument with `typeid == 21` ("Lovforslag som fremsat",
i.e. the bill as introduced) and falling back to the first Dokument, then
querying `Fil` for that document's `filurl` (one more call). Confirmed
live against Sag 36985 (L 80): 10 documents, including one `typeid: 21`
titled "Lovforslag som fremsat". `Fil.filurl` can be empty for a given
document, so at most two Fil lookups are tried (preferred, then the
first) before falling back to the case page: three extra requests per
kept case at most.
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
FIL_URL = "https://oda.ft.dk/api/Fil"
CASE_PAGE_URL = "https://www.ft.dk/samling/oversigt/sag.htm?sagId={sag_id}"
# Sagstype ids that are law-changing (see module docstring): 3 Lovforslag
# (bill), 5 Beslutningsforslag (motion for a resolution), 9 Forslag til
# vedtagelse (motion to be adopted). Excludes questions (10), budget
# transfers (8) and the procedural/report types.
DEFAULT_DOCUMENT_TYPE_IDS = [3, 5, 9]
# The Dokument typeid for a bill "as introduced": the substantive text,
# preferred over amendments, committee reports or cover letters.
PREFERRED_DOCUMENT_TYPE_ID = 21


@register_source
class FolketingSource(PolicySource):
    """Fetches Danish parliamentary cases from oda.ft.dk."""

    id = "folketing"

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        self.dropped_doc_type = 0
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        document_types = params.get("document_types") or DEFAULT_DOCUMENT_TYPE_IDS

        results: list[CrawlResult] = []
        seen_sag_ids: set = set()
        seen_urls: set[str] = set()

        async with build_client() as client:
            for term in terms:
                # max_documents counts KEPT cases only: len(results) only
                # grows on a kept case, so a run of dropped questions never
                # exhausts the cap.
                if len(results) >= max_documents:
                    break
                for case in await self._search(client, term, max_documents):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(
                        client, case, seen_sag_ids, seen_urls, document_types,
                    )
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
                    "$select": "id,titel,resume,typeid",
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

    async def _expand_documents(
        self, client: httpx.AsyncClient, sag_id
    ) -> list[dict]:
        """The case's Dokument records, via `SagDokument/Dokument`. One call."""
        try:
            resp = await client.get(
                f"{SAG_URL}({sag_id})",
                params={"$expand": "SagDokument/Dokument", "$format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Folketing document expand failed for Sag %s: %s", sag_id, e)
            return []

        sag_dokument = data.get("SagDokument") if isinstance(data, dict) else None
        if not isinstance(sag_dokument, list):
            return []
        documents = []
        for entry in sag_dokument:
            doc = entry.get("Dokument") if isinstance(entry, dict) else None
            if isinstance(doc, dict):
                documents.append(doc)
        return documents

    async def _fil_url(self, client: httpx.AsyncClient, dokument_id) -> str:
        """The first non-empty `filurl` for a document. One call."""
        try:
            resp = await client.get(
                FIL_URL,
                params={"$filter": f"dokumentid eq {dokument_id}", "$format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Folketing Fil lookup failed for document %s: %s", dokument_id, e)
            return ""

        value = data.get("value") if isinstance(data, dict) else None
        if not isinstance(value, list):
            return ""
        for entry in value:
            if isinstance(entry, dict) and entry.get("filurl"):
                return entry["filurl"]
        return ""

    async def _document_url(
        self, client: httpx.AsyncClient, sag_id, case_page_url: str
    ) -> str:
        """The bill document's file URL, or the case page as a last resort.

        Prefers the Dokument with typeid == 21 ("som fremsat"), then the
        first Dokument returned; tries Fil for each in turn. At most one
        expand call plus two Fil lookups: three extra requests total.
        """
        documents = await self._expand_documents(client, sag_id)
        if not documents:
            return case_page_url

        preferred = next(
            (d for d in documents if d.get("typeid") == PREFERRED_DOCUMENT_TYPE_ID), None
        )
        first = documents[0]

        candidates = [preferred] if preferred else []
        if first.get("id") != (preferred or {}).get("id"):
            candidates.append(first)

        for doc in candidates:
            doc_id = doc.get("id")
            if doc_id is None:
                continue
            fil_url = await self._fil_url(client, doc_id)
            if fil_url:
                return fil_url

        return case_page_url

    async def _to_crawl_result(
        self,
        client: httpx.AsyncClient,
        case: dict,
        seen_sag_ids: set,
        seen_urls: set[str],
        document_types: list[int],
    ) -> CrawlResult | None:
        if not isinstance(case, dict):
            return None
        sag_id = case.get("id")
        if sag_id is None or sag_id in seen_sag_ids:
            return None
        seen_sag_ids.add(sag_id)

        typeid = case.get("typeid")
        if typeid not in document_types:
            self.dropped_doc_type += 1
            logger.debug(
                "Folketing dropped by document-type allow-list: typeid=%r title=%r",
                typeid, case.get("titel"),
            )
            return None

        titel = case.get("titel") or ""
        resume = case.get("resume") or ""
        content = f"{titel}\n\n{resume}".strip()
        if not content:
            return None

        case_page_url = CASE_PAGE_URL.format(sag_id=sag_id)
        url = await self._document_url(client, sag_id, case_page_url)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=titel,
            lifecycle_stage="proposed",
        )
