"""Policy CRUD and statistics endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import get_scan_manager, get_policy_store
from ...agent.tools import jurisdiction_matches
from ...orchestration.scan_manager import ScanManager
from ...storage.store import PolicyStore

router = APIRouter(prefix="/api", tags=["policies"])


@router.get("/policies")
def list_policies(
    jurisdiction: Optional[str] = Query(None),
    policy_type: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None, ge=1, le=10),
    scan_id: Optional[str] = Query(None),
    store: PolicyStore = Depends(get_policy_store),
    manager: ScanManager = Depends(get_scan_manager),
):
    """Search policies with optional filters."""
    # Merge stored policies with in-memory scan results
    stored = store.search(
        jurisdiction=jurisdiction,
        policy_type=policy_type,
        min_score=min_score,
        scan_id=scan_id,
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
        in_memory.append(p_dict)

    # Deduplicate by URL
    seen_urls = {p["url"] for p in stored}
    for p in in_memory:
        if p["url"] not in seen_urls:
            stored.append(p)
            seen_urls.add(p["url"])

    return {"policies": stored, "count": len(stored)}


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
