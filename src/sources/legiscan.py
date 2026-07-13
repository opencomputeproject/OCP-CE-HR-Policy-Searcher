"""LegiScan structured policy source — US state legislation.

Searches LegiScan's getSearchRaw op for candidate bills, then resolves
each hit's official state legislature URL via getBill (LegiScan itself is
only an aggregator; its own bill pages are never used as the citation of
record). Full bill text is deliberately never fetched (getBillText) to
conserve the API quota — screening/analysis works off title + description
+ last action instead. Disabled entirely (returns []) until
LEGISCAN_API_KEY is set.

Follows the LegiScan API Crash Course
(https://legiscan.com/legiscan/crashcourse):
- Only the API (api.legiscan.com) is used; the legiscan.com front end is
  never scraped (that is prohibited and gets keys suspended - it is listed
  in config/rejected_sites).
- change_hash is cached per bill (data/legiscan_seen.json) so unchanged
  bills never spend a getBill query on rerun ("use the hashes").
- The JSON "status" field is checked; an ERROR (e.g. the 30,000/month
  public limit, which resets on the 1st) halts the run instead of burning
  more queries.
- Data is CC BY 4.0: any published output must credit LegiScan.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import TIMEOUT_SECONDS, USER_AGENT
from .base import PolicySource

logger = logging.getLogger(__name__)

API_KEY_ENV = "LEGISCAN_API_KEY"
BASE_URL = "https://api.legiscan.com/"
DEFAULT_TERMS = ["waste heat", "district heating", "data center energy"]
DEFAULT_MAX_DOCUMENTS = 25
DEFAULT_MAX_API_CALLS = 40

# Cache of bill_id -> change_hash so unchanged bills are skipped on rerun.
SEEN_FILE = Path("data") / "legiscan_seen.json"

# Persistent per-calendar-month query ledger enforcing the free public
# tier's 30,000-query/month cap (Crash Course). Every actual API call
# counts; the ledger resets when the calendar month changes.
USAGE_FILE = Path("data") / "legiscan_usage.json"
MONTHLY_QUERY_LIMIT = 30000


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load_usage() -> int:
    """Queries spent in the current calendar month (0 after a month rolls over)."""
    if not USAGE_FILE.exists():
        return 0
    try:
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", USAGE_FILE, e)
        return 0
    if data.get("month") != _current_month():
        return 0
    return int(data.get("queries", 0))


def _record_usage(n: int) -> None:
    if n <= 0:
        return
    used = _load_usage() + n
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = USAGE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"month": _current_month(), "queries": used}), encoding="utf-8"
    )
    tmp.replace(USAGE_FILE)


def monthly_usage() -> dict:
    """Report LegiScan query usage for the current month (for monitoring)."""
    used = _load_usage()
    return {
        "month": _current_month(),
        "used": used,
        "remaining": max(0, MONTHLY_QUERY_LIMIT - used),
        "limit": MONTHLY_QUERY_LIMIT,
    }


def _load_seen() -> dict:
    if not SEEN_FILE.exists():
        return {}
    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", SEEN_FILE, e)
        return {}


def _save_seen(seen: dict) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SEEN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen, indent=2), encoding="utf-8")
    tmp.replace(SEEN_FILE)


def _lifecycle_from_bill(bill: dict, last_action: str) -> str:
    text = " ".join(
        str(part) for part in (bill.get("status_text", ""), last_action) if part
    ).lower()
    if any(k in text for k in ("signed", "enacted", "chaptered")):
        return "enacted"
    if "committee" in text:
        return "in_committee"
    if "passed" in text:
        return "passed"
    if "introduced" in text:
        return "proposed"
    return "proposed"


class _CallBudget:
    """Tracks API calls against a per-fetch cap; stops cleanly once spent.

    Also carries a hard stop for API-level errors (e.g. monthly query limit
    exhausted) so the whole run halts instead of spending more queries.
    """

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.calls = 0
        self.halted = False

    def spend(self) -> None:
        self.calls += 1

    def halt(self) -> None:
        self.halted = True

    @property
    def exhausted(self) -> bool:
        return self.halted or self.calls >= self.max_calls


def _status_error(data: object) -> str | None:
    """Return the alert message if the API JSON reports status ERROR.

    LegiScan returns HTTP 200 with {"status":"ERROR", ...} on API errors such
    as an exhausted monthly limit or a bad key, so the Crash Course requires
    checking this field explicitly (HTTP status alone is not enough).
    """
    if not isinstance(data, dict) or data.get("status") != "ERROR":
        return None
    alert = data.get("alert")
    if isinstance(alert, dict):
        return str(alert.get("message", "unknown error"))
    return "unknown error"


@register_source
class LegiscanSource(PolicySource):
    """Fetches US state bills from api.legiscan.com, citing the official state link."""

    id = "legiscan"
    api_key_env = API_KEY_ENV

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            logger.info("source disabled: %s not set", API_KEY_ENV)
            return []

        params = domain.get("source_params", {})
        terms = params.get("terms") or DEFAULT_TERMS
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        max_api_calls = params.get("max_api_calls", DEFAULT_MAX_API_CALLS)

        # Enforce the 30,000-query/month public cap: this run may spend at
        # most whatever is left this calendar month.
        monthly_remaining = MONTHLY_QUERY_LIMIT - _load_usage()
        if monthly_remaining <= 0:
            logger.warning(
                "LegiScan monthly query limit (%d) reached; skipping this run "
                "until the 1st of next month", MONTHLY_QUERY_LIMIT,
            )
            return []
        effective_cap = min(max_api_calls, monthly_remaining)

        seen = _load_seen()
        results: list[CrawlResult] = []
        budget = _CallBudget(effective_cap)

        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}
            ) as client:
                for term in terms:
                    if len(results) >= max_documents or budget.exhausted:
                        break
                    for bill_id, hit in await self._search(client, term, api_key, budget):
                        if len(results) >= max_documents or budget.exhausted:
                            break
                        result = await self._to_crawl_result(
                            client, api_key, bill_id, hit, seen, budget
                        )
                        if result:
                            results.append(result)
        finally:
            _save_seen(seen)
            _record_usage(budget.calls)

        return results

    async def _search(
        self, client: httpx.AsyncClient, term: str, api_key: str, budget: "_CallBudget"
    ) -> list[tuple[int, dict]]:
        try:
            resp = await client.get(
                BASE_URL,
                params={"key": api_key, "op": "getSearchRaw", "state": "ALL", "query": term},
            )
            budget.spend()
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("LegiScan search failed for term %r: %s", term, e)
            return []

        alert = _status_error(data)
        if alert:
            logger.warning("LegiScan API error (stopping run): %s", alert)
            budget.halt()
            return []

        searchresult = data.get("searchresult") if isinstance(data, dict) else None
        if not isinstance(searchresult, dict):
            return []

        hits = []
        for key, hit in searchresult.items():
            if key == "summary" or not isinstance(hit, dict):
                continue
            bill_id = hit.get("bill_id")
            if bill_id is not None:
                hits.append((bill_id, hit))
        return hits

    async def _to_crawl_result(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        bill_id: int,
        hit: dict,
        seen: dict,
        budget: "_CallBudget",
    ) -> CrawlResult | None:
        change_hash = hit.get("change_hash")
        if seen.get(str(bill_id)) == change_hash:
            return None  # unchanged since last run

        try:
            resp = await client.get(
                BASE_URL, params={"key": api_key, "op": "getBill", "id": bill_id}
            )
            budget.spend()
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("LegiScan getBill failed for %s: %s", bill_id, e)
            return None

        alert = _status_error(data)
        if alert:
            logger.warning("LegiScan API error (stopping run): %s", alert)
            budget.halt()
            return None

        bill = data.get("bill") if isinstance(data, dict) else None
        if not isinstance(bill, dict):
            return None
        state_link = bill.get("state_link")
        if not state_link:
            return None  # no official URL to cite -- skip

        title = bill.get("title") or hit.get("title", "")
        description = bill.get("description", "")
        last_action = hit.get("last_action", "")
        content = " ".join(part for part in (title, description, last_action) if part)

        seen[str(bill_id)] = change_hash
        return CrawlResult(
            url=state_link,
            status=PageStatus.SUCCESS,
            content=content,
            title=title,
            lifecycle_stage=_lifecycle_from_bill(bill, last_action),
        )
