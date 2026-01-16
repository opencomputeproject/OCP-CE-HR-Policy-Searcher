"""Unit tests for last-run command functionality."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.logging.run_logger import (
    get_last_run_log,
    find_run_log,
    list_run_logs,
    load_run_log,
    format_last_run_summary,
    format_last_run_config,
    RunConfig,
)


class TestGetLastRunLog:
    """Tests for get_last_run_log function."""

    def test_no_logs_directory(self):
        """Returns None when logs directory doesn't exist."""
        result = get_last_run_log("/nonexistent/path")
        assert result is None

    def test_empty_logs_directory(self):
        """Returns None when logs directory is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_last_run_log(tmpdir)
            assert result is None

    def test_no_run_files(self):
        """Returns None when no run_*.json files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create non-run files
            (Path(tmpdir) / "cost_history.json").write_text("{}")
            (Path(tmpdir) / "alert_history.json").write_text("{}")
            result = get_last_run_log(tmpdir)
            assert result is None

    def test_single_run_file(self):
        """Returns the single run file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_file = Path(tmpdir) / "run_20260115_120000.json"
            run_file.write_text("[]")
            result = get_last_run_log(tmpdir)
            assert result == run_file

    def test_multiple_run_files(self):
        """Returns the most recent run file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import time

            # Create older file
            older_file = Path(tmpdir) / "run_20260114_120000.json"
            older_file.write_text("[]")

            time.sleep(0.1)  # Ensure different mtime

            # Create newer file
            newer_file = Path(tmpdir) / "run_20260115_120000.json"
            newer_file.write_text("[]")

            result = get_last_run_log(tmpdir)
            assert result == newer_file

    def test_ignores_non_run_json_files(self):
        """Ignores JSON files that don't match run_*.json pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create various non-run files
            (Path(tmpdir) / "cost_history.json").write_text("{}")
            (Path(tmpdir) / "config.json").write_text("{}")
            (Path(tmpdir) / "test.json").write_text("{}")

            # Create a run file
            run_file = Path(tmpdir) / "run_20260115_120000.json"
            run_file.write_text("[]")

            result = get_last_run_log(tmpdir)
            assert result == run_file


class TestLoadRunLog:
    """Tests for load_run_log function."""

    def test_load_valid_log(self):
        """Loads run_completed event from valid log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "run_test.json"
            events = [
                {"event": "run_started", "timestamp": "2026-01-15T12:00:00Z"},
                {"event": "info", "message": "Test"},
                {
                    "event": "run_completed",
                    "timestamp": "2026-01-15T12:05:00Z",
                    "domains_scanned": 5,
                    "policies_found": 2,
                },
            ]
            log_file.write_text(json.dumps(events))

            result = load_run_log(log_file)
            assert result is not None
            assert result["event"] == "run_completed"
            assert result["domains_scanned"] == 5
            assert result["policies_found"] == 2

    def test_load_missing_file(self):
        """Returns None for missing file."""
        result = load_run_log(Path("/nonexistent/run.json"))
        assert result is None

    def test_load_invalid_json(self):
        """Returns None for invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "run_test.json"
            log_file.write_text("not valid json {{{")

            result = load_run_log(log_file)
            assert result is None

    def test_load_no_run_completed(self):
        """Returns None when no run_completed event exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "run_test.json"
            events = [
                {"event": "run_started"},
                {"event": "info", "message": "Test"},
            ]
            log_file.write_text(json.dumps(events))

            result = load_run_log(log_file)
            assert result is None

    def test_load_with_config(self):
        """Loads run_completed event with config data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "run_test.json"
            events = [
                {
                    "event": "run_completed",
                    "timestamp": "2026-01-15T12:05:00Z",
                    "domains_scanned": 5,
                    "config": {
                        "domain_group": "nordic",
                        "min_keyword_score": 5.0,
                        "enable_llm": True,
                    },
                },
            ]
            log_file.write_text(json.dumps(events))

            result = load_run_log(log_file)
            assert result is not None
            assert "config" in result
            assert result["config"]["domain_group"] == "nordic"


class TestFormatLastRunSummary:
    """Tests for format_last_run_summary function."""

    def test_basic_summary(self):
        """Formats basic run data."""
        run_data = {
            "timestamp": "2026-01-15T12:05:00+00:00",
            "domains_scanned": 5,
            "pages_crawled": 100,
            "pages_success": 90,
            "pages_blocked": 8,
            "pages_error": 2,
            "success_rate": 90.0,
            "policies_found": 3,
            "policies_new": 2,
            "policies_duplicate": 1,
            "duration_seconds": 300,
        }

        result = format_last_run_summary(run_data, "run_20260115_120000")

        assert "LAST RUN SUMMARY" in result
        assert "run_20260115_120000" in result
        assert "Domains scanned:" in result
        assert "5" in result
        assert "Pages crawled:" in result
        assert "100" in result
        assert "Policies found:" in result
        assert "3" in result
        assert "Duration:" in result
        assert "5m 0s" in result

    def test_summary_with_llm_stats(self):
        """Includes LLM stats when present."""
        run_data = {
            "timestamp": "2026-01-15T12:05:00+00:00",
            "domains_scanned": 5,
            "pages_crawled": 100,
            "pages_success": 90,
            "pages_blocked": 8,
            "pages_error": 2,
            "success_rate": 90.0,
            "policies_found": 3,
            "policies_new": 2,
            "policies_duplicate": 1,
            "duration_seconds": 300,
            "screening_calls": 10,
            "screening_tokens_input": 50000,
            "screening_tokens_output": 5000,
            "llm_calls": 5,
            "llm_tokens_input": 25000,
            "llm_tokens_output": 2500,
            "estimated_cost_usd": 0.15,
        }

        result = format_last_run_summary(run_data, "run_test")

        assert "Screening (Haiku)" in result
        assert "Analysis (Sonnet)" in result
        assert "TOTAL COST" in result

    def test_summary_handles_missing_fields(self):
        """Handles missing optional fields gracefully."""
        run_data = {
            "timestamp": "2026-01-15T12:05:00+00:00",
            "domains_scanned": 0,
            # Missing most fields
        }

        result = format_last_run_summary(run_data, "run_test")

        assert "LAST RUN SUMMARY" in result
        assert "Domains scanned:" in result

    def test_summary_formats_duration(self):
        """Formats duration correctly for various values."""
        run_data = {
            "timestamp": "2026-01-15T12:05:00+00:00",
            "domains_scanned": 1,
            "pages_crawled": 10,
            "pages_success": 10,
            "pages_blocked": 0,
            "pages_error": 0,
            "success_rate": 100.0,
            "policies_found": 0,
            "policies_new": 0,
            "policies_duplicate": 0,
            "duration_seconds": 3661,  # 1 hour, 1 minute, 1 second
        }

        result = format_last_run_summary(run_data, "run_test")

        assert "61m 1s" in result  # 61 minutes, 1 second


class TestFormatLastRunConfig:
    """Tests for format_last_run_config function."""

    def test_basic_config(self):
        """Formats basic configuration."""
        config = {
            "domain_group": "nordic",
            "domains_count": 5,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": True,
            "screening_model": "claude-haiku-4-20250514",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }

        result = format_last_run_config(config)

        assert "RUN CONFIGURATION" in result
        assert "nordic" in result
        assert "min_keyword_score" in result
        assert "5.0" in result
        assert "two-stage" in result
        assert "claude-haiku" in result
        assert "claude-sonnet" in result

    def test_config_with_filters(self):
        """Includes filter information when present."""
        config = {
            "domain_group": "all",
            "domains_count": 10,
            "category_filter": "energy_ministry",
            "tag_filters": ["efficiency", "mandates"],
            "policy_type_filters": ["regulation"],
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": False,
            "screening_model": "",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }

        result = format_last_run_config(config)

        assert "Category filter:" in result
        assert "energy_ministry" in result
        assert "Tag filters:" in result
        assert "efficiency" in result
        assert "Policy types:" in result
        assert "regulation" in result

    def test_config_llm_disabled(self):
        """Shows LLM disabled message when appropriate."""
        config = {
            "domain_group": "test",
            "domains_count": 1,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": False,
            "enable_two_stage": False,
            "screening_model": "",
            "analysis_model": "",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }

        result = format_last_run_config(config)

        assert "disabled (keyword-only)" in result

    def test_config_single_stage(self):
        """Shows single-stage when two-stage is disabled."""
        config = {
            "domain_group": "test",
            "domains_count": 1,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": False,
            "screening_model": "",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }

        result = format_last_run_config(config)

        assert "single-stage" in result

    def test_config_combinations_disabled(self):
        """Shows DISABLED when required combinations is off."""
        config = {
            "domain_group": "test",
            "domains_count": 1,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": False,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": True,
            "screening_model": "claude-haiku-4-20250514",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }

        result = format_last_run_config(config)

        assert "DISABLED" in result

    def test_config_cache_cleared(self):
        """Shows cache cleared status."""
        config = {
            "domain_group": "test",
            "domains_count": 1,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": True,
            "screening_model": "claude-haiku-4-20250514",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": True,
            "dry_run": False,
        }

        result = format_last_run_config(config)

        assert "enabled (cleared)" in result

    def test_config_with_chunking(self):
        """Shows chunking information when present."""
        config = {
            "domain_group": "all",
            "domains_count": 29,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": True,
            "screening_model": "claude-haiku-4-20250514",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
            "chunking": "5 per batch",
        }

        result = format_last_run_config(config)

        assert "Chunking:" in result
        assert "5 per batch" in result

    def test_config_with_cost_breakdown(self):
        """Shows cost breakdown when run_data with LLM stats is provided."""
        config = {
            "domain_group": "nordic",
            "domains_count": 5,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": True,
            "screening_model": "claude-haiku-4-20250514",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }
        run_data = {
            "screening_calls": 10,
            "screening_tokens_input": 50000,
            "screening_tokens_output": 5000,
            "llm_calls": 5,
            "llm_tokens_input": 25000,
            "llm_tokens_output": 2500,
            "estimated_cost_usd": 0.15,
        }

        result = format_last_run_config(config, run_data)

        assert "COST BREAKDOWN" in result
        assert "Screening (Haiku)" in result
        assert "Analysis (Sonnet)" in result
        assert "TOTAL COST" in result
        assert "$0.15" in result

    def test_config_with_only_sonnet_cost(self):
        """Shows only Sonnet cost when no screening was used."""
        config = {
            "domain_group": "test",
            "domains_count": 1,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": False,
            "screening_model": "",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }
        run_data = {
            "screening_calls": 0,
            "llm_calls": 5,
            "llm_tokens_input": 25000,
            "llm_tokens_output": 2500,
            "estimated_cost_usd": 0.1125,
        }

        result = format_last_run_config(config, run_data)

        assert "COST BREAKDOWN" in result
        assert "Screening (Haiku)" not in result
        assert "Analysis (Sonnet)" in result
        assert "TOTAL COST" in result

    def test_config_without_run_data(self):
        """Works without run_data (no cost section shown)."""
        config = {
            "domain_group": "test",
            "domains_count": 1,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": True,
            "enable_two_stage": True,
            "screening_model": "claude-haiku-4-20250514",
            "analysis_model": "claude-sonnet-4-20250514",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }

        result = format_last_run_config(config)

        assert "COST BREAKDOWN" not in result
        assert "RUN CONFIGURATION" in result

    def test_config_no_llm_calls(self):
        """No cost section when LLM wasn't used."""
        config = {
            "domain_group": "test",
            "domains_count": 1,
            "min_keyword_score": 5.0,
            "min_keyword_matches": 2,
            "required_combinations_enabled": True,
            "min_density": 1.0,
            "density_enabled": True,
            "boost_keywords_enabled": True,
            "penalty_keywords_enabled": True,
            "enable_llm": False,
            "enable_two_stage": False,
            "screening_model": "",
            "analysis_model": "",
            "screening_min_confidence": 5,
            "min_relevance_score": 5,
            "cache_enabled": True,
            "cache_cleared": False,
            "dry_run": False,
        }
        run_data = {
            "screening_calls": 0,
            "llm_calls": 0,
            "estimated_cost_usd": 0,
        }

        result = format_last_run_config(config, run_data)

        assert "COST BREAKDOWN" not in result


