"""Tests for the unified logging system (log_setup.py) and log API endpoints.

Covers:
- Log file creation and rotation setup
- JSON-lines file output format
- Sensitive data redaction (API keys, JWTs, Google keys)
- Crash-safe audit log (fsync, append-only)
- Log readers (read_logs, read_audit_log) with filtering
- Log file path reporting
- Session ID generation and binding
- CLI log viewer (--logs flag)
- API log endpoints (/api/logs, /api/logs/audit, /api/logs/info)
"""

import json
import logging
import logging.handlers

import pytest

from src.core.log_setup import (
    SESSION_ID,
    FlushingRotatingFileHandler,
    get_log_file_paths,
    log_audit_event,
    read_audit_log,
    read_logs,
    setup_logging,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_handlers():
    """Remove all handlers from root logger to avoid test interference."""
    root = logging.getLogger()
    for handler in root.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)


def _write_log_lines(log_file, entries: list[dict]):
    """Write pre-built JSON log entries to a file for testing readers."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Session ID
# ---------------------------------------------------------------------------

@pytest.mark.small
class TestSessionID:
    """Test that a unique session ID is generated per process."""

    def test_session_id_is_string(self):
        assert isinstance(SESSION_ID, str)

    def test_session_id_length(self):
        """Session ID is the first 8 chars of a UUID4."""
        assert len(SESSION_ID) == 8

    def test_session_id_is_hex_like(self):
        """Session ID should be alphanumeric (hex chars + hyphens from UUID)."""
        assert all(c in "0123456789abcdef-" for c in SESSION_ID)


# ---------------------------------------------------------------------------
# FlushingRotatingFileHandler
# ---------------------------------------------------------------------------

class TestFlushingHandler:
    """Test the crash-safe flushing file handler."""

    @pytest.mark.small
    def test_inherits_rotating_handler(self):
        assert issubclass(FlushingRotatingFileHandler, logging.handlers.RotatingFileHandler)

    @pytest.mark.medium
    def test_flush_on_emit(self, tmp_path):
        """Handler should flush after each emit for crash safety."""
        log_file = tmp_path / "test.log"
        handler = FlushingRotatingFileHandler(
            log_file, maxBytes=1024 * 1024, backupCount=1, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="crash-safe test", args=(), exc_info=None,
        )
        handler.emit(record)

        # File should contain the message immediately (no buffering)
        content = log_file.read_text(encoding="utf-8")
        assert "crash-safe test" in content
        handler.close()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

@pytest.mark.medium
class TestSetupLogging:
    """Test the unified logging configuration."""

    def test_creates_log_directory(self, tmp_path):
        """setup_logging should create the logs/ subdirectory."""
        log_dir = tmp_path / "nested" / "path"
        setup_logging(str(log_dir))
        assert (log_dir / "logs").exists()
        _cleanup_handlers()

    def test_returns_log_file_path(self, tmp_path):
        log_file = setup_logging(str(tmp_path))
        assert log_file.name == "agent.log"
        assert log_file.parent.exists()
        _cleanup_handlers()

    def test_file_handler_writes_json(self, tmp_path):
        """Log file output should be JSON-lines format."""
        log_file = setup_logging(str(tmp_path))
        test_logger = logging.getLogger("test_json_format")
        test_logger.warning("test json output")

        content = log_file.read_text(encoding="utf-8").strip()
        if content:
            for line in content.splitlines():
                parsed = json.loads(line)
                assert "event" in parsed
                assert "level" in parsed
        _cleanup_handlers()

    def test_console_handler_at_warning(self, tmp_path):
        """Console handler should be at WARNING level by default."""
        setup_logging(str(tmp_path))
        root = logging.getLogger()
        console_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)
                            and not isinstance(h, logging.FileHandler)]
        assert any(h.level >= logging.WARNING for h in console_handlers)
        _cleanup_handlers()

    def test_noisy_libraries_silenced(self, tmp_path):
        """httpx, httpcore, etc. should be at WARNING level."""
        setup_logging(str(tmp_path))
        for lib in ("httpx", "httpcore", "anthropic", "urllib3", "asyncio"):
            assert logging.getLogger(lib).level >= logging.WARNING
        _cleanup_handlers()


# ---------------------------------------------------------------------------
# Sensitive data redaction
# ---------------------------------------------------------------------------

@pytest.mark.medium
class TestRedaction:
    """Test that API keys and tokens are stripped from log output."""

    def test_anthropic_key_redacted(self, tmp_path):
        log_file = setup_logging(str(tmp_path))
        logger = logging.getLogger("test_redact_anthropic")
        logger.warning("Key is sk-ant-abc123xyz-very-long-key-value")

        content = log_file.read_text(encoding="utf-8")
        assert "sk-ant-abc123xyz" not in content
        assert "[REDACTED]" in content
        _cleanup_handlers()

    def test_generic_sk_key_redacted(self, tmp_path):
        log_file = setup_logging(str(tmp_path))
        logger = logging.getLogger("test_redact_generic")
        logger.warning("sk-1234567890abcdefghij1234567890")

        content = log_file.read_text(encoding="utf-8")
        assert "sk-12345678" not in content
        _cleanup_handlers()

    def test_jwt_redacted(self, tmp_path):
        log_file = setup_logging(str(tmp_path))
        logger = logging.getLogger("test_redact_jwt")
        logger.warning("Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.secret")

        content = log_file.read_text(encoding="utf-8")
        assert "eyJhbGciOiJIUzI1NiJ9.eyJ" not in content
        _cleanup_handlers()

    def test_google_key_redacted(self, tmp_path):
        log_file = setup_logging(str(tmp_path))
        logger = logging.getLogger("test_redact_google")
        logger.warning("AIzaSyA1234567890abcdefghijklmnopqrstuvwx")

        content = log_file.read_text(encoding="utf-8")
        assert "AIzaSyA12345" not in content
        _cleanup_handlers()

    def test_normal_text_not_redacted(self, tmp_path):
        """Non-sensitive text should pass through unchanged."""
        log_file = setup_logging(str(tmp_path))
        logger = logging.getLogger("test_no_redact")
        logger.warning("Normal scan message about domain bmwk_de")

        content = log_file.read_text(encoding="utf-8")
        assert "bmwk_de" in content
        _cleanup_handlers()


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@pytest.mark.medium
class TestAuditLog:
    """Test the crash-safe audit log (audit.jsonl)."""

    def test_creates_audit_file(self, tmp_path):
        log_audit_event(data_dir=str(tmp_path), event="test_event", scan_id="abc")
        audit_file = tmp_path / "logs" / "audit.jsonl"
        assert audit_file.exists()

    def test_appends_not_overwrites(self, tmp_path):
        log_audit_event(data_dir=str(tmp_path), event="first")
        log_audit_event(data_dir=str(tmp_path), event="second")
        log_audit_event(data_dir=str(tmp_path), event="third")

        audit_file = tmp_path / "logs" / "audit.jsonl"
        lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    def test_includes_timestamp(self, tmp_path):
        log_audit_event(data_dir=str(tmp_path), event="timestamped")
        audit_file = tmp_path / "logs" / "audit.jsonl"
        data = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert "timestamp" in data

    def test_preserves_fields(self, tmp_path):
        log_audit_event(
            data_dir=str(tmp_path),
            event="policy_found",
            scan_id="abc123",
            domain_id="de_bmwk",
            policy_name="EnEfG",
            relevance=9,
        )
        audit_file = tmp_path / "logs" / "audit.jsonl"
        data = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert data["event"] == "policy_found"
        assert data["scan_id"] == "abc123"
        assert data["policy_name"] == "EnEfG"
        assert data["relevance"] == 9

    def test_redacts_api_keys(self, tmp_path):
        log_audit_event(
            data_dir=str(tmp_path),
            event="test",
            api_key="sk-ant-secret-key-value-here",
        )
        audit_file = tmp_path / "logs" / "audit.jsonl"
        content = audit_file.read_text(encoding="utf-8")
        assert "sk-ant-secret" not in content
        assert "[REDACTED]" in content


# ---------------------------------------------------------------------------
# Log readers
# ---------------------------------------------------------------------------

@pytest.mark.medium
class TestReadLogs:
    """Test the read_logs() function for the CLI viewer and API."""

    def test_returns_empty_when_no_file(self, tmp_path):
        entries = read_logs(str(tmp_path))
        assert entries == []

    def test_reads_entries_newest_first(self, tmp_path):
        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "first", "level": "info", "timestamp": "2024-01-01T00:00:00"},
            {"event": "second", "level": "info", "timestamp": "2024-01-01T00:01:00"},
            {"event": "third", "level": "info", "timestamp": "2024-01-01T00:02:00"},
        ])

        entries = read_logs(str(tmp_path), lines=10)
        assert len(entries) == 3
        # Newest first (reversed order)
        assert entries[0]["event"] == "third"
        assert entries[2]["event"] == "first"

    def test_limits_returned_entries(self, tmp_path):
        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": f"entry_{i}", "level": "info"} for i in range(100)
        ])

        entries = read_logs(str(tmp_path), lines=5)
        assert len(entries) == 5

    def test_filters_by_level(self, tmp_path):
        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "debug_msg", "level": "debug"},
            {"event": "info_msg", "level": "info"},
            {"event": "warning_msg", "level": "warning"},
            {"event": "error_msg", "level": "error"},
        ])

        entries = read_logs(str(tmp_path), level="warning")
        assert len(entries) == 2
        events = {e["event"] for e in entries}
        assert "warning_msg" in events
        assert "error_msg" in events
        assert "info_msg" not in events

    def test_filters_by_scan_id(self, tmp_path):
        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "scan_a", "level": "info", "scan_id": "aaa"},
            {"event": "scan_b", "level": "info", "scan_id": "bbb"},
            {"event": "scan_a2", "level": "info", "scan_id": "aaa"},
        ])

        entries = read_logs(str(tmp_path), scan_id="aaa")
        assert len(entries) == 2
        assert all(e["scan_id"] == "aaa" for e in entries)

    def test_filters_by_session_id(self, tmp_path):
        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "sess_x", "level": "info", "session_id": "xxx"},
            {"event": "sess_y", "level": "info", "session_id": "yyy"},
        ])

        entries = read_logs(str(tmp_path), session_id="xxx")
        assert len(entries) == 1
        assert entries[0]["session_id"] == "xxx"

    def test_skips_malformed_lines(self, tmp_path):
        """Corrupt log lines should be skipped, not crash the reader."""
        log_file = tmp_path / "logs" / "agent.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w", encoding="utf-8") as f:
            f.write('{"event": "good", "level": "info"}\n')
            f.write("THIS IS NOT JSON\n")
            f.write('{"event": "also_good", "level": "info"}\n')

        entries = read_logs(str(tmp_path))
        assert len(entries) == 2

    def test_skips_empty_lines(self, tmp_path):
        log_file = tmp_path / "logs" / "agent.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w", encoding="utf-8") as f:
            f.write('{"event": "one", "level": "info"}\n')
            f.write("\n")
            f.write("\n")
            f.write('{"event": "two", "level": "info"}\n')

        entries = read_logs(str(tmp_path))
        assert len(entries) == 2


@pytest.mark.medium
class TestReadAuditLog:
    """Test the read_audit_log() function."""

    def test_returns_empty_when_no_file(self, tmp_path):
        entries = read_audit_log(str(tmp_path))
        assert entries == []

    def test_filters_by_event_type(self, tmp_path):
        log_audit_event(data_dir=str(tmp_path), event="scan_started", scan_id="a")
        log_audit_event(data_dir=str(tmp_path), event="policy_found", scan_id="a")
        log_audit_event(data_dir=str(tmp_path), event="scan_completed", scan_id="a")

        entries = read_audit_log(str(tmp_path), event_type="policy_found")
        assert len(entries) == 1
        assert entries[0]["event"] == "policy_found"

    def test_filters_by_scan_id(self, tmp_path):
        log_audit_event(data_dir=str(tmp_path), event="scan_started", scan_id="scan1")
        log_audit_event(data_dir=str(tmp_path), event="scan_started", scan_id="scan2")

        entries = read_audit_log(str(tmp_path), scan_id="scan1")
        assert len(entries) == 1
        assert entries[0]["scan_id"] == "scan1"

    def test_returns_newest_first(self, tmp_path):
        log_audit_event(data_dir=str(tmp_path), event="first")
        log_audit_event(data_dir=str(tmp_path), event="second")
        log_audit_event(data_dir=str(tmp_path), event="third")

        entries = read_audit_log(str(tmp_path))
        assert entries[0]["event"] == "third"
        assert entries[2]["event"] == "first"


# ---------------------------------------------------------------------------
# Log file paths
# ---------------------------------------------------------------------------

@pytest.mark.medium
class TestGetLogFilePaths:
    """Test get_log_file_paths() for CLI and API info endpoints."""

    def test_returns_none_when_no_files(self, tmp_path):
        paths = get_log_file_paths(str(tmp_path))
        assert paths["agent_log"] is None
        assert paths["audit_log"] is None
        assert "log_directory" in paths

    def test_returns_paths_when_files_exist(self, tmp_path):
        # Create log files
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.log").write_text("test", encoding="utf-8")
        (log_dir / "audit.jsonl").write_text("test", encoding="utf-8")

        paths = get_log_file_paths(str(tmp_path))
        assert paths["agent_log"] is not None
        assert paths["audit_log"] is not None
        assert "agent.log" in paths["agent_log"]
        assert "audit.jsonl" in paths["audit_log"]


# ---------------------------------------------------------------------------
# CLI log viewer helpers
# ---------------------------------------------------------------------------

@pytest.mark.small
class TestFormatSize:
    """Test the _format_size() helper in __main__.py."""

    def test_bytes(self):
        from src.agent.__main__ import _format_size
        assert _format_size(500) == "500 B"

    def test_kilobytes(self):
        from src.agent.__main__ import _format_size
        result = _format_size(2048)
        assert "KB" in result

    def test_megabytes(self):
        from src.agent.__main__ import _format_size
        result = _format_size(5 * 1024 * 1024)
        assert "MB" in result


@pytest.mark.medium
class TestHandleLogsCommand:
    """Test the _handle_logs_command() CLI handler."""

    def test_shows_empty_message_when_no_logs(self, tmp_path, capsys):
        from src.agent.__main__ import _handle_logs_command
        _handle_logs_command([], str(tmp_path))
        captured = capsys.readouterr()
        assert "No log entries found" in captured.out

    def test_audit_subcommand(self, tmp_path, capsys):
        from src.agent.__main__ import _handle_logs_command
        _handle_logs_command(["audit"], str(tmp_path))
        captured = capsys.readouterr()
        assert "No audit events found" in captured.out

    def test_json_flag_with_entries(self, tmp_path, capsys):
        """--json should output raw JSON lines."""
        from src.agent.__main__ import _handle_logs_command

        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "test_event", "level": "info", "timestamp": "2024-01-01T00:00:00"},
        ])

        _handle_logs_command(["--json"], str(tmp_path))
        captured = capsys.readouterr()
        # Should be valid JSON
        parsed = json.loads(captured.out.strip())
        assert parsed["event"] == "test_event"

    def test_level_filter(self, tmp_path, capsys):
        from src.agent.__main__ import _handle_logs_command

        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "debug_msg", "level": "debug"},
            {"event": "error_msg", "level": "error"},
        ])

        _handle_logs_command(["--level", "error"], str(tmp_path))
        captured = capsys.readouterr()
        assert "error_msg" in captured.out
        assert "debug_msg" not in captured.out

    def test_invalid_lines_arg(self, tmp_path):
        """--lines with non-numeric value should exit."""
        from src.agent.__main__ import _handle_logs_command
        with pytest.raises(SystemExit):
            _handle_logs_command(["--lines", "abc"], str(tmp_path))


# ---------------------------------------------------------------------------
# API log endpoints
# ---------------------------------------------------------------------------

@pytest.mark.medium
class TestLogAPI:
    """Test the /api/logs endpoints via FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        """Create a TestClient for the FastAPI app."""
        from fastapi.testclient import TestClient
        from src.api.app import app
        return TestClient(app)

    def test_get_logs_endpoint(self, client):
        response = client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "count" in data

    def test_get_logs_with_level_filter(self, client):
        response = client.get("/api/logs?level=error")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data

    def test_get_logs_with_lines_limit(self, client):
        response = client.get("/api/logs?lines=5")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] <= 5

    def test_get_audit_endpoint(self, client):
        response = client.get("/api/logs/audit")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "count" in data

    def test_get_audit_with_event_type(self, client):
        response = client.get("/api/logs/audit?event_type=scan_started")
        assert response.status_code == 200

    def test_get_log_info_endpoint(self, client):
        response = client.get("/api/logs/info")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "log_directory" in data

    def test_log_info_has_session_id(self, client):
        """Session ID should match the server's SESSION_ID."""
        response = client.get("/api/logs/info")
        data = response.json()
        assert len(data["session_id"]) == 8

    def test_get_logs_lines_validation(self, client):
        """Lines parameter should be validated (1-500)."""
        response = client.get("/api/logs?lines=0")
        assert response.status_code == 422  # Validation error

        response = client.get("/api/logs?lines=501")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.medium
