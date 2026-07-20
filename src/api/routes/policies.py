"""Policy CRUD, review workflow, and statistics endpoints."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_scan_manager, get_policy_store
from ...agent.tools import jurisdiction_matches
from ...core import jurisdictions
from ...orchestration.scan_manager import ScanManager
from ...storage.store import PolicyStore

router = APIRouter(prefix="/api", tags=["policies"])


def _matches_place(place: "jurisdictions.Jurisdiction", jurisdiction_text: Optional[str]) -> bool:
    """Whether a policy's free-text jurisdiction rolls up to ``place``.

    Equality on the resolved slug covers subnational/supranational exactness
    (place=california or place=eu match only themselves); the ``country_of``
    check adds descendant-inclusion for a country place (place=us also
    matches every US state).
    """
    jur = jurisdictions.resolve_text(jurisdiction_text)
    if jur is None:
        return False
    if jur.slug == place.slug:
        return True
    country = jurisdictions.country_of(jur)
    return country is not None and country.slug == place.slug


@router.get("/policies")
def list_policies(
    jurisdiction: Optional[str] = Query(None),
    policy_type: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None, ge=1, le=10),
    scan_id: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    place: Optional[str] = Query(None),
    store: PolicyStore = Depends(get_policy_store),
    manager: ScanManager = Depends(get_scan_manager),
):
    """Search policies with optional filters.

    ``place`` is a jurisdiction-registry slug (see ``src/core/jurisdictions.py``)
    and composes with the other filters. Country slugs are descendant-inclusive
    (place=us also returns federal + every US state policy); subnational and
    supranational slugs match exactly.
    """
    place_jur = None
    if place is not None:
        place_jur = jurisdictions.get(place)
        if place_jur is None:
            raise HTTPException(status_code=404, detail=f"Unknown place '{place}'")

    # Merge stored policies with in-memory scan results
    stored = store.search(
        jurisdiction=jurisdiction,
        policy_type=policy_type,
        min_score=min_score,
        scan_id=scan_id,
        review_status=review_status,
    )

    # Also include in-memory policies from recent scans
    in_memory = []
    for policy in manager.get_all_policies():
        p_dict = policy.model_dump(mode="json")
        if jurisdiction and not jurisdiction_matches(jurisdiction, p_dict.get("jurisdiction", "")):
            continue
        if policy_type and p_dict.get("policy_type") != policy_type:
            continue
        if min_score and (p_dict.get("relevance_score", 0) or 0) < min_score:
            continue
        if scan_id and p_dict.get("scan_id") != scan_id:
            continue
        if review_status and p_dict.get("review_status", "new") != review_status:
            continue
        in_memory.append(p_dict)

    # Deduplicate by URL
    seen_urls = {p["url"] for p in stored}
    for p in in_memory:
        if p["url"] not in seen_urls:
            stored.append(p)
            seen_urls.add(p["url"])

    if place_jur is not None:
        stored = [p for p in stored if _matches_place(place_jur, p.get("jurisdiction"))]

    return {"policies": stored, "count": len(stored)}


class ReviewUpdate(BaseModel):
    url: str
    review_status: Literal["new", "reviewed", "promoted", "rejected"]


@router.patch("/policies/review")
def update_review_status(
    update: ReviewUpdate,
    store: PolicyStore = Depends(get_policy_store),
    manager: ScanManager = Depends(get_scan_manager),
):
    """Set a policy's review status (admin action via the gate middleware)."""
    updated = store.update_review_status(update.url, update.review_status)

    # Policies also live in ScanManager's in-memory results for the life of
    # the process; without this, a reviewed policy resurrects in the "new"
    # queue on the next list merge.
    for policy in manager.get_all_policies():
        if policy.url == update.url:
            policy.review_status = update.review_status
            updated = True

    if not updated:
        raise HTTPException(
            status_code=404, detail=f"No policy with URL: {update.url}",
        )
    return {"url": update.url, "review_status": update.review_status}


@router.get("/policies/stats")
def policy_stats(
    store: PolicyStore = Depends(get_policy_store),
    manager: ScanManager = Depends(get_scan_manager),
):
    """Get aggregate policy statistics."""
    stats = store.get_stats()

    # Add in-memory counts
    in_memory = manager.get_all_policies()
    stats["in_memory_count"] = len(in_memory)

    return stats
