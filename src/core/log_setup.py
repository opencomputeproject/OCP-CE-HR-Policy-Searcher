"""Unified logging configuration for OCP CE HR Policy Searcher.

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
- **Session IDs** — each process gets a unique ``session_id`` so
  concurrent agents (multiple API workers, parallel CLI runs) can be
  distinguished in the same log file.
- **Correlation IDs** — ``structlog.contextvars`` propagates ``scan_id``,
  ``domain_id``, and ``request_id`` through async tasks automatically.
- **Sensitive data redaction** — API keys and tokens are stripped from log
  output before it reaches any handler.
- **Separate audit log** — critical events (scan start/complete, policy
  found, cost) are appended to ``data/logs/audit.jsonl`` with ``os.fsync``
  for guaranteed persistence.
- **Log reader** — ``read_logs()`` and ``read_audit_log()`` provide
  filtered, paginated access for the CLI viewer and REST API.

Usage
-----
::

    from src.core.log_setup import setup_logging, log_audit_event, read_logs

    # At application startup (CLI or API):
    log_file = setup_logging(data_dir="data")

    # In scan workers, bind context so every subsequent log includes it:
    import structlog
    structlog.contextvars.bind_contextvars(scan_id="abc123", domain_id="de_bmwk")
    logger.info("page_crawled", url="https://...", status=200)
    # → {"scan_id": "abc123", "domain_id": "de_bmwk", "event": "page_crawled", ...}

    # For critical events that MUST survive crashes:
    log_audit_event(data_dir="data", event="policy_found", policy_name="EnEfG", ...)

    # Read recent logs (for CLI viewer or API endpoint):
    entries = read_logs(data_dir="data", lines=50, level="warning")
"""

import atexit
import json
import logging
import logging.handlers
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

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

# Unique session ID for this process.  When multiple agents or API workers
# run concurrently, each writes to the same log file — the session_id lets
# you filter to just one session's messages.
SESSION_ID = str(uuid.uuid4())[:8]

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
    for OCP CE HR Policy Searcher's workload (~hundreds of messages per scan).
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

    # ── session tracking ─────────────────────────────────────────────

    # Bind session_id so every log message identifies which process wrote
    # it.  This is critical when multiple agents or API workers share the
    # same log file.
    structlog.contextvars.bind_contextvars(session_id=SESSION_ID)

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


# ---------------------------------------------------------------------------
# Log readers — for CLI viewer and API endpoints
# ---------------------------------------------------------------------------

_LEVEL_PRIORITY = {
    "debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4,
}


def read_logs(
    data_dir: str = "data",
    *,
    lines: int = 50,
    level: Optional[str] = None,
    scan_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Read recent entries from the structured log file.

    Parses the JSON-lines log file and returns the most recent entries,
    optionally filtered by level, scan_id, or session_id.  Used by the
    ``--logs`` CLI command and the ``GET /api/logs`` endpoint.

    Args:
        data_dir:    Base data directory (logs are in ``{data_dir}/logs/``).
        lines:       Maximum number of entries to return.
        level:       Minimum log level (``"debug"``, ``"info"``, ``"warning"``,
                     ``"error"``).  Case-insensitive.
        scan_id:     Only include entries with this scan_id.
        session_id:  Only include entries from this session.

    Returns:
        List of log entry dicts, newest first.
    """
    log_file = Path(data_dir) / "logs" / "agent.log"
    if not log_file.exists():
        return []

    min_level = _LEVEL_PRIORITY.get((level or "debug").lower(), 0)
    entries: list[dict[str, Any]] = []

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()
    except OSError:
        return []

    # Walk backwards through the file for efficiency (newest first)
    for raw_line in reversed(raw_lines):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        # Filter by level
        entry_level = _LEVEL_PRIORITY.get(
            entry.get("level", "debug").lower(), 0,
        )
        if entry_level < min_level:
            continue

        # Filter by scan_id
        if scan_id and entry.get("scan_id") != scan_id:
            continue

        # Filter by session_id
        if session_id and entry.get("session_id") != session_id:
            continue

        entries.append(entry)
        if len(entries) >= lines:
            break

    return entries


def read_audit_log(
    data_dir: str = "data",
    *,
    lines: int = 50,
    event_type: Optional[str] = None,
    scan_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Read recent entries from the crash-safe audit log.

    Args:
        data_dir:    Base data directory.
        lines:       Maximum number of entries to return.
        event_type:  Only include events of this type (e.g. ``"policy_found"``).
        scan_id:     Only include events for this scan.

    Returns:
        List of audit event dicts, newest first.
    """
    audit_file = Path(data_dir) / "logs" / "audit.jsonl"
    if not audit_file.exists():
        return []

    entries: list[dict[str, Any]] = []

    try:
        with open(audit_file, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()
    except OSError:
        return []

    for raw_line in reversed(raw_lines):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        if event_type and entry.get("event") != event_type:
            continue
        if scan_id and entry.get("scan_id") != scan_id:
            continue

        entries.append(entry)
        if len(entries) >= lines:
            break

    return entries


def get_log_file_paths(data_dir: str = "data") -> dict[str, Optional[str]]:
    """Return paths to log files, or None if they don't exist.

    Useful for showing users where to find logs and for the API to
    report log file locations.

    Returns:
        Dict with ``"agent_log"`` and ``"audit_log"`` keys.
    """
    log_dir = Path(data_dir) / "logs"
    agent_log = log_dir / "agent.log"
    audit_log = log_dir / "audit.jsonl"

    return {
        "agent_log": str(agent_log) if agent_log.exists() else None,
        "audit_log": str(audit_log) if audit_log.exists() else None,
        "log_directory": str(log_dir),
    }
