"""Japan e-Gov Law API v2 structured policy source.

Enacted Japanese law with real full-text search. Pairs with the Kokkai
source: Kokkai shows what the Diet is discussing, e-Gov shows what became
law. Japan matters here because it is a major data-centre market where, as
of mid-2026, officials are publicly acknowledging there is no waste-heat
regulation yet — so the gap between the two sources is itself the signal.

Verified live 2026-07-17. Two corrections to the source catalog:
- the result list key is `items`, NOT `laws`;
- Japanese writes waste heat two ways and the counts differ sharply:
  排熱 -> 1 law, 廃熱 -> 10 laws. Shipping one loses most of the results.

License: Government Standard Terms of Use v2.0 (CC BY 4.0 compatible).
"""

import logging
import re
from datetime import date

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://laws.e-gov.go.jp/api/2/keyword"
LAW_URL = "https://laws.e-gov.go.jp/law/{law_id}"

# Both waste-heat kanji, plus heat supply and data centres. 熱供給 alone
# matches 430 laws, so per-term caps matter more than breadth here.
DEFAULT_TERMS = ["排熱", "廃熱", "未利用熱", "熱供給", "データセンター"]
DEFAULT_MAX_DOCUMENTS = 25
PER_TERM_LIMIT = 20

_SPAN_RE = re.compile(r"</?span[^>]*>")


def _strip_highlight(text: str) -> str:
    """Matched sentences arrive with the term wrapped in <span> tags."""
    return _SPAN_RE.sub("", text or "").strip()


def _lifecycle(revision: dict) -> str:
    """e-Gov holds enacted law only, so the question is merely whether the
    current revision is in force yet."""
    scheduled = revision.get("amendment_scheduled_enforcement_date")
    if scheduled:
        try:
            if date.fromisoformat(str(scheduled)) > date.today():
                return "passed"
        except (TypeError, ValueError):
            # Unparseable date: fall through rather than guess.
            pass
    return "enacted"


@register_source
class EGovJapanSource(PolicySource):
    """Fetches enacted Japanese law from the e-Gov Law API v2."""

    id = "egov_japan"
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
                SEARCH_URL, params={"keyword": term, "limit": PER_TERM_LIMIT}
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("e-Gov search failed for %r: %s", term, e)
            return []

        # Live API returns "items"; the catalog said "laws" and was wrong.
        items = data.get("items") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    def _to_crawl_result(self, item: dict, seen_urls: set[str]) -> CrawlResult | None:
        if not isinstance(item, dict):
            return None
        law_info = item.get("law_info") or {}
        revision = item.get("revision_info") or {}

        law_id = law_info.get("law_id")
        if not law_id:
            return None

        url = LAW_URL.format(law_id=law_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        title = revision.get("law_title") or ""
        sentences = [
            _strip_highlight(s.get("text", ""))
            for s in (item.get("sentences") or [])
            if isinstance(s, dict)
        ]

        meta = [f"法令番号: {law_info['law_num']}." if law_info.get("law_num") else ""]
        if law_info.get("promulgation_date"):
            meta.append(f"公布日: {law_info['promulgation_date']}.")
        if revision.get("category"):
            meta.append(f"分類: {revision['category']}.")
        if revision.get("amendment_enforcement_date"):
            meta.append(f"施行日: {revision['amendment_enforcement_date']}.")
        scheduled = revision.get("amendment_scheduled_enforcement_date")
        if scheduled:
            meta.append(f"施行予定日 (scheduled enforcement): {scheduled}.")

        content = "\n\n".join(p for p in (
            title, " ".join(m for m in meta if m), "\n".join(sentences),
        ) if p.strip())
        if not content:
            return None

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage=_lifecycle(revision),
        )
