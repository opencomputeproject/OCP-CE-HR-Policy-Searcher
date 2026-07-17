"""Greece Diavgeia (Δι@ύγεια) structured policy source.

Not a parliament API: Diavgeia is Greece's statutory transparency register.
By law (N. 3861/2010) every government act is INVALID until posted there,
which makes the register same-day early by statute. The Greek Parliament
itself has no open-data API, so this is Greece's structured channel.

Hard-won access lesson, pinned by a test: the plain `/opendata/search`
endpoint's `q` parameter is a NO-OP — a nonsense query returns the same
3.1M results as a real one (the same silent-filter trap that disqualified
Denmark's Retsinformation). Only `/opendata/search/advanced` with Lucene
`subject:"..."` syntax actually filters; verified live 2026-07-17 with a
nonsense subject returning total=0. The server also applies a rolling
~6-month issueDate window automatically, so recency comes for free.

Search stems Greek: κέντρα δεδομένων and κέντρων δεδομένων both return the
same 99 acts, so one grammatical form per term suffices.

License: Greek open government data (Diavgeia terms allow reads keylessly).
"""

import logging
from datetime import datetime, timezone

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://diavgeia.gov.gr/opendata/search/advanced"
PUBLIC_URL = "https://diavgeia.gov.gr/doc/{ada}"

# Measured live 2026-07-17 (rolling ~6-month window):
#   τηλεθέρμανση 586, ενεργειακή απόδοση 518, κέντρα δεδομένων 99,
#   ανάκτηση θερμότητας 33, απορριπτόμενη θερμότητα 3.
# Specific terms first so the max_documents cap spends itself on-topic.
DEFAULT_TERMS = [
    "απορριπτόμενη θερμότητα",   # waste heat
    "ανάκτηση θερμότητας",       # heat recovery
    "κέντρα δεδομένων",          # data centres
    "τηλεθέρμανση",              # district heating
    "ενεργειακή απόδοση",        # energy efficiency
]
DEFAULT_MAX_DOCUMENTS = 25
PER_TERM_RECORDS = 10


def _epoch_ms_to_iso(value) -> str:
    """Convert Diavgeia's epoch-millisecond timestamps to "YYYY-MM-DD".

    Returns "" for anything unparseable or out of range rather than
    raising: a cosmetic date must never cost us a real policy.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    try:
        moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return moment.strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return ""


@register_source
class DiavgeiaSource(PolicySource):
    """Fetches Greek government acts from the Diavgeia transparency register."""

    id = "diavgeia"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)

        results: list[CrawlResult] = []
        seen_adas: set[str] = set()

        async with build_client() as client:
            for term in terms:
                if len(results) >= max_documents:
                    break
                for decision in await self._search(client, term):
                    if len(results) >= max_documents:
                        break
                    result = await self._to_crawl_result(client, decision, seen_adas)
                    if result:
                        results.append(result)

        return results

    async def _search(self, client: httpx.AsyncClient, term: str) -> list[dict]:
        try:
            resp = await client.get(
                SEARCH_URL,
                params={
                    "q": f'subject:"{term}"',
                    "size": PER_TERM_RECORDS,
                    "page": 0,
                },
                # Without this Diavgeia answers in XML.
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Diavgeia search failed for %r: %s", term, e)
            return []

        decisions = data.get("decisions") if isinstance(data, dict) else None
        return [d for d in decisions if isinstance(d, dict)] if isinstance(decisions, list) else []

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, decision: dict, seen_adas: set[str]
    ) -> CrawlResult | None:
        ada = decision.get("ada")
        if not ada or not isinstance(ada, str):
            return None
        if ada in seen_adas:
            return None
        seen_adas.add(ada)

        url = PUBLIC_URL.format(ada=ada)
        subject = (decision.get("subject") or "").strip()

        meta = []
        issued = _epoch_ms_to_iso(decision.get("issueDate"))
        if issued:
            meta.append(f"Ημερομηνία έκδοσης: {issued}.")
        meta.append(f"ΑΔΑ: {ada}.")
        protocol = decision.get("protocolNumber")
        if protocol:
            meta.append(f"Αρ. πρωτοκόλλου: {protocol}.")

        # The register's own metadata is thin (one subject line), so pull
        # the act's actual text from the official PDF; fall back to
        # metadata-only if the document is unavailable or a scanned image.
        document_text = ""
        document_url = decision.get("documentUrl")
        if document_url:
            document_text, _ = await fetch_document_text(client, document_url)

        content = "\n\n".join(p for p in (
            subject,
            " ".join(meta),
            document_text,
        ) if p and p.strip())
        if not content:
            return None

        # Diavgeia posts executive acts, not bills; the register says
        # nothing about a legislative pipeline stage, so claim none.
        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=subject,
            lifecycle_stage=None,
        )