class TestRunConfigDataclass:
    """Tests for RunConfig dataclass."""

    def test_default_values(self):
        """RunConfig has sensible defaults."""
        config = RunConfig()

        assert config.domain_group == "all"
        assert config.min_keyword_score == 5.0
        assert config.enable_llm is True
        assert config.enable_two_stage is True

    def test_format_verbose(self):
        """format_verbose returns formatted lines."""
        config = RunConfig(
            domain_group="nordic",
            domains_count=5,
            min_keyword_score=5.0,
            enable_llm=True,
        )

        lines = config.format_verbose()

        assert len(lines) > 0
        # Check for expected content
        full_output = "\n".join(lines)
        assert "nordic" in full_output
        assert "5" in full_output


class TestIntegration:
    """Integration tests for last-run functionality."""

    def test_full_workflow(self):
        """Test complete workflow of saving and loading run data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "run_20260115_120000.json"

            # Create a complete run log
            events = [
                {"event": "run_started", "timestamp": "2026-01-15T12:00:00+00:00"},
                {
                    "event": "run_completed",
                    "timestamp": "2026-01-15T12:05:00+00:00",
                    "domains_scanned": 5,
                    "pages_crawled": 100,
                    "pages_success": 95,
                    "pages_blocked": 3,
                    "pages_error": 2,
                    "success_rate": 95.0,
                    "policies_found": 3,
                    "policies_new": 2,
                    "policies_duplicate": 1,
                    "duration_seconds": 300,
                    "estimated_cost_usd": 0.15,
                    "config": {
                        "domain_group": "nordic",
                        "domains_count": 5,
                        "category_filter": None,
                        "tag_filters": None,
                        "policy_type_filters": None,
                        "min_keyword_score": 5.0,
                        "min_keyword_matches": 2,
                        "required_combinations_enabled": True,
                        "min_density": 1.0,
                        "density_enabled": True,
                        "boost_keywords_enabled": True,
                        "penalty_keywords_enabled": True,
                        "enable_llm": True,
                        "enable_two_stage": True,
                        "screening_model": "claude-haiku-4-20250514",
                        "analysis_model": "claude-sonnet-4-20250514",
                        "screening_min_confidence": 5,
                        "min_relevance_score": 5,
                        "cache_enabled": True,
                        "cache_cleared": False,
                        "dry_run": False,
                        "chunking": None,
                    },
                },
            ]
            log_file.write_text(json.dumps(events, indent=2))

            # Find the log file
            found_file = get_last_run_log(tmpdir)
            assert found_file == log_file

            # Load the run data
            run_data = load_run_log(found_file)
            assert run_data is not None
            assert run_data["domains_scanned"] == 5

            # Format summary
            summary = format_last_run_summary(run_data, "run_20260115_120000")
            assert "nordic" not in summary  # Config not in summary
            assert "5" in summary  # Domains count is in summary

            # Format config
            config = run_data.get("config")
            assert config is not None
            config_output = format_last_run_config(config)
            assert "nordic" in config_output
            assert "two-stage" in config_output


class TestFindRunLog:
    """Tests for find_run_log function."""

    def test_no_logs_directory(self):
        """Returns None when logs directory doesn't exist."""
        result = find_run_log("anything", "/nonexistent/path")
        assert result is None

    def test_empty_logs_directory(self):
        """Returns None when logs directory is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = find_run_log("anything", tmpdir)
            assert result is None

    def test_find_by_numeric_index(self):
        """Finds run by numeric index (1=most recent)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import time

            # Create files with different mtimes
            file1 = Path(tmpdir) / "run_20260114_100000.json"
            file1.write_text("[]")
            time.sleep(0.1)

            file2 = Path(tmpdir) / "run_20260115_100000.json"
            file2.write_text("[]")
            time.sleep(0.1)

            file3 = Path(tmpdir) / "run_20260116_100000.json"
            file3.write_text("[]")

            # Index 1 = most recent (file3)
            result = find_run_log("1", tmpdir)
            assert result == file3

            # Index 2 = second most recent (file2)
            result = find_run_log("2", tmpdir)
            assert result == file2

            # Index 3 = oldest (file1)
            result = find_run_log("3", tmpdir)
            assert result == file1

    def test_find_by_invalid_index(self):
        """Returns None for out-of-range numeric index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "run_20260115_100000.json"
            file1.write_text("[]")

            result = find_run_log("99", tmpdir)
            assert result is None

    def test_find_by_full_run_id(self):
        """Finds run by full run ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "run_20260115_143022.json"
            file1.write_text("[]")

            result = find_run_log("run_20260115_143022", tmpdir)
            assert result == file1

    def test_find_by_partial_run_id(self):
        """Finds run by partial run ID (without run_ prefix)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "run_20260115_143022.json"
            file1.write_text("[]")

            result = find_run_log("20260115_143022", tmpdir)
            assert result == file1

    def test_find_by_date(self):
        """Finds run by date only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import time

            file1 = Path(tmpdir) / "run_20260115_100000.json"
            file1.write_text("[]")
            time.sleep(0.1)

            file2 = Path(tmpdir) / "run_20260115_120000.json"
            file2.write_text("[]")

            # Should find the most recent file matching the date
            result = find_run_log("20260115", tmpdir)
            assert result == file2

    def test_find_handles_json_extension(self):
        """Handles .json extension in pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "run_20260115_143022.json"
            file1.write_text("[]")

            result = find_run_log("run_20260115_143022.json", tmpdir)
            assert result == file1

    def test_find_no_match(self):
        """Returns None when no match found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "run_20260115_100000.json"
            file1.write_text("[]")

            result = find_run_log("20260114", tmpdir)
            assert result is None