class TestEdgeCases:
    """Edge case tests for logging robustness."""

    def test_concurrent_audit_writes(self, tmp_path):
        """Multiple audit events written rapidly should not corrupt the file."""
        for i in range(20):
            log_audit_event(data_dir=str(tmp_path), event=f"event_{i}", index=i)

        audit_file = tmp_path / "logs" / "audit.jsonl"
        lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 20

        # Every line should be valid JSON
        for line in lines:
            data = json.loads(line)
            assert "event" in data

    def test_read_logs_with_very_long_lines(self, tmp_path):
        """Log reader should handle very long log lines without issues."""
        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "x" * 10000, "level": "info"},
        ])
        entries = read_logs(str(tmp_path))
        assert len(entries) == 1

    def test_setup_logging_idempotent(self, tmp_path):
        """Calling setup_logging twice should not duplicate handlers."""
        setup_logging(str(tmp_path))
        handler_count_1 = len(logging.getLogger().handlers)
        setup_logging(str(tmp_path))
        handler_count_2 = len(logging.getLogger().handlers)
        # handlers.clear() is called in setup_logging, so count should be consistent
        assert handler_count_2 == handler_count_1
        _cleanup_handlers()

    def test_audit_log_survives_unicode(self, tmp_path):
        """Audit events with Unicode should be written and readable."""
        log_audit_event(
            data_dir=str(tmp_path),
            event="policy_found",
            policy_name="Energieffektiviseringslagen",
            jurisdiction="Abwärmenutzungsverordnung",
            domain_id="sweden_gov",
        )
        audit_file = tmp_path / "logs" / "audit.jsonl"
        content = audit_file.read_text(encoding="utf-8")
        # Verify the JSON is valid and the data survived
        data = json.loads(content.strip())
        assert data["policy_name"] == "Energieffektiviseringslagen"
        assert "Abw" in data["jurisdiction"]  # ä may be escaped by json.dumps

    def test_read_logs_empty_file(self, tmp_path):
        """An empty log file should return an empty list."""
        log_file = tmp_path / "logs" / "agent.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("", encoding="utf-8")

        entries = read_logs(str(tmp_path))
        assert entries == []

    def test_level_filter_case_insensitive(self, tmp_path):
        """Level filter should be case-insensitive."""
        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "err", "level": "ERROR"},
            {"event": "info", "level": "INFO"},
        ])

        entries = read_logs(str(tmp_path), level="error")
        assert len(entries) == 1
        assert entries[0]["event"] == "err"

    def test_combined_filters(self, tmp_path):
        """Multiple filters should be applied together (AND logic)."""
        log_file = tmp_path / "logs" / "agent.log"
        _write_log_lines(log_file, [
            {"event": "scan_a_warn", "level": "warning", "scan_id": "aaa"},
            {"event": "scan_a_info", "level": "info", "scan_id": "aaa"},
            {"event": "scan_b_warn", "level": "warning", "scan_id": "bbb"},
        ])

        entries = read_logs(str(tmp_path), level="warning", scan_id="aaa")
        assert len(entries) == 1
        assert entries[0]["event"] == "scan_a_warn"
