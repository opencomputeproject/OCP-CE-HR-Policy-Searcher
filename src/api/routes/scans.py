"""Scan endpoints — start/stop/status + WebSocket progress."""


from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query

from ..deps import get_scan_manager, get_broadcaster, get_policy_store
from ...core.models import ScanRequest
from ...orchestration.events import EventBroadcaster
from ...orchestration.scan_manager import ScanManager
from ...storage.store import PolicyStore

router = APIRouter(prefix="/api", tags=["scans"])


@router.post("/scans")
async def start_scan(
    request: ScanRequest,
    manager: ScanManager = Depends(get_scan_manager),
    store: PolicyStore = Depends(get_policy_store),
):
    """Start a new parallel scan. Returns immediately with scan_id."""
    job = await manager.start_scan(
        domains_group=request.domains,
        max_concurrent=request.max_concurrent,
        skip_llm=request.skip_llm,
        dry_run=request.dry_run,
        category=request.category,
        tags=request.tags,
        policy_type=request.policy_type,
    )
    return {
        "scan_id": job.scan_id,
        "status": job.status.value,
        "domain_count": job.domain_count,
    }


@router.get("/scans")
def list_scans(manager: ScanManager = Depends(get_scan_manager)):
    """List all scans."""
    return [
        {
            "scan_id": job.scan_id,
            "status": job.status.value,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "domain_count": job.domain_count,
            "policy_count": job.policy_count,
        }
        for job in manager.jobs.values()
    ]


@router.get("/scans/{scan_id}")
def get_scan(
    scan_id: str,
    manager: ScanManager = Depends(get_scan_manager),
):
    """Get detailed scan status including per-domain progress."""
    job = manager.jobs.get(scan_id)
    if not job:
        return {"error": f"Scan '{scan_id}' not found"}

    policies = manager.get_policies(scan_id)

    return {
        "scan_id": job.scan_id,
        "status": job.status.value,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "domain_count": job.domain_count,
        "policy_count": job.policy_count,
        "progress": {
            "total": job.progress.total_domains,
            "completed": job.progress.completed_domains,
            "running": job.progress.running_domains,
            "domains": [dp.model_dump() for dp in job.progress.domains],
        },
        "policies": [p.model_dump(mode="json") for p in policies],
        "cost": job.cost.model_dump() if job.cost else None,
        "audit_advisory": job.audit_advisory,
    }


@router.delete("/scans/{scan_id}")
async def cancel_scan(
    scan_id: str,
    manager: ScanManager = Depends(get_scan_manager),
):
    """Cancel a running scan."""
    success = await manager.stop_scan(scan_id)
    if success:
        return {"status": "cancelled", "scan_id": scan_id}
    return {"error": f"Scan '{scan_id}' not running or not found"}


@router.websocket("/api/scans/{scan_id}/ws")
async def scan_websocket(
    websocket: WebSocket,
    scan_id: str,
    broadcaster: EventBroadcaster = Depends(get_broadcaster),
):
    """WebSocket endpoint for real-time scan progress."""
    await broadcaster.connect(scan_id, websocket)
    try:
        while True:
            # Keep connection alive, listen for client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        broadcaster.disconnect(scan_id, websocket)


@router.post("/cost-estimate")
def estimate_cost(
    domains: str = Query("quick"),
    manager: ScanManager = Depends(get_scan_manager),
):
    """Estimate API costs for a scan."""
    return manager.estimate_cost(domains)
