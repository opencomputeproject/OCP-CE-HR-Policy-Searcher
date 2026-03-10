"""Unified logging configuration for OCP Policy Hub.

Provides structured logging via ``structlog`` on top of Python's stdlib
``logging``.  All existing ``logging.getLogger(__name__)`` calls throughout
the codebase continue to work unchanged — structlog is configured as the
formatter/processor layer, not a replacement for the stdlib API.

Features
--------
- **JSON file logs** — machine-parseable, grep-friendly, one JSON object
  per line in ``data/logs/agent.log``.
- **Human-readable console** — colored, concise output for interactive use
  (WARNING+ only so it doesn't clutter the CLI UI).
- **Crash-safe flush** — the file handler flushes after every emit, and an
  ``atexit`` handler ensures clean shutdown.
- **Correlation IDs** — ``structlog.contextvars`` propagates ``scan_id``,
  ``domain_id``, and ``request_id`` through async tasks automatically.
- **Sensitive data redaction** — API keys and tokens are stripped from log
  output before it reaches any handler.
- **Separate audit log** — critical events (scan start/complete, policy
  found, cost) are appended to ``data/logs/audit.jsonl`` with ``os.fsync``
  for guaranteed persistence.

Usage
-----
::

    from src.core.log_setup import setup_logging, log_audit_event

    # At application startup (CLI or API):
    log_file = setup_logging(data_dir="data")

    # In scan workers, bind context so every subsequent log includes it:
    import structlog
    structlog.contextvars.bind_contextvars(scan_id="abc123", domain_id="de_bmwk")
    logger.info("page_crawled", url="https://...", status=200)
    # → {"scan_id": "abc123", "domain_id": "de_bmwk", "event": "page_crawled", ...}

    # For critical events that MUST survive crashes:
    log_audit_event(data_dir="data", event="policy_found", policy_name="EnEfG", ...)
"""

import atexit
import json
import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rotation limits: 10 MB per file, keep 5 backups → 60 MB max disk usage.
# A deep scan of 40+ domains generates substantial log output; 15 MB (the
# old default) could rotate away useful context mid-scan.
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5

# Libraries that flood DEBUG/INFO with HTTP traffic details.
_NOISY_LIBRARIES = ("httpx", "httpcore", "anthropic", "urllib3", "asyncio")

# Patterns that should never appear in log output.
_SENSITIVE_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9_-]+"),       # Anthropic API keys
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),        # Generic API keys
    re.compile(r"eyJ[a-zA-Z0-9_-]+\.eyJ"),       # JWT tokens (base64-encoded)
    re.compile(r"AIza[a-zA-Z0-9_-]{30,}"),       # Google API keys
]


# ---------------------------------------------------------------------------
# Flush-on-write handler (crash-safe)
# ---------------------------------------------------------------------------

class FlushingRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that flushes the stream after every write.

    Python's default logging buffers output.  If the process crashes (OOM,
    segfault, power loss) the last several messages — often the most useful
    for debugging — are lost.  This handler calls ``flush()`` after each
    ``emit()`` to guarantee every log line reaches the OS buffer immediately.

    The performance cost (one extra syscall per log message) is negligible
    for OCP Policy Hub's workload (~hundreds of messages per scan).
    """

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


# ---------------------------------------------------------------------------
# structlog processors
# ---------------------------------------------------------------------------

def _redact_sensitive(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Strip API keys, tokens, and credentials from all log values.

    Runs as a structlog processor — every log message passes through this
    before reaching any handler.  Only string values are checked; nested
    dicts/lists are left alone (log values should be flat scalars).
    """
    for key, value in event_dict.items():
        if isinstance(value, str):
            for pattern in _SENSITIVE_PATTERNS:
                value = pattern.sub("[REDACTED]", value)
            event_dict[key] = value
    return event_dict


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(
    data_dir: str = "data",
    *,
    json_console: bool = False,
    console_level: int = logging.WARNING,
) -> Path:
    """Configure structured logging for the entire application.

    Call this once at startup — both the CLI entry point
    (``src.agent.__main__``) and the FastAPI app (``src.api.app``) should
    use the same function so log format and handlers are consistent.

    File output is always JSON (one object per line).  Console output is
    human-readable by default (for interactive CLI), but can be switched
    to JSON for production/API mode via *json_console*.

    Args:
        data_dir:      Base directory.  Logs go to ``{data_dir}/logs/``.
        json_console:  If ``True``, console output is JSON instead of
                       colored human-readable text.
        console_level: Minimum level for console output.  Defaults to
                       ``WARNING`` so interactive mode isn't cluttered.

    Returns:
        Path to the active log file (``{data_dir}/logs/agent.log``).
    """
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"

    # ── stdlib handlers ──────────────────────────────────────────────

    # File handler: JSON format, flush-on-write for crash safety
    file_handler = FlushingRotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    # Console handler: human-readable (or JSON), WARNING+ by default
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)

    # Root logger — clear any previous handlers (e.g. basicConfig in app.py)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Silence noisy libraries
    for lib in _NOISY_LIBRARIES:
        logging.getLogger(lib).setLevel(logging.WARNING)

    # ── structlog configuration ──────────────────────────────────────

    # Shared processors run for both stdlib-originated and structlog-
    # originated log messages.
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,    # async-safe context
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _redact_sensitive,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # File formatter: always JSON — machine-parseable, one object per line
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
    )

    # Console formatter: human-readable by default, JSON if requested
    if json_console:
        console_renderer = structlog.processors.JSONRenderer()
    else:
        console_renderer = structlog.dev.ConsoleRenderer()

    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=console_renderer,
            foreign_pre_chain=shared_processors,
        )
    )

    # ── atexit flush ─────────────────────────────────────────────────

    def _flush_all() -> None:
        for handler in logging.root.handlers:
            try:
                handler.flush()
            except Exception:
                pass  # best-effort on shutdown

    atexit.register(_flush_all)

    return log_file


def log_audit_event(data_dir: str = "data", **fields: Any) -> None:
    """Append a single JSON line to the audit log with crash-safe fsync.

    The audit log (``data/logs/audit.jsonl``) is a separate, append-only
    file for critical events that must survive crashes: scan start/complete,
    policy discoveries, cost summaries.  Each line is one JSON object.

    Unlike the regular log (which uses buffered rotation), this function
    calls ``os.fsync()`` to force the OS to write data to the physical
    disk before returning.

    Args:
        data_dir:  Base data directory.
        **fields:  Arbitrary key-value pairs to include in the event.
                   An ``"event"`` key is recommended for easy filtering.

    Example::

        log_audit_event(
            data_dir="data",
            event="policy_found",
            scan_id="abc123",
            domain_id="de_bmwk",
            policy_name="EnEfG",
            relevance=9,
        )
    """
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    audit_file = log_dir / "audit.jsonl"

    # Add ISO timestamp
    from datetime import datetime, timezone

    fields["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Redact sensitive values
    for key, value in fields.items():
        if isinstance(value, str):
            for pattern in _SENSITIVE_PATTERNS:
                value = pattern.sub("[REDACTED]", value)
            fields[key] = value

    line = json.dumps(fields, default=str) + "\n"
    try:
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())  # Force to disk
    except OSError:
        # Best-effort — don't crash the scan because audit logging failed
        logging.getLogger(__name__).error(
            "Failed to write audit event", exc_info=True,
        )
