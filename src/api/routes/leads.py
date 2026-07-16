"""Lead queue endpoints — candidate policies awaiting a chase or dismissal."""

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_config, get_lead_store, get_policy_store
from ...core.config import ConfigLoader
from ...core.url_safety import is_public_http_url
from ...storage.leads import Lead, LeadStore
from ...storage.store import PolicyStore
from .analysis import run_url_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["leads"])


class LeadSubmission(BaseModel):
    url: str
    note: str = ""


@router.get("/leads")
def list_leads(
    status: str | None = None,
    store: LeadStore = Depends(get_lead_store),
):
    """List leads, newest first, optionally filtered by status."""
    leads = store.list(status=status)
    return {
        "leads": [lead.model_dump(mode="json") for lead in leads],
        "count": len(leads),
    }


@router.post("/leads")
def submit_lead(
    submission: LeadSubmission,
    store: LeadStore = Depends(get_lead_store),
):
    """Community submission: a URL someone believes points at a policy."""
    # SSRF guard: only accept public http(s) URLs. Blocks localhost,
    # private ranges, and cloud metadata endpoints from entering the
    # queue, so a later chase cannot be steered at internal services.
    if not is_public_http_url(submission.url):
        raise HTTPException(
            status_code=422, detail="url must be a public http(s) address"
        )

    lead = Lead(
        title=submission.note[:200] or urlparse(submission.url).netloc,
        source_url=submission.url,
        snippet=submission.note,
        origin="community",
    )
    added = store.add_leads([lead])
    if not added:
        raise HTTPException(status_code=409, detail="URL already submitted")
    return {"lead_id": lead.lead_id, "status": lead.status}


@router.post("/leads/{lead_id}/dismiss")
def dismiss_lead(
    lead_id: str,
    store: LeadStore = Depends(get_lead_store),
):
    lead = store.update_status(lead_id, "dismissed")
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")
    return {"lead_id": lead_id, "status": "dismissed"}


@router.post("/leads/{lead_id}/chase")
async def chase_lead(
    lead_id: str,
    lead_store: LeadStore = Depends(get_lead_store),
    config: ConfigLoader = Depends(get_config),
    policy_store: PolicyStore = Depends(get_policy_store),
):
    """Run the full analysis pipeline against a lead's URL.

    Spends API budget — admin-gated when an admin token is configured.
    """
    lead = lead_store.get(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")

    # Re-check at fetch time: news leads bypass the submission guard, and a
    # host's address can change between submission and chase.
    if not is_public_http_url(lead.source_url):
        raise HTTPException(
            status_code=400,
            detail="Lead URL is not a public http(s) address; refusing to fetch.",
        )

    result = await run_url_analysis(lead.source_url, config, policy_store)

    policy_url = None
    if result.get("policy"):
        policy_url = result["policy"].get("url")
    lead_store.update_status(lead_id, "chased", policy_url=policy_url)

    return {"lead_id": lead_id, "status": "chased", "analysis": result}
