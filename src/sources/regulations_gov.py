"""Regulations.gov structured policy source — US federal rulemaking dockets.

Searches the regulations.gov v4 documents endpoint and cites the official
regulations.gov document detail page. Open comment periods are surfaced
as lifecycle_stage="consultation" (with the deadline folded into content)
so downstream analysis sees the window before it closes. Disabled
entirely (returns []) until REGULATIONSGOV_API_KEY is set.

API terms (https://open.gsa.gov/api/regulationsgov/):
- Key sent in the X-Api-Key header (done below).
- api.data.gov default limit is 1000 GET/hour per key; on HTTP 429 the
  fetch stops rather than burning the remaining terms.
- Page size 25, far under the v4 maximum of 250.
- ATTRIBUTION REQUIREMENT (interface, not fulfilled here): before any
  public UI displays regulations.gov data, it MUST link to the
  Regulations.gov terms of participation and privacy notice
  (https://www.regulations.gov/user-notice). Tracked in the API key
  tracker as a pre-public-release obligation.
"""

import logging
import os
from datetime import datetime, timezone

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import TIMEOUT_SECONDS, USER_AGENT
from .base import PolicySource

logger = logging.getLogger(__name__)

API_KEY_ENV = "REGULATIONSGOV_API_KEY"
DOCUMENTS_URL = "https://api.regulations.gov/v4/documents"
DETAIL_URL = "https://www.regulations.gov/document/{doc_id}"
DEFAULT_TERMS = ["waste heat", "data center energy efficiency", "district heating"]
DEFAULT_MAX_DOCUMENTS = 25
PAGE_SIZE = 25


def _is_future(date_str: str) -> bool:
    if not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt > datetime.now(timezone.utc)


@register_source
class RegulationsGovSource(PolicySource):
    """Fetches US federal rulemaking documents from api.regulations.gov."""

    id = "regulations_gov"
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
            headers={"User-Agent": USER_AGENT, "X-Api-Key": api_key},
        ) as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                items, rate_limited = await self._search(client, term)
                for item in items:
                    if len(results) >= max_documents:
                        break
                    result = self._to_crawl_result(item, seen_urls)
                    if result:
                        results.append(result)
                if rate_limited:
                    # api.data.gov allows 1000 GET/hour per key; on a 429
                    # stop rather than burn the remaining terms into more
                    # throttled calls. The weekly cadence recovers next run.
                    break

        return results

    async def _search(
        self, client: httpx.AsyncClient, term: str,
    ) -> tuple[list[dict], bool]:
        """Return (documents, rate_limited). rate_limited=True on HTTP 429."""
        params = {
            "filter[searchTerm]": term,
            "sort": "-postedDate",
            "page[size]": PAGE_SIZE,
        }
        try:
            resp = await client.get(DOCUMENTS_URL, params=params)
            if getattr(resp, "status_code", 200) == 429:
                retry_after = resp.headers.get("Retry-After", "?")
                logger.warning(
                    "Regulations.gov rate limit hit (429, Retry-After=%s); "
                    "stopping this run", retry_after,
                )
                return [], True
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Regulations.gov search failed for term %r: %s", term, e)
            return [], False

        items = data.get("data") if isinstance(data, dict) else None
        return (items if isinstance(items, list) else []), False

    def _to_crawl_result(self, item: dict, seen_urls: set[str]) -> CrawlResult | None:
        if not isinstance(item, dict):
            return None
        doc_id = item.get("id")
        attrs = item.get("attributes")
        if not doc_id or not isinstance(attrs, dict):
            return None
        url = DETAIL_URL.format(doc_id=doc_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        title = attrs.get("title", "")
        document_type = attrs.get("documentType", "")
        docket_id = attrs.get("docketId", "")
        posted_date = attrs.get("postedDate", "")
        comment_end_date = attrs.get("commentEndDate", "")
        content = " ".join(
            part
            for part in (
                title,
                document_type,
                f"Docket: {docket_id}" if docket_id else "",
                f"Posted: {posted_date}" if posted_date else "",
                f"Comment end: {comment_end_date}" if comment_end_date else "",
            )
            if part
        )
        if not content:
            return None
        lifecycle_stage = "consultation" if _is_future(comment_end_date) else "proposed"

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            title=title,
            lifecycle_stage=lifecycle_stage,
        )
