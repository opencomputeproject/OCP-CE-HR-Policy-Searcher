"""Japan NDL Kokkai (Diet proceedings) structured policy source.

A leading indicator rather than a law register. Kokkai carries what the Diet
is *saying*; e-Gov carries what Japan has *enacted*. The gap between the two
is the signal: on 2026-06-12 an Environment Ministry official told the House
Environment Committee that Japanese environmental law has no framework
regulating waste heat at all, while acknowledging the data-centre build-out.
That is a regulatory vacuum being named in public, which is exactly the kind
of thing this project exists to catch early.

Consequence to be honest about: these documents are speeches, so most will
correctly fail the downstream screening gate ("is this a government policy
action?"). Low yield is the expected, correct behaviour. The source earns
its place on the day a minister first signals intent.

NDL asks API users not to burst: space requests seconds apart and make no
parallel calls. That is enforced here in code.

License: Government Standard Terms of Use v2.0 (CC BY 4.0 compatible).
"""

import asyncio
import logging

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://kokkai.ndl.go.jp/api/speech"

# Japanese writes waste heat two ways; both are needed (see egov_japan).
DEFAULT_TERMS = ["排熱", "廃熱", "未利用熱", "熱供給 データセンター"]
DEFAULT_MAX_DOCUMENTS = 15
PER_TERM_RECORDS = 20

# NDL politeness: seconds between calls, never parallel.
REQUEST_SPACING_SECONDS = 2.0

# Floor guard against procedural chatter ("○委員長　次に、田中君。", ~12 chars)
# reaching the analysis model. Measured over 40 live hits the shortest real
# speech was 171 chars (median 544), so this rarely fires — it only matters
# if a caller passes a term broad enough to match a one-line interjection.
MIN_SPEECH_LENGTH = 60


@register_source
class KokkaiSource(PolicySource):
    """Fetches Japanese Diet proceedings from the NDL Kokkai API."""

    id = "kokkai"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()

        async with build_client() as client:
            for index, term in enumerate(terms):
                if len(results) >= max_documents:
                    break
                # Space every request after the first; never burst, never
                # run these concurrently.
                if index:
                    await asyncio.sleep(REQUEST_SPACING_SECONDS)
                for speech in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = self._to_crawl_result(speech, seen_urls)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(
                SEARCH_URL,
                params={
                    "any": term,
                    "maximumRecords": PER_TERM_RECORDS,
                    "recordPacking": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Kokkai search failed for %r: %s", term, e)
            return []

        records = data.get("speechRecord") if isinstance(data, dict) else None
        return records if isinstance(records, list) else []

    def _to_crawl_result(
        self, speech: dict, seen_urls: set[str]
    ) -> CrawlResult | None:
        if not isinstance(speech, dict):
            return None

        url = speech.get("speechURL")
        if not url:
            return None
        if url in seen_urls:
            return None

        text = (speech.get("speech") or "").strip()
        if len(text) < MIN_SPEECH_LENGTH:
            return None

        seen_urls.add(url)

        date = speech.get("date") or ""
        house = speech.get("nameOfHouse") or ""
        meeting = speech.get("nameOfMeeting") or ""
        speaker = speech.get("speaker") or ""
        position = speech.get("speakerPosition") or ""

        title = " ".join(p for p in (date, house, meeting) if p).strip()
        header = " ".join(p for p in (
            f"発言日: {date}." if date else "",
            f"会議: {house} {meeting}.".strip() if (house or meeting) else "",
            f"発言者: {speaker} ({position})." if speaker else "",
        ) if p)

        content = "\n\n".join(p for p in (title, header, text) if p.strip())

        # A speech has no lifecycle stage. Since a source-declared stage
        # overrides the analysis model, claiming one here would be a lie.
        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title or (speech.get("speechID") or ""),
            lifecycle_stage=None,
        )
