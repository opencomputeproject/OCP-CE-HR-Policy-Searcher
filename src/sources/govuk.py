"""UK gov.uk consultations and policy papers structured policy source.

Complements uk_bills. A bill is late: by the time one exists the shape of
the policy is largely settled. gov.uk consultations, calls for evidence and
policy papers appear months earlier, and an *open* consultation carries a
closing date — the window where outside input can still change the outcome.

Two APIs, both keyless:
- Search  https://www.gov.uk/api/search.json  (full-text, unlike Oireachtas)
- Content https://www.gov.uk/api/content{path} (body + closing_date)

License: Open Government Licence v3.0.
"""

import logging

import httpx
from bs4 import BeautifulSoup

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

# gov.uk search IS full-text, so precise domain phrases work here (unlike
# the title-only Oireachtas API, which needs broad single words).
DEFAULT_TERMS = [
    "heat network",
    "waste heat",
    "district heating",
    "heat reuse",
    "data centre",
]
DEFAULT_MAX_DOCUMENTS = 25
SEARCH_PAGE_SIZE = 50
MIN_CONTENT_LENGTH = 200

BASE = "https://www.gov.uk"
SEARCH_URL = f"{BASE}/api/search.json"
CONTENT_URL = f"{BASE}/api/content"

# Everything policy-shaped: consultations, calls for evidence, policy papers.
CONTENT_SUPERGROUP = "policy_and_engagement"

# An OPEN window is the early signal; a closed one is history.
_OPEN_FORMATS = {"open_consultation", "open_call_for_evidence"}


def _lifecycle_from_format(fmt: str) -> str:
    return "consultation" if fmt in _OPEN_FORMATS else "proposed"


def _strip_html(html: str) -> str:
    if not html:
        return ""
    try:
        return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("gov.uk body parse failed: %s", e)
        return ""


def _quote(term: str) -> str:
    """Phrase-search multi-word terms so "heat network" doesn't match
    every page containing "heat" and "network" separately."""
    return f'"{term}"' if " " in term and not term.startswith('"') else term


@register_source
class GovUKSource(PolicySource):
    """Fetches UK consultations and policy papers from gov.uk."""

    id = "govuk"
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
                for hit in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(client, hit, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(
                SEARCH_URL,
                params={
                    "q": _quote(term),
                    "filter_content_purpose_supergroup": CONTENT_SUPERGROUP,
                    "count": SEARCH_PAGE_SIZE,
                    "order": "-public_timestamp",
                    "fields": "title,description,link,format,public_timestamp",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("gov.uk search failed for %r: %s", term, e)
            return []

        hits = data.get("results") if isinstance(data, dict) else None
        return hits if isinstance(hits, list) else []

    async def _fetch_content(self, client: httpx.AsyncClient, path: str) -> dict:
        try:
            resp = await client.get(f"{CONTENT_URL}{path}")
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("gov.uk content fetch failed for %s: %s", path, e)
            return {}
        return data if isinstance(data, dict) else {}

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, hit: dict, seen_urls: set[str]
    ) -> CrawlResult | None:
        if not isinstance(hit, dict):
            return None
        path = hit.get("link")
        if not path or not isinstance(path, str):
            return None

        url = path if path.startswith("http") else f"{BASE}{path}"
        if url in seen_urls:
            return None
        seen_urls.add(url)

        fmt = hit.get("format") or ""
        title = hit.get("title") or ""
        description = hit.get("description") or ""

        content_doc = await self._fetch_content(client, path)
        details = content_doc.get("details") or {}
        body = _strip_html(details.get("body") or "")

        # The deadline is the reason an open consultation matters, so put it
        # where the analysis model will actually read it.
        window_parts = []
        if details.get("opening_date"):
            window_parts.append(f"Consultation opened: {details['opening_date']}")
        if details.get("closing_date"):
            window_parts.append(f"Consultation closes: {details['closing_date']}")
        window = ". ".join(window_parts)

        content = "\n\n".join(p for p in (title, description, window, body) if p.strip())
        if len(content) < MIN_CONTENT_LENGTH and not description:
            return None
        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage=_lifecycle_from_format(fmt),
        )
