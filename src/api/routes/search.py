"""Place-first search planning endpoint.

Turns "California" + optional topic terms into a reviewable scan plan
(sources, cost ceiling, LegiScan budget, warnings) BEFORE money is spent.
Read-only: the plan itself costs nothing and reveals no secrets, so it is
open like the other read endpoints.
"""

from fastapi import APIRouter, Depends, Query

from ...core.config import ConfigLoader
from ...core.search_plan import build_search_plan
from ..deps import get_config, get_cost_settings_store

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search/plan")
def search_plan(
    place: str = Query(..., min_length=1, max_length=100),
    terms: str = Query("", max_length=500),
    config: ConfigLoader = Depends(get_config),
):
    """Build a scan plan for a place plus optional comma-separated topic terms."""
    term_list = [t.strip() for t in terms.split(",") if t.strip()] or None
    cost_level = get_cost_settings_store().get().cost_level
    return build_search_plan(place, term_list, config, cost_level=cost_level)
