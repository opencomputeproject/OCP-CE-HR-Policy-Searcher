"""Tip queue endpoints — candidate policies awaiting a chase or dismissal.

User-facing vocabulary is "Tips" (paths below, UI text in LeadsInbox.js);
the storage layer underneath stays LeadStore/Lead (src/storage/leads.py)
per the 2026-07 rename decision — only the public API surface changed.
"""

import logging
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..deps import get_config, get_lead_store, get_policy_store
from ..rate_limit import SlidingWindowLimiter, client_ip as _client_ip
from ...core.config import ConfigLoader
from ...core.url_safety import is_public_http_url
from ...storage.leads import Lead, LeadStore
from ...storage.store import PolicyStore
from .analysis import run_url_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tips"])

TIPS_USAGE_FILENAME = "tips_usage.json"
# Community submissions are unauthenticated and cheap to abuse; these bound
# both a single visitor's burst and the total the queue accepts per day,
# mirroring the /api/ask limiter (see ..rate_limit.SlidingWindowLimiter).
TIPS_RATE_PER_MINUTE = 5
TIPS_DAILY_LIMIT = 100


class TipSubmission(BaseModel):
    url: str = ""
    note: str = ""


class _TipsLimiter(SlidingWindowLimiter):
    def __init__(self, data_dir: str):
        super().__init__(data_dir, TIPS_USAGE_FILENAME)


_limiter: _TipsLimiter | None = None


def _get_limiter() -> _TipsLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _TipsLimiter(os.environ.get("OCP_DATA_DIR", "data"))
    return _limiter


def reset_tip_limits_for_tests(data_dir: str, keep_usage_file: bool = False) -> None:
    """Reinitialize limiter state (unit tests only)."""
    global _limiter
    from pathlib import Path

    if not keep_usage_file:
        usage_file = Path(data_dir) / TIPS_USAGE_FILENAME
        usage_file.unlink(missing_ok=True)
    _limiter = _TipsLimiter(data_dir)


@router.get("/tips")
def list_tips(
    status: str | None = None,
    store: LeadStore = Depends(get_lead_store),
):
    """List tips, newest first, optionally filtered by status."""
    leads = store.list(status=status)
    return {
        "leads": [lead.model_dump(mode="json") for lead in leads],
        "count": len(leads),
    }


@router.post("/tips")
def submit_tip(
    submission: TipSubmission,
    request: Request,
    store: LeadStore = Depends(get_lead_store),
):
    """Community submission: a URL, a note, or both pointing at a policy.

    Rate-limited before any other validation runs — a burst or the daily
    cap is checked first, so an attacker can't use invalid payloads to
    dodge cost bounds.
    """
    limiter = _get_limiter()
    ip = _client_ip(request)

    wait = limiter.check_rate(ip, TIPS_RATE_PER_MINUTE)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many tips submitted at once. Please wait a moment and try again.",
            headers={"Retry-After": str(max(1, int(wait) + 1))},
        )
    if limiter.daily_remaining(TIPS_DAILY_LIMIT) <= 0:
        raise HTTPException(
            status_code=429,
            detail="The daily tip submission limit has been reached. Please try again tomorrow.",
        )
    limiter.record(ip)

    url = submission.url.strip()
    note = submission.note.strip()
    if not url and not note:
        raise HTTPException(
            status_code=422, detail="Provide a URL, a note, or both.",
        )

    # SSRF guard: only accept public http(s) URLs. Blocks localhost,
    # private ranges, and cloud metadata endpoints from entering the
    # queue, so a later chase cannot be steered at internal services.
    # Note-only tips (no url) skip this check entirely.
    if url and not is_public_http_url(url):
        raise HTTPException(
            status_code=422, detail="url must be a public http(s) address"
        )

    lead = Lead(
        title=note[:200] or (urlparse(url).netloc if url else ""),
        source_url=url,
        snippet=note,
        origin="community",
    )
    added = store.add_leads([lead])
    if not added:
        raise HTTPException(status_code=409, detail="This tip has already been submitted")
    return {"lead_id": lead.lead_id, "status": lead.status}


@router.post("/tips/{lead_id}/dismiss")
def dismiss_tip(
    lead_id: str,
    store: LeadStore = Depends(get_lead_store),
):
    lead = store.update_status(lead_id, "dismissed")
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")
    return {"lead_id": lead_id, "status": "dismissed"}


@router.post("/tips/{lead_id}/chase")
async def chase_tip(
    lead_id: str,
    lead_store: LeadStore = Depends(get_lead_store),
    config: ConfigLoader = Depends(get_config),
    policy_store: PolicyStore = Depends(get_policy_store),
):
    """Run the full analysis pipeline against a tip's URL.

    Spends API budget — admin-gated when an admin token is configured.
    """
    lead = lead_store.get(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")

    if not lead.source_url:
        raise HTTPException(
            status_code=400,
            detail="This tip has no URL — it's a note-only submission and can't be chased.",
        )

    # Re-check at fetch time: news leads bypass the submission guard, and a
    # host's address can change between submission and chase.
    if not is_public_http_url(lead.source_url):
        raise HTTPException(
            status_code=400,
            detail="Lead URL is not a public http(s) address; refusing to fetch.",
        )

    try:
        result = await run_url_analysis(lead.source_url, config, policy_store)
    except Exception as e:
        # Some URLs the fetcher cannot process (e.g. news.google.com
        # redirect wrappers) raise instead of returning an unsuccessful
        # crawl result. Report it as a clean chase outcome rather than
        # letting it surface as an unhandled 500 — and don't mark the tip
        # chased, so it stays available to retry.
        logger.error(
            "Chase fetch failed for lead %s (%s): %s: %s",
            lead_id, lead.source_url, type(e).__name__, e,
        )
        lead_store.record_chase(
            lead_id, outcome="fetch_failed", mark_chased=False, error=str(e),
        )
        return {
            "lead_id": lead_id,
            "status": "new",
            "analysis": {"policy": None, "outcome": "fetch_failed", "error": str(e)},
        }

    policy_url = None
    if result.get("policy"):
        policy_url = result["policy"].get("url")
    outcome = "policy_found" if policy_url else "no_policy"
    lead_store.record_chase(lead_id, outcome=outcome, mark_chased=True, policy_url=policy_url)

    return {"lead_id": lead_id, "status": "chased", "analysis": result}
