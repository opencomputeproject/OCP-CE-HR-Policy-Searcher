"""Unit tests for run report generation."""

import pytest

from src.reporting.run_report import (
    DomainStats,
    FilterStats,
    RunReport,
    parse_run_events,
    format_report,
    _format_duration,
    _format_timestamp,
    _format_cost,
    _generate_suggestions,
)


def _make_events(*event_tuples):
    """Build a minimal event list from (event_type, message_or_fields) tuples."""
    events = []
    for item in event_tuples:
        if isinstance(item, dict):
            events.append(item)
        else:
            etype, msg = item
            if etype == "run_started":
                events.append({"timestamp": "2026-01-15T10:00:00+00:00", "event": "run_started"})
            elif etype == "section":
                events.append({"timestamp": "2026-01-15T10:00:00+00:00", "event": "section", "name": msg})
            else:
                events.append({"timestamp": "2026-01-15T10:00:00+00:00", "event": etype, "message": msg})
    return events


class TestFormatHelpers:
    """Tests for formatting helper functions."""

    def test_format_duration_seconds(self):
        assert _format_duration(45) == "45s"

    def test_format_duration_minutes(self):
        assert _format_duration(125) == "2m 5s"

    def test_format_duration_zero(self):
        assert _format_duration(0) == "0s"

    def test_format_timestamp_iso(self):
        result = _format_timestamp("2026-02-03T16:44:01.947509+00:00")
        assert result == "2026-02-03 16:44 UTC"

    def test_format_timestamp_empty(self):
        assert _format_timestamp("") == "unknown"

    def test_format_cost_zero(self):
        assert _format_cost(0) == "$0.00"

    def test_format_cost_small(self):
        assert _format_cost(0.005) == "$0.0050"

    def test_format_cost_normal(self):
        assert _format_cost(1.23) == "$1.23"


