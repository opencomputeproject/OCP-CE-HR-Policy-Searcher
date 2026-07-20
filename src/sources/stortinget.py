"""Norway Stortinget structured policy source.

Norway matters disproportionately here: district heating is mainstream and
the Storting is actively amending the Energy Act to cover surplus heat from
data centres ("Endringer i energiloven (utnyttelse av overskuddsvarme...)").

Two corrections to the source catalog, both found by measuring live data:
- The suggested search terms were wrong. Across all 650 saker of session
  2025-2026, "spillvarme" and "fjernvarme" each matched ZERO. Norwegian
  legislative titles say **overskuddsvarme** (surplus heat). "energi"
  matched 7 saker and catches the Energy Act amendment.
- Dates are .NET WCF format ("/Date(1782338400000+0200)/"), not ISO 8601.

The list endpoint carries titles only, so like the Oireachtas client this
one matches titles locally with deliberately broad terms and lets the
keyword and screening gates do precision.

License: NLOD (Norwegian Licence for Open Government Data).
"""

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client
from .base import PolicySource

logger = logging.getLogger(__name__)

LIST_URL = "https://data.stortinget.no/eksport/saker"
DETAIL_URL = "https://data.stortinget.no/eksport/sak"
PUBLIC_URL = "https://www.stortinget.no/no/Saker-og-publikasjoner/Saker/Sak/?p={sak_id}"

# Broad, per the measurement above. "overskuddsvarme" is the correct
# Norwegian domain term and is kept so an exact hit is never missed.
DEFAULT_TERMS = ["energi", "overskuddsvarme", "varme", "datasenter", "klima"]
DEFAULT_SESSION = "2025-2026"
DEFAULT_MAX_DOCUMENTS = 25

_WCF_RE = re.compile(r"/Date\((-?\d+)([+-]\d{4})?\)/")


def _parse_wcf_date(value) -> str:
    """Convert "/Date(1782338400000+0200)/" to "YYYY-MM-DD".

    The trailing offset is part of the value and must be applied: the
    example above is 22:00 UTC on the 24th but midnight on the 25th in
    Oslo, and Stortinget means the 25th. Dropping the offset silently
    reports every late-evening case a day early.

    Returns "" for anything unparseable rather than raising: a cosmetic
    date must never cost us a real policy.
    """
    if not isinstance(value, str):
        return ""
    match = _WCF_RE.search(value)
    if not match:
        return ""
    try:
        millis = int(match.group(1))
        moment = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
        offset = match.group(2)
        if offset:
            sign = 1 if offset[0] == "+" else -1
            delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5]))
            moment = moment + sign * delta
        return moment.strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return ""


@register_source
class StortingetSource(PolicySource):
    """Fetches Norwegian parliamentary cases from data.stortinget.no."""

    id = "stortinget"
    api_key_env = None

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        terms = [t.lower() for t in (params.get("terms") or DEFAULT_TERMS)]
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        session = params.get("session") or DEFAULT_SESSION

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()

        async with build_client() as client:
            for sak in await self._list_saker(client, session):
                if len(results) >= max_documents:
                    break
                if not self._matches(sak, terms):
                    continue
                result = await self._to_crawl_result(client, sak, seen_urls)
                if result:
                    results.append(result)

        return results

    async def _list_saker(self, client: httpx.AsyncClient, session: str) -> list[dict]:
        try:
            resp = await client.get(
                LIST_URL, params={"format": "json", "sesjonid": session}
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Stortinget list failed (session=%s): %s", session, e)
            return []

        saker = data.get("saker_liste") if isinstance(data, dict) else None
        return [s for s in saker if isinstance(s, dict)] if isinstance(saker, list) else []

    @staticmethod
    def _matches(sak: dict, terms: list[str]) -> bool:
        haystack = " ".join([
            sak.get("tittel") or "", sak.get("korttittel") or "",
        ]).lower()
        return any(term in haystack for term in terms)

    async def _detail(self, client: httpx.AsyncClient, sak_id) -> dict:
        try:
            resp = await client.get(
                DETAIL_URL, params={"sakid": sak_id, "format": "json"}
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("Stortinget detail failed for %s: %s", sak_id, e)
            return {}
        return data if isinstance(data, dict) else {}

    async def _to_crawl_result(
        self, client: httpx.AsyncClient, sak: dict, seen_urls: set[str]
    ) -> CrawlResult | None:
        sak_id = sak.get("id")
        if sak_id is None:
            return None

        url = PUBLIC_URL.format(sak_id=sak_id)
        if url in seen_urls:
            return None
        seen_urls.add(url)

        detail = await self._detail(client, sak_id)
        title = detail.get("tittel") or sak.get("tittel") or ""

        meta = []
        updated = _parse_wcf_date(sak.get("sist_oppdatert_dato"))
        if updated:
            meta.append(f"Sist oppdatert: {updated}.")
        komite = (sak.get("komite") or {}).get("navn")
        if komite:
            meta.append(f"Komite: {komite}.")
        emner = [
            e.get("navn") for e in (sak.get("emne_liste") or [])
            if isinstance(e, dict) and e.get("navn")
        ]
        if emner:
            meta.append(f"Emner: {', '.join(emner)}.")

        content = "\n\n".join(p for p in (
            title,
            " ".join(meta),
            detail.get("kortvedtak") or "",
            detail.get("innstillingstekst") or "",
            detail.get("vedtakstekst") or "",
        ) if p and p.strip())
        if not content:
            return None

        # `ferdigbehandlet` means the Storting finished processing, NOT that
        # the proposal was adopted — it can finish by rejecting. kortvedtak
        # records which, so leave the stage for the analysis model rather
        # than override it with a guess.
        lifecycle_stage = None if detail.get("ferdigbehandlet") else "proposed"

        return CrawlResult(
            url=url,
            status=PageStatus.SUCCESS,
            content=content,
            content_type="text/plain",
            title=title,
            lifecycle_stage=lifecycle_stage,
        )
