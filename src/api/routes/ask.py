"""Public reader Q&A endpoint.

POST /api/ask is the one natural-language endpoint open to everyone:
readers ask about policies already in the library, a small Haiku-powered
agent answers from stored data only. Spend is bounded three ways:
the reader agent's own tool/iteration caps, a per-IP per-minute rate
limit, and a persisted daily question cap the admin controls.
"""

import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ...agent.ask import answer_question
from ..deps import get_config, get_cost_settings_store, get_scan_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ask"])

USAGE_FILENAME = "ask_usage.json"
RATE_WINDOW_SECONDS = 60.0


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class _AskLimiter:
    """Per-IP sliding window + persisted daily counter."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.usage_file = self.data_dir / USAGE_FILENAME
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._daily_date, self._daily_count = self._load_usage()

    def _load_usage(self) -> tuple[str, int]:
        today = date.today().isoformat()
        if not self.usage_file.exists():
            return today, 0
        try:
            raw = json.loads(self.usage_file.read_text(encoding="utf-8"))
            if raw.get("date") == today:
                return today, int(raw.get("count", 0))
        except Exception as e:
            logger.warning("Could not load ask usage (%s); starting at 0", e)
        return today, 0

    def _save_usage(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.usage_file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"date": self._daily_date, "count": self._daily_count}),
            encoding="utf-8",
        )
        tmp.replace(self.usage_file)

    def _roll_day(self) -> None:
        today = date.today().isoformat()
        if today != self._daily_date:
            self._daily_date = today
            self._daily_count = 0

    def check_rate(self, ip: str, per_minute: int) -> float | None:
        """Return seconds to wait if over the per-minute limit, else None."""
        now = time.monotonic()
        window = self._requests[ip]
        while window and now - window[0] > RATE_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= per_minute:
            return RATE_WINDOW_SECONDS - (now - window[0])
        return None

    def daily_remaining(self, daily_limit: int) -> int:
        self._roll_day()
        return max(0, daily_limit - self._daily_count)

    def record(self, ip: str) -> None:
        self._requests[ip].append(time.monotonic())
        self._roll_day()
        self._daily_count += 1
        self._save_usage()


_limiter: _AskLimiter | None = None


def _get_limiter() -> _AskLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _AskLimiter(os.environ.get("OCP_DATA_DIR", "data"))
    return _limiter


def _client_ip(request) -> str:
    """Best-effort real client IP.

    Behind a reverse proxy (the deployment runs behind Caddy),
    request.client.host is the proxy's address, which would collapse every
    visitor into one rate-limit bucket. Prefer the leftmost X-Forwarded-For
    entry (the original client) when present. A spoofed header can only
    dodge the per-minute burst limit, never the global daily cap, so cost
    stays bounded regardless.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


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
