"""Shared per-IP rate limiting: sliding-window burst limit + persisted daily cap.

Extracted from the original /api/ask limiter (src/api/routes/ask.py) so
/api/tips can bound community submissions the same way without
duplicating the window/persistence bookkeeping.
"""

import json
import logging
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

RATE_WINDOW_SECONDS = 60.0


def client_ip(request) -> str:
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


class SlidingWindowLimiter:
    """Per-IP sliding window + persisted daily counter.

    Subclassed per endpoint (see ``_AskLimiter`` / ``_TipsLimiter``) so each
    gets its own usage file, while sharing the window/persistence logic.
    """

    def __init__(self, data_dir: str, usage_filename: str):
        self.data_dir = Path(data_dir)
        self.usage_file = self.data_dir / usage_filename
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
            logger.warning("Could not load usage from %s (%s); starting at 0", self.usage_file, e)
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
