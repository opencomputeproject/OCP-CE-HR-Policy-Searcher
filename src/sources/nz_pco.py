"""New Zealand PCO Legislation API structured policy source.

The official replacement for the WAF-blocked legacy feeds, and the
best-behaved API in the registry: genuine full-text content search
(nonsense terms return total=0, verified live 2026-07-17), typed filters,
and every hit carries official legislation.govt.nz URLs in HTML, PDF and
XML. NZ legislation is public domain.

Because search is full-text, precise domain phrases work here (like
gov.uk, unlike the title-only sources): "waste heat" 6 works,
"data centre" 7, "heat recovery" 5, measured on the production key.

Keyed: requires NZ_PCO_API_KEY (email contact@pco.govt.nz), sent via the
X-Api-Key header, never in the URL. Limits: 10k requests/day; the client
stays orders of magnitude below that.

Document-text caveat, measured 2026-07-17: the API serves METADATA ONLY,
and every format URL it hands out points at www.legislation.govt.nz, whose
AWS WAF answers scripts (any UA, even browser strings) with an empty
HTTP 202 challenge page. The client still attempts the fetch - harmless
today, and it starts working by itself if the WAF ever relaxes - but the
reliable signal is that the server's own FULL-TEXT search matched the
term inside the document, so that fact is written into the content where
the keyword and screening gates can see it.

Lifecycle mapping is conservative: bill "current" -> proposed, bill
"enacted" -> enacted, bill "terminated" -> nothing claimed (defeated,
withdrawn and lapsed look identical - finished is not adopted). Acts and
secondary legislation claim "enacted" only when in force; "not_in_force"
is ambiguous between repealed and not-yet-commenced, so it claims nothing.
"""

import logging
import os

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

API_KEY_ENV = "NZ_PCO_API_KEY"
SEARCH_URL = "https://api.legislation.govt.nz/v0/works/"

DEFAULT_TERMS = [
    "waste heat",
    "heat recovery",
    "data centre",
    "district heating",
    "energy efficiency",
]
DEFAULT_MAX_DOCUMENTS = 25
PER_TERM_RECORDS = 10


def _quote(term: str) -> str:
    """Phrase-quote multi-word terms so "waste heat" doesn't match every
    act containing "waste" and "heat" separately."""
    return f'"{term}"' if " " in term and not term.startswith('"') else term


def _lifecycle(work: dict) -> str | None:
    if work.get("legislation_type") == "bill":
        status = work.get("bill_status")
        if status == "current":
            return "proposed"
        if status == "enacted":
            return "enacted"
        return None  # terminated: defeated/withdrawn/lapsed all look alike
    if work.get("legislation_status") == "in_force":
        return "enacted"
    return None  # not_in_force: repealed and not-yet-commenced look alike


def _best_format_url(work: dict) -> tuple[str, str]:
    """(citation URL, title) preferring the human-readable HTML format."""
    version = work.get("latest_matching_version") or {}
    title = version.get("title") or ""
    formats = version.get("formats") or []
    by_type = {
        f.get("type"): f.get("url")
        for f in formats
        if isinstance(f, dict) and f.get("url")
    }
    url = by_type.get("html") or by_type.get("pdf") or by_type.get("xml") or ""
    return url, title


@register_source
class NZPCOSource(PolicySource):
    """Fetches NZ bills, acts and secondary legislation from the PCO API."""

    id = "nz_pco"
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
        seen_work_ids: set[str] = set()

        async with build_client() as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                for work in await self._search(client, api_key, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(
                        client, work, term, seen_work_ids
                    )
                    if result:
                        results.append(result)

        return results

    async def _search(
        self, client: httpx.AsyncClient, api_key: str, term: str
    ) -> list[dict]:
        try:
            resp = await client.get(
                SEARCH_URL,
                params={
                    "search_term": _quote(term),
                    "search_field": "content",
                    "per_page": PER_TERM_RECORDS,
                    "sort_by": "most_recently_updated",
                },
                # Key goes in the header, never the URL: URLs end up in
                # logs, caches and error messages.
                headers={"X-Api-Key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("NZ PCO search failed for %r: %s", term, e)
            return []

        works = data.get("results") if isinstance(data, dict) else None
        return [w for w in works if isinstance(w, dict)] if isinstance(works, list) else []

    async def _to_crawl_result(
        self,
        client: httpx.AsyncClient,
        work: dict,
        term: str,
        seen_work_ids: set[str],
    ) -> CrawlResult | None:
        work_id = work.get("work_id")
        if not work_id or not isinstance(work_id, str):
            return None
        if work_id in seen_work_ids:
            return None
        seen_work_ids.add(work_id)

        url, title = _best_format_url(work)
        if not url:
            return None

        meta = []
        leg_type = work.get("legislation_type")
        if leg_type:
            meta.append(f"Type: {leg_type}.")
        if work.get("bill_status"):
            meta.append(f"Bill status: {work['bill_status']}.")
        if work.get("legislation_status"):
            meta.append(f"Status: {work['legislation_status']}.")
        agencies = [a for a in (work.get("administering_agencies") or []) if a]
        if agencies:
            meta.append(f"Administering agencies: {', '.join(agencies)}.")
        # The API's own full-text index matched this term inside the
        # document. With the document body WAF-blocked (see module
        # docstring), this line IS the content signal.
        meta.append(f'Full-text search matched "{term}" within this legislation.')

        document_text, _ = await fetch_document_text(client, url)

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
            lifecycle_stage=_lifecycle(work),
        )