class TestParseRunEvents:
    """Tests for event stream parsing."""

    def test_empty_events(self):
        report = parse_run_events([], "test_run")
        assert report.run_id == "test_run"
        assert report.domains == []
        assert report.completed is False

    def test_parse_domain_lifecycle(self):
        events = _make_events(
            ("run_started", ""),
            ("info", "Starting: my_domain"),
            ("success", "Fetched: /page1 (200ms)"),
            ("success", "Fetched: /page2 (300ms)"),
            ("info", "Complete: 2 pages, 2 ok, 0 blocked"),
        )
        report = parse_run_events(events, "test_run")
        assert len(report.domains) == 1
        d = report.domains[0]
        assert d.domain_id == "my_domain"
        assert d.pages_total == 2
        assert d.pages_ok == 2
        assert d.pages_blocked == 0
        assert d.pages_error == 0
        assert len(d.fetched_paths) == 2
        assert d.fetch_times_ms == [200, 300]

    def test_parse_multiple_domains(self):
        events = _make_events(
            ("run_started", ""),
            ("info", "Starting: domain_a"),
            ("success", "Fetched: /a (100ms)"),
            ("info", "Complete: 1 pages, 1 ok, 0 blocked"),
            ("info", "Starting: domain_b"),
            ("success", "Fetched: /b (200ms)"),
            ("warning", "access_denied: /blocked"),
            ("info", "Complete: 2 pages, 1 ok, 1 blocked"),
        )
        report = parse_run_events(events, "test_run")
        assert len(report.domains) == 2
        assert report.domains[0].domain_id == "domain_a"
        assert report.domains[1].domain_id == "domain_b"
        assert report.domains[1].pages_blocked == 1

    def test_parse_blocked_warnings(self):
        events = _make_events(
            ("run_started", ""),
            ("info", "Starting: test_domain"),
            ("warning", "access_denied: /page1 (HTTP 403 -- Cloudflare)"),
            ("warning", "captcha: /page2"),
            ("info", "Complete: 2 pages, 0 ok, 2 blocked"),
        )
        report = parse_run_events(events, "test_run")
        d = report.domains[0]
        assert len(d.blocked_pages) == 2
        assert d.blocked_pages[0] == ("/page1", "access_denied (HTTP 403 -- Cloudflare)")
        assert d.blocked_pages[1] == ("/page2", "captcha")

    def test_parse_error_warnings(self):
        events = _make_events(
            ("run_started", ""),
            ("info", "Starting: test_domain"),
            ("warning", "Error: /page1 - Page.goto: Download is starting\nCall log:\n  extra"),
            ("info", "Complete: 1 pages, 0 ok, 0 blocked"),
        )
        report = parse_run_events(events, "test_run")
        d = report.domains[0]
        assert len(d.error_pages) == 1
        assert d.error_pages[0][0] == "/page1"
        assert "Download is starting" in d.error_pages[0][1]
        # Multi-line message should be truncated to first line
        assert "\n" not in d.error_pages[0][1]

    def test_parse_run_completed(self):
        events = [
            {"timestamp": "2026-01-15T10:00:00+00:00", "event": "run_started"},
            {
                "timestamp": "2026-01-15T10:05:00+00:00",
                "event": "run_completed",
                "pages_crawled": 50,
                "pages_success": 45,
                "pages_blocked": 3,
                "pages_error": 2,
                "policies_found": 5,
                "policies_new": 3,
                "policies_duplicate": 2,
                "domains_scanned": 3,
                "urls_filtered": 10,
                "keywords_passed": 8,
                "estimated_cost_usd": 0.05,
                "success_rate": 90.0,
                "duration_seconds": 300.0,
                "config": {"domain_group": "test_group"},
            },
        ]
        report = parse_run_events(events, "test_run")
        assert report.completed is True
        assert report.pages_crawled == 50
        assert report.policies_found == 5
        assert report.policies_new == 3
        assert report.domain_group == "test_group"
        assert report.estimated_cost_usd == 0.05

    def test_parse_filter_details(self):
        events = _make_events(
            ("run_started", ""),
            ("info", "URL pre-filter: skipped 5 URLs (details)"),
            ("detail", "/page1.pdf                       -> Skipped extension: .pdf"),
            ("detail", "/page2.pdf                       -> Skipped extension: .pdf"),
            ("detail", "/login/page                      -> Matched skip path: /login"),
            ("section", "ANALYSIS"),
        )
        report = parse_run_events(events, "test_run")
        fs = report.filter_stats
        assert fs.urls_filtered == 5
        assert fs.filter_reasons.get("Skipped extension: .pdf") == 2
        assert fs.filter_reasons.get("Matched skip path: /login") == 1

    def test_parse_keyword_details(self):
        events = _make_events(
            ("run_started", ""),
            ("info", "Keywords: 2/10 pages passed (details)"),
            ("detail", "Thresholds: score>=5.0  matches>=2  combinations=required"),
            ("detail", ""),
            ("detail", "FAILED by reason:"),
            ("detail", "  Below min score (5.0)                         6 pages"),
            ("detail", "  No required keyword combination satisfied     2 pages"),
            ("section", "ANALYSIS"),
        )
        report = parse_run_events(events, "test_run")
        fs = report.filter_stats
        assert fs.keywords_passed == 2
        assert fs.keywords_checked == 10
        assert fs.keyword_thresholds == "Thresholds: score>=5.0  matches>=2  combinations=required"
        assert fs.keyword_fail_reasons["Below min score (5.0)"] == 6
        assert fs.keyword_fail_reasons["No required keyword combination satisfied"] == 2

    def test_parse_incomplete_run(self):
        """Test parsing a run that didn't complete (no run_completed event)."""
        events = _make_events(
            ("run_started", ""),
            ("info", "Starting: domain_a"),
            ("success", "Fetched: /page (100ms)"),
            ("info", "Complete: 1 pages, 1 ok, 0 blocked"),
        )
        report = parse_run_events(events, "test_run")
        assert report.completed is False
        assert report.domains_scanned == 1
        assert report.pages_crawled == 1
        assert report.pages_success == 1


class TestDomainStats:
    """Tests for DomainStats dataclass."""

    def test_avg_fetch_time(self):
        d = DomainStats(domain_id="test", fetch_times_ms=[100, 200, 300])
        assert d.avg_fetch_time == 200

    def test_avg_fetch_time_empty(self):
        d = DomainStats(domain_id="test")
        assert d.avg_fetch_time is None

    def test_has_issues_blocked(self):
        d = DomainStats(domain_id="test", pages_blocked=1)
        assert d.has_issues is True

    def test_has_issues_errors(self):
        d = DomainStats(domain_id="test", pages_error=1)
        assert d.has_issues is True

    def test_has_issues_clean(self):
        d = DomainStats(domain_id="test", pages_ok=5)
        assert d.has_issues is False


