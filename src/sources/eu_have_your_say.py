"""EU "Have Your Say" (Better Regulation portal) structured policy source.

The earliest signal of all sources here. EUR-Lex and national law APIs show
a policy once it exists; this shows Commission initiatives while they are
still being shaped, with an explicit feedback window. A
receivingFeedbackStatus of OPEN plus a feedbackEndDate is the one state
where the heat-reuse community can still influence an EU act.

The API is undocumented and internal to the Commission's portal, so it may
change without notice. Build defensively: never raise, degrade to fewer
results, and pin its known quirks in tests.

Known quirks (verified live 2026-07-17):
- `language` and `page` are effectively REQUIRED; omitting either yields
  HTTP 500 "general_error".
- `id` arrives as a float (14628.0) but the public URL needs an integer.
- The detail endpoint 500s if `text` is passed through to it.
- Dates are "YYYY/MM/DD HH:MM:SS" strings, not ISO 8601.

License: Commission content reuse (Decision 2011/833/EU, CC BY 4.0-aligned).
"""

import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

API_BASE = "https://ec.europa.eu/info/law/better-regulation/brpapi"
SEARCH_URL = f"{API_BASE}/searchInitiatives"
DETAIL_URL = f"{API_BASE}/groupInitiatives/{{initiative_id}}"
PUBLIC_URL = (
    "https://ec.europa.eu/info/law/better-regulation/have-your-say/initiatives/{initiative_id}"
)

DEFAULT_TERMS = [
    "waste heat",
    "district heating",
    "heat network",
    "data centre",
    "energy efficiency",
]
DEFAULT_MAX_DOCUMENTS = 25
SEARCH_PAGE_SIZE = 50
LANGUAGE = "EN"


def _initiative_id(raw) -> str | None:
    """id arrives as a float; the public URL needs a plain integer."""
    if raw is None:
        return None
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return None


def _feedback_window(initiative: dict) -> tuple[bool, str, str]:
    """Return (is_open, start, end) across the initiative's statuses."""
    is_open, start, end = False, "", ""
    for status in initiative.get("currentStatuses") or []:
        if not isinstance(status, dict):
            continue
        if status.get("receivingFeedbackStatus") == "OPEN":
            is_open = True
            start = status.get("feedbackStartDate") or start
            end = status.get("feedbackEndDate") or end
        elif not start and not end:
            start = status.get("feedbackStartDate") or ""
            end = status.get("feedbackEndDate") or ""
    return is_open, start, end


@register_source
class EUHaveYourSaySource(PolicySource):
    """Fetches EU Commission initiatives and their feedback windows."""

    id = "eu_have_your_say"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        open_only = bool(params.get("open_only", False))

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()

        async with build_client() as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                for initiative in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(
                        client, initiative, seen_urls, open_only
                    )
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(
                SEARCH_URL,
                params={
                    "text": term,
                    # language and page are required; without them: HTTP 500.
                    "language": LANGUAGE,
                    "page": 0,
                    "size": SEARCH_PAGE_SIZE,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("EU Have Your Say search failed for %r: %s", term, e)
            return []

        page = data.get("initiativeResultDtoPage") if isinstance(data, dict) else None
        content = page.get("content") if isinstance(page, dict) else None
        return content if isinstance(content, list) else []

    async def _detail(self, client: httpx.AsyncClient, initiative_id: str) -> dict:
        try:
            resp = await client.get(
                DETAIL_URL.format(initiative_id=initiative_id),
                # Passing `text` through here makes the detail endpoint 500.
                params={"language": LANGUAGE},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("EU initiative detail failed for %s: %s", initiative_id, e)
            return {}
        return data if isinstance(data, dict) else {}

    async def _to_crawl_result(
        self,
        client: httpx.AsyncClient,
        initiative: dict,
        seen_urls: set[str],
        open_only: bool,
    ) -> CrawlResult | None:
        if not isinstance(initiative, dict):
            return None

        initiative_id = _initiative_id(initiative.get("id"))
        if not initiative_id:
            return None

        is_open, start, end = _feedback_window(initiative)
        if open_only and not is_open:
            return None

        url = PUBLIC_URL.format(initiative_id=initiative_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        detail = await self._detail(client, initiative_id)
        title = detail.get("shortTitle") or initiative.get("shortTitle") or ""
        summary = detail.get("dossierSummary") or ""

        window_parts = []
        if is_open:
            window_parts.append("Feedback period is OPEN.")
        if start:
            window_parts.append(f"Feedback opened: {start}.")
        if end:
            window_parts.append(f"Feedback closes: {end}.")

        meta_parts = []
        if initiative.get("reference"):
            meta_parts.append(f"Reference: {initiative['reference']}.")
        if detail.get("dg"):
            meta_parts.append(f"Lead DG: {detail['dg']}.")
        topics = [
            t.get("label") for t in (initiative.get("topics") or [])
            if isinstance(t, dict) and t.get("label")
        ]
        if topics:
            meta_parts.append(f"Topics: {', '.join(topics)}.")

        content = "\n\n".join(p for p in (
            title, " ".join(window_parts), " ".join(meta_parts), summary,
        ) if p.strip())
        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage="consultation" if is_open else "proposed",
        )
