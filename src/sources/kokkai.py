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

Signals lane (added 2026-09-02, WP-3; ADR-0007, status Proposed, ships
switched OFF, default lane stays "policies"): the reviewer removed 11 of 11
Kokkai rows as "not a policy", every one a Diet speech, exactly the low
yield this source's docstring already predicted. `source_params.lane:
"signals"` routes each matching speech into the lead queue instead
(`src/storage/leads.py`, `origin="kokkai"`) rather than the analysis
pipeline: no model spend, and the speech still surfaces in the Admin tips
inbox for a person to chase. `fetch()` returns `[]` in this lane: the
scanner never sees a CrawlResult, only the leads written directly to
`LeadStore`. The default lane, "policies", is unchanged from today.
"""

import asyncio
import logging
import os
import re

import httpx

from ..core.models import CrawlResult, PageStatus
from ..storage.leads import Lead, LeadStore
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

# Today's behaviour: every matching speech goes to analysis as a policy
# candidate. "signals" instead files it as a lead; see module docstring.
DEFAULT_LANE = "policies"
SIGNALS_LANE = "signals"

# A lead snippet prefers the sentence containing the search term; this caps
# the fallback when no sentence boundary is found.
SNIPPET_FALLBACK_CHARS = 300


@register_source
class KokkaiSource(PolicySource):
    """Fetches Japanese Diet proceedings from the NDL Kokkai API."""

    id = "kokkai"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        lane = params.get("lane") or DEFAULT_LANE

        collected: list = []
        seen_urls: set[str] = set()

        async with build_client() as client:
            for index, term in enumerate(terms):
                if len(collected) >= max_documents:
                    break
                # Space every request after the first; never burst, never
                # run these concurrently.
                if index:
                    await asyncio.sleep(REQUEST_SPACING_SECONDS)
                for speech in await self._search(client, term):
                    if len(collected) >= max_documents:
                        break
                    item = (
                        self._to_lead(speech, seen_urls, term)
                        if lane == SIGNALS_LANE
                        else self._to_crawl_result(speech, seen_urls)
                    )
                    if item:
                        collected.append(item)

        if lane == SIGNALS_LANE:
            # No model spend in this lane: leads wait in the tips inbox for
            # a person to chase. The scanner sees no CrawlResult at all.
            data_dir = os.environ.get("OCP_DATA_DIR", "data")
            LeadStore(data_dir).add_leads(collected)
            return []

        return collected

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

    @staticmethod
    def _matching_sentence(text: str, term: str) -> str:
        """The sentence containing the search term, or "" if none does.

        Japanese sentences end in 。 rather than a period; splitting on it
        (and on newlines, for header-like breaks) is enough for a snippet.
        This is not a general-purpose sentence tokenizer.
        """
        for sentence in re.split(r"(?<=[。\n])", text):
            if term in sentence:
                return sentence.strip()
        return ""

    def _to_lead(
        self, speech: dict, seen_urls: set[str], term: str
    ) -> Lead | None:
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
        # House + meeting, not date + house + meeting: the date already has
        # its own place in the title format below, so folding it in here
        # too would print it twice.
        meeting_title = " ".join(p for p in (house, meeting) if p)

        snippet = self._matching_sentence(text, term) or text[:SNIPPET_FALLBACK_CHARS]

        return Lead(
            title=f"{speaker or 'Diet speech'}, {date}: {meeting_title}",
            source_url=url,
            snippet=snippet,
            origin="kokkai",
            jurisdiction_guess="Japan",
        )
