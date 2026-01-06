"""Unit tests for cost tracking utilities."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.utils.costs import (
    MODEL_PRICING,
    CostBreakdown,
    RunCostRecord,
    CostHistory,
    CostTracker,
    estimate_run_cost,
)


class TestModelPricing:
    """Tests for model pricing constants."""

    def test_sonnet_pricing(self):
        """Should have correct pricing for Sonnet models."""
        pricing = MODEL_PRICING["claude-sonnet-4-20250514"]
        assert pricing["input"] == 3.00
        assert pricing["output"] == 15.00

    def test_haiku_pricing(self):
        """Should have cheaper pricing for Haiku models."""
        pricing = MODEL_PRICING["claude-3-5-haiku-20241022"]
        assert pricing["input"] < MODEL_PRICING["claude-sonnet-4-20250514"]["input"]
        assert pricing["output"] < MODEL_PRICING["claude-sonnet-4-20250514"]["output"]

    def test_opus_pricing(self):
        """Should have more expensive pricing for Opus models."""
        pricing = MODEL_PRICING["claude-3-opus-20240229"]
        assert pricing["input"] > MODEL_PRICING["claude-sonnet-4-20250514"]["input"]
        assert pricing["output"] > MODEL_PRICING["claude-sonnet-4-20250514"]["output"]

    def test_default_fallback(self):
        """Should have default pricing for unknown models."""
        assert "default" in MODEL_PRICING
        assert MODEL_PRICING["default"]["input"] > 0
        assert MODEL_PRICING["default"]["output"] > 0


class TestCostBreakdown:
    """Tests for CostBreakdown dataclass."""

    def test_calculate_zero_tokens(self):
        """Should calculate zero cost for zero tokens."""
        breakdown = CostBreakdown.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=0,
            output_tokens=0,
            api_calls=0,
        )

        assert breakdown.input_cost_usd == 0.0
        assert breakdown.output_cost_usd == 0.0
        assert breakdown.total_cost_usd == 0.0

    def test_calculate_input_cost(self):
        """Should calculate correct input cost."""
        # 1M tokens at $3/1M = $3.00
        breakdown = CostBreakdown.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,
            output_tokens=0,
            api_calls=10,
        )

        assert breakdown.input_cost_usd == 3.00
        assert breakdown.output_cost_usd == 0.0
        assert breakdown.total_cost_usd == 3.00

    def test_calculate_output_cost(self):
        """Should calculate correct output cost."""
        # 1M tokens at $15/1M = $15.00
        breakdown = CostBreakdown.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=0,
            output_tokens=1_000_000,
            api_calls=10,
        )

        assert breakdown.input_cost_usd == 0.0
        assert breakdown.output_cost_usd == 15.00
        assert breakdown.total_cost_usd == 15.00

    def test_calculate_combined_cost(self):
        """Should calculate combined input + output cost."""
        # 100K input at $3/1M = $0.30
        # 10K output at $15/1M = $0.15
        # Total = $0.45
        breakdown = CostBreakdown.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=100_000,
            output_tokens=10_000,
            api_calls=5,
        )

        assert breakdown.input_cost_usd == pytest.approx(0.30, abs=0.001)
        assert breakdown.output_cost_usd == pytest.approx(0.15, abs=0.001)
        assert breakdown.total_cost_usd == pytest.approx(0.45, abs=0.001)

    def test_calculate_unknown_model_uses_default(self):
        """Should use default pricing for unknown models."""
        breakdown = CostBreakdown.calculate(
            model="some-unknown-model",
            input_tokens=1_000_000,
            output_tokens=0,
            api_calls=1,
        )

        # Should use default pricing (same as Sonnet)
        assert breakdown.input_cost_usd == MODEL_PRICING["default"]["input"]

    def test_format_summary(self):
        """Should format readable summary."""
        breakdown = CostBreakdown.calculate(
            model="claude-sonnet-4-20250514",
            input_tokens=50000,
            output_tokens=5000,
            api_calls=10,
        )

        summary = breakdown.format_summary()

        assert "claude-sonnet-4-20250514" in summary
        assert "50,000" in summary
        assert "5,000" in summary
        assert "10" in summary


class TestCostHistory:
    """Tests for CostHistory dataclass."""

    def test_empty_history(self):
        """Should handle empty history."""
        history = CostHistory()

        assert len(history.runs) == 0
        assert history.total_cost_usd == 0.0
        assert history.total_api_calls == 0

    def test_add_run(self):
        """Should add run and update totals."""
        history = CostHistory()

        record = RunCostRecord(
            run_id="test_run_1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            model="claude-sonnet-4-20250514",
            input_tokens=10000,
            output_tokens=1000,
            total_cost_usd=0.05,
            api_calls=5,
            domains_scanned=2,
            policies_found=1,
        )

        history.add_run(record)

        assert len(history.runs) == 1
        assert history.total_cost_usd == 0.05
        assert history.total_api_calls == 5
        assert history.total_input_tokens == 10000
        assert history.total_output_tokens == 1000

    def test_add_multiple_runs(self):
        """Should accumulate totals across runs."""
        history = CostHistory()

        for i in range(3):
            record = RunCostRecord(
                run_id=f"run_{i}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                model="claude-sonnet-4-20250514",
                input_tokens=10000,
                output_tokens=1000,
                total_cost_usd=0.10,
                api_calls=5,
                domains_scanned=2,
                policies_found=1,
            )
            history.add_run(record)

        assert len(history.runs) == 3
        assert history.total_cost_usd == pytest.approx(0.30, abs=0.001)
        assert history.total_api_calls == 15

    def test_get_runs_since(self):
        """Should filter runs by date."""
        history = CostHistory()

        # Add old run (8 days ago)
        old_record = RunCostRecord(
            run_id="old_run",
            timestamp=(datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
            model="claude-sonnet-4-20250514",
            input_tokens=10000,
            output_tokens=1000,
            total_cost_usd=0.10,
            api_calls=5,
            domains_scanned=2,
            policies_found=1,
        )
        history.add_run(old_record)

        # Add recent run (1 day ago)
        recent_record = RunCostRecord(
            run_id="recent_run",
            timestamp=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            model="claude-sonnet-4-20250514",
            input_tokens=10000,
            output_tokens=1000,
            total_cost_usd=0.20,
            api_calls=5,
            domains_scanned=2,
            policies_found=1,
        )
        history.add_run(recent_record)

        runs_7d = history.get_runs_since(7)
        assert len(runs_7d) == 1
        assert runs_7d[0].run_id == "recent_run"

    def test_get_cost_since(self):
        """Should calculate cost for date range."""
        history = CostHistory()

        # Add runs at different times
        for days_ago, cost in [(1, 0.10), (5, 0.20), (10, 0.50)]:
            record = RunCostRecord(
                run_id=f"run_{days_ago}d",
                timestamp=(datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
                model="claude-sonnet-4-20250514",
                input_tokens=10000,
                output_tokens=1000,
                total_cost_usd=cost,
                api_calls=5,
                domains_scanned=2,
                policies_found=1,
            )
            history.add_run(record)

        assert history.get_cost_since(7) == pytest.approx(0.30, abs=0.001)  # 1d + 5d
        assert history.get_cost_since(30) == pytest.approx(0.80, abs=0.001)  # all

    def test_format_summary(self):
        """Should format readable summary."""
        history = CostHistory()

        record = RunCostRecord(
            run_id="test_run",
            timestamp=datetime.now(timezone.utc).isoformat(),
            model="claude-sonnet-4-20250514",
            input_tokens=10000,
            output_tokens=1000,
            total_cost_usd=0.05,
            api_calls=5,
            domains_scanned=2,
            policies_found=1,
        )
        history.add_run(record)

        summary = history.format_summary()

        assert "COST HISTORY" in summary
        assert "Total runs" in summary
        assert "test_run" in summary


class TestCostTracker:
    """Tests for CostTracker class."""

    def test_load_nonexistent_history(self, tmp_path):
        """Should create empty history when file doesn't exist."""
        history_file = tmp_path / "nonexistent.json"
        tracker = CostTracker(str(history_file))

        assert len(tracker.history.runs) == 0

    def test_record_and_persist(self, tmp_path):
        """Should record run and save to file."""
        history_file = tmp_path / "cost_history.json"
        tracker = CostTracker(str(history_file))

        breakdown = tracker.record_run(
            run_id="test_run",
            model="claude-sonnet-4-20250514",
            input_tokens=50000,
            output_tokens=5000,
            api_calls=10,
            domains_scanned=5,
            policies_found=2,
        )

        assert history_file.exists()
        assert breakdown.total_cost_usd > 0

        # Reload and verify persistence
        tracker2 = CostTracker(str(history_file))
        assert len(tracker2.history.runs) == 1
        assert tracker2.history.runs[0].run_id == "test_run"

    def test_check_budget_warning_under(self, tmp_path):
        """Should return None when under budget."""
        history_file = tmp_path / "cost_history.json"
        tracker = CostTracker(str(history_file))

        # Add small cost
        tracker.record_run(
            run_id="test_run",
            model="claude-sonnet-4-20250514",
            input_tokens=10000,
            output_tokens=1000,
            api_calls=1,
            domains_scanned=1,
            policies_found=0,
        )

        warning = tracker.check_budget_warning(monthly_budget=50.0)
        assert warning is None

    def test_check_budget_warning_approaching(self, tmp_path):
        """Should warn when approaching budget."""
        history_file = tmp_path / "cost_history.json"
        tracker = CostTracker(str(history_file))

        # Add cost that puts us at 85% of $1 budget (using small budget for testing)
        # 85K input tokens at $3/1M = $0.255
        # 17K output tokens at $15/1M = $0.255
        # Total = $0.51 (51% of $1)... need more
        # Let's use direct manipulation for test
        record = RunCostRecord(
            run_id="expensive_run",
            timestamp=datetime.now(timezone.utc).isoformat(),
            model="claude-sonnet-4-20250514",
            input_tokens=1000000,
            output_tokens=100000,
            total_cost_usd=0.85,  # 85% of $1 budget
            api_calls=50,
            domains_scanned=10,
            policies_found=5,
        )
        tracker.history.add_run(record)
        tracker._save_history()

        warning = tracker.check_budget_warning(monthly_budget=1.0, warn_threshold=0.8)
        assert warning is not None
        assert "warning" in warning.lower() or "85" in warning

    def test_check_budget_warning_exceeded(self, tmp_path):
        """Should warn when budget exceeded."""
        history_file = tmp_path / "cost_history.json"
        tracker = CostTracker(str(history_file))

        record = RunCostRecord(
            run_id="expensive_run",
            timestamp=datetime.now(timezone.utc).isoformat(),
            model="claude-sonnet-4-20250514",
            input_tokens=1000000,
            output_tokens=100000,
            total_cost_usd=1.50,  # 150% of $1 budget
            api_calls=50,
            domains_scanned=10,
            policies_found=5,
        )
        tracker.history.add_run(record)
        tracker._save_history()

        warning = tracker.check_budget_warning(monthly_budget=1.0)
        assert warning is not None
        assert "EXCEEDED" in warning

    def test_no_warning_without_budget(self, tmp_path):
        """Should not warn when no budget set."""
        history_file = tmp_path / "cost_history.json"
        tracker = CostTracker(str(history_file))

        record = RunCostRecord(
            run_id="expensive_run",
            timestamp=datetime.now(timezone.utc).isoformat(),
            model="claude-sonnet-4-20250514",
            input_tokens=1000000,
            output_tokens=100000,
            total_cost_usd=100.00,
            api_calls=50,
            domains_scanned=10,
            policies_found=5,
        )
        tracker.history.add_run(record)

        warning = tracker.check_budget_warning(monthly_budget=None)
        assert warning is None