class TestListRunLogs:
    """Tests for list_run_logs function."""

    def test_no_logs_directory(self):
        """Returns empty list when logs directory doesn't exist."""
        result = list_run_logs("/nonexistent/path")
        assert result == []

    def test_empty_logs_directory(self):
        """Returns empty list when logs directory is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = list_run_logs(tmpdir)
            assert result == []

    def test_lists_runs_in_order(self):
        """Lists runs with most recent first."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import time

            # Create files with different mtimes
            file1 = Path(tmpdir) / "run_20260114_100000.json"
            file1.write_text(json.dumps([{"event": "run_completed", "domains_scanned": 5}]))
            time.sleep(0.1)

            file2 = Path(tmpdir) / "run_20260115_100000.json"
            file2.write_text(json.dumps([{"event": "run_completed", "domains_scanned": 10}]))
            time.sleep(0.1)

            file3 = Path(tmpdir) / "run_20260116_100000.json"
            file3.write_text(json.dumps([{"event": "run_completed", "domains_scanned": 15}]))

            result = list_run_logs(tmpdir)

            assert len(result) == 3
            # Check order (most recent first)
            assert result[0][0] == 1  # Index 1
            assert result[0][1] == file3
            assert result[0][2]["domains_scanned"] == 15

            assert result[1][0] == 2  # Index 2
            assert result[1][1] == file2
            assert result[1][2]["domains_scanned"] == 10

            assert result[2][0] == 3  # Index 3
            assert result[2][1] == file1
            assert result[2][2]["domains_scanned"] == 5

    def test_respects_limit(self):
        """Respects limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import time

            # Create 5 files
            for i in range(5):
                file = Path(tmpdir) / f"run_2026011{i}_100000.json"
                file.write_text(json.dumps([{"event": "run_completed"}]))
                time.sleep(0.05)

            # Default limit is 10, should get all 5
            result = list_run_logs(tmpdir)
            assert len(result) == 5

            # Limit to 2
            result = list_run_logs(tmpdir, limit=2)
            assert len(result) == 2

            # Limit 0 means all
            result = list_run_logs(tmpdir, limit=0)
            assert len(result) == 5

    def test_extracts_summary_info(self):
        """Extracts summary information from log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "run_20260115_100000.json"
            events = [{
                "event": "run_completed",
                "timestamp": "2026-01-15T10:00:00+00:00",
                "domains_scanned": 7,
                "policies_found": 3,
                "estimated_cost_usd": 0.25,
                "config": {"domain_group": "nordic"}
            }]
            file1.write_text(json.dumps(events))

            result = list_run_logs(tmpdir)

            assert len(result) == 1
            idx, path, summary = result[0]
            assert idx == 1
            assert path == file1
            assert summary["timestamp"] == "2026-01-15T10:00:00+00:00"
            assert summary["domains_scanned"] == 7
            assert summary["policies_found"] == 3
            assert summary["estimated_cost_usd"] == 0.25
            assert summary["domain_group"] == "nordic"

    def test_handles_missing_config(self):
        """Handles logs without config section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "run_20260115_100000.json"
            events = [{
                "event": "run_completed",
                "domains_scanned": 5,
            }]
            file1.write_text(json.dumps(events))

            result = list_run_logs(tmpdir)

            assert len(result) == 1
            _, _, summary = result[0]
            assert summary["domains_scanned"] == 5
            assert summary["domain_group"] == ""  # Empty when no config

    def test_handles_invalid_log_files(self):
        """Handles corrupted or invalid log files gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Valid file
            file1 = Path(tmpdir) / "run_20260115_100000.json"
            file1.write_text(json.dumps([{"event": "run_completed", "domains_scanned": 5}]))

            # Invalid JSON
            file2 = Path(tmpdir) / "run_20260116_100000.json"
            file2.write_text("not valid json")

            result = list_run_logs(tmpdir)

            # Should still return 2 entries
            assert len(result) == 2
            # The invalid one should have empty summary
            for idx, path, summary in result:
                if path == file2:
                    assert summary == {}

    def test_ignores_non_run_files(self):
        """Ignores files that don't match run_*.json pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Non-run files
            (Path(tmpdir) / "cost_history.json").write_text("{}")
            (Path(tmpdir) / "config.json").write_text("{}")

            # Run file
            run_file = Path(tmpdir) / "run_20260115_100000.json"
            run_file.write_text(json.dumps([{"event": "run_completed"}]))

            result = list_run_logs(tmpdir)

            assert len(result) == 1
            assert result[0][1] == run_file