class TestRunReportProperties:
    """Tests for RunReport computed properties."""

    def test_pages_after_filter(self):
        report = RunReport(run_id="test", pages_success=100, urls_filtered=30)
        assert report.pages_after_filter == 70

    def test_domain_group_from_config(self):
        report = RunReport(run_id="test", config={"domain_group": "eu"})
        assert report.domain_group == "eu"

    def test_domain_group_unknown(self):
        report = RunReport(run_id="test")
        assert report.domain_group == "unknown"


class TestGenerateSuggestions:
    """Tests for suggestion generation heuristics."""

    def test_zero_policies_keyword_bottleneck(self):
        report = RunReport(
            run_id="test",
            pages_crawled=10,
            pages_success=8,
            urls_filtered=0,
            keywords_passed=0,
            policies_found=0,
            config={"min_keyword_score": 5.0},
        )
        suggestions = _generate_suggestions(report)
        assert len(suggestions) >= 1
        assert suggestions[0][0] == "[!]"
        assert "bottleneck" in suggestions[0][1][0].lower()

    def test_high_block_rate_suggestion(self):
        report = RunReport(
            run_id="test",
            pages_crawled=10,
            policies_found=0,
            domains=[
                DomainStats(
                    domain_id="blocked_domain",
                    pages_total=4,
                    pages_blocked=4,
                    blocked_pages=[
                        ("/p1", "access_denied"),
                        ("/p2", "access_denied"),
                        ("/p3", "access_denied"),
                        ("/p4", "access_denied"),
                    ],
                )
            ],
        )
        suggestions = _generate_suggestions(report)
        # Should have bottleneck + block rate suggestions
        block_suggestions = [s for s in suggestions if "blocked_domain" in s[1][0]]
        assert len(block_suggestions) == 1
        assert "requires_playwright" in block_suggestions[0][1][1].lower()

    def test_download_error_suggestion(self):
        report = RunReport(
            run_id="test",
            pages_crawled=5,
            policies_found=1,
            domains=[
                DomainStats(
                    domain_id="dl_domain",
                    pages_total=3,
                    pages_ok=1,
                    pages_error=2,
                    error_pages=[
                        ("/file1", "Download is starting"),
                        ("/file2", "Download is starting"),
                    ],
                )
            ],
        )
        suggestions = _generate_suggestions(report)
        dl_suggestions = [s for s in suggestions if "download" in s[1][0].lower()]
        assert len(dl_suggestions) == 1

    def test_no_suggestions_clean_run(self):
        report = RunReport(
            run_id="test",
            pages_crawled=10,
            pages_success=10,
            urls_filtered=0,
            keywords_passed=5,
            policies_found=3,
            domains=[
                DomainStats(
                    domain_id="clean",
                    pages_total=10,
                    pages_ok=10,
                )
            ],
        )
        suggestions = _generate_suggestions(report)
        assert len(suggestions) == 0


class TestFormatReport:
    """Tests for the full report formatter."""

    def test_format_report_contains_sections(self):
        events = [
            {"timestamp": "2026-01-15T10:00:00+00:00", "event": "run_started"},
            {"timestamp": "2026-01-15T10:00:01+00:00", "event": "info", "message": "Starting: test_domain"},
            {"timestamp": "2026-01-15T10:00:02+00:00", "event": "success", "message": "Fetched: /page (100ms)"},
            {"timestamp": "2026-01-15T10:00:03+00:00", "event": "info", "message": "Complete: 1 pages, 1 ok, 0 blocked"},
            {
                "timestamp": "2026-01-15T10:05:00+00:00",
                "event": "run_completed",
                "pages_crawled": 1,
                "pages_success": 1,
                "pages_blocked": 0,
                "pages_error": 0,
                "policies_found": 0,
                "domains_scanned": 1,
                "urls_filtered": 0,
                "keywords_passed": 0,
                "duration_seconds": 60.0,
                "success_rate": 100.0,
                "estimated_cost_usd": 0.0,
            },
        ]
        report = parse_run_events(events, "test_run_123")
        output = format_report(report)

        assert "RUN REPORT" in output
        assert "test_run_123" in output
        assert "PIPELINE FUNNEL" in output
        assert "DOMAIN BREAKDOWN" in output
        assert "test_domain" in output

    def test_format_report_no_crash_empty(self):
        """Format should not crash on empty events."""
        report = parse_run_events([], "empty_run")
        output = format_report(report)
        assert "RUN REPORT" in output
        assert "empty_run" in output