class TestEstimateRunCost:
    """Tests for estimate_run_cost function."""

    def test_basic_estimate(self):
        """Should estimate cost for given parameters."""
        estimate = estimate_run_cost(
            domains=10,
            pages_per_domain=50,
            relevance_rate=0.1,
            avg_tokens_per_page=4000,
        )

        assert estimate["domains"] == 10
        assert estimate["estimated_pages"] == 500
        assert estimate["estimated_analyzed"] == 50
        assert estimate["estimated_input_tokens"] == 200000  # 50 * 4000
        assert estimate["estimated_output_tokens"] == 25000  # 50 * 500
        assert estimate["estimated_cost_usd"] > 0

    def test_estimate_with_different_model(self):
        """Should use model-specific pricing."""
        sonnet_estimate = estimate_run_cost(
            domains=10,
            model="claude-sonnet-4-20250514",
        )

        haiku_estimate = estimate_run_cost(
            domains=10,
            model="claude-3-5-haiku-20241022",
        )

        # Haiku should be cheaper
        assert haiku_estimate["estimated_cost_usd"] < sonnet_estimate["estimated_cost_usd"]

    def test_estimate_zero_domains(self):
        """Should handle zero domains."""
        estimate = estimate_run_cost(domains=0)

        assert estimate["estimated_pages"] == 0
        assert estimate["estimated_cost_usd"] == 0.0


class TestIntegration:
    """Integration tests for cost tracking workflow."""

    def test_full_workflow(self, tmp_path):
        """Test complete cost tracking workflow."""
        history_file = tmp_path / "costs.json"
        tracker = CostTracker(str(history_file))

        # Simulate 3 runs
        for i in range(3):
            tracker.record_run(
                run_id=f"run_{i}",
                model="claude-sonnet-4-20250514",
                input_tokens=50000 * (i + 1),
                output_tokens=5000 * (i + 1),
                api_calls=10 * (i + 1),
                domains_scanned=5,
                policies_found=i,
            )

        # Verify totals
        history = tracker.get_history()
        assert len(history.runs) == 3
        assert history.total_api_calls == 60  # 10 + 20 + 30
        assert history.total_cost_usd > 0

        # Verify persistence
        tracker2 = CostTracker(str(history_file))
        assert len(tracker2.history.runs) == 3

        # Verify summary generation
        summary = tracker2.history.format_summary()
        assert "run_0" in summary
        assert "run_2" in summary
