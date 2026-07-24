"""Public reader Q&A endpoint.

POST /api/ask is the one natural-language endpoint open to everyone:
readers ask about policies already in the library, a small Haiku-powered
agent answers from stored data only. Spend is bounded three ways:
the reader agent's own tool/iteration caps, a per-IP per-minute rate
limit, and a persisted daily question cap the admin controls.
"""

import logging
import os
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ...agent.ask import answer_question
from ..deps import get_config, get_cost_settings_store, get_scan_manager
from ..rate_limit import SlidingWindowLimiter, client_ip as _client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ask"])

USAGE_FILENAME = "ask_usage.json"


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class _AskLimiter(SlidingWindowLimiter):
    def __init__(self, data_dir: str):
        super().__init__(data_dir, USAGE_FILENAME)


_limiter: _AskLimiter | None = None


def _get_limiter() -> _AskLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _AskLimiter(os.environ.get("OCP_DATA_DIR", "data"))
    return _limiter


def reset_limits_for_tests(data_dir: str, keep_usage_file: bool = False) -> None:
    """Reinitialize limiter state (unit tests only)."""
    global _limiter
    if not keep_usage_file:
        usage_file = Path(data_dir) / USAGE_FILENAME
        usage_file.unlink(missing_ok=True)
    _limiter = _AskLimiter(data_dir)


@router.post("/ask")
async def ask(
    payload: AskRequest,
    request: Request,
    response: Response,
    config=Depends(get_config),
    scan_manager=Depends(get_scan_manager),
    cost_store=Depends(get_cost_settings_store),
):
    """Answer a reader's natural language question from stored policies."""
    settings = cost_store.get()
    if not settings.ask_enabled:
        raise HTTPException(
            status_code=503,
            detail="Questions are temporarily disabled by the administrator.",
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="The question service is not configured yet.",
        )

    limiter = _get_limiter()
    ip = _client_ip(request)

    wait = limiter.check_rate(ip, settings.ask_rate_per_minute)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many questions at once. Please wait a moment and try again.",
            headers={"Retry-After": str(max(1, int(wait) + 1))},
        )

    if limiter.daily_remaining(settings.ask_daily_limit) <= 0:
        raise HTTPException(
            status_code=429,
            detail=(
                "The daily question limit has been reached. "
                "Please come back tomorrow, or browse the policy list below."
            ),
        )

    limiter.record(ip)

    model = cost_store.resolved_models()["ask_model"]
    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        result = await answer_question(
            payload.question,
            client=client,
            model=model,
            config=config,
            scan_manager=scan_manager,
        )
    except Exception as e:
        logger.error("Ask failed: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong answering your question. Please try again.",
        ) from e
    finally:
        await client.close()

    return {
        "answer": result["answer"],
        "tool_calls": result["tool_calls"],
        "remaining_today": limiter.daily_remaining(settings.ask_daily_limit),
    }
