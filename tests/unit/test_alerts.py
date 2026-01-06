"""Unit tests for alert system."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

from src.utils.alerts import (
    AlertType,
    AlertSeverity,
    Alert,
    AlertThresholds,
    RunHealthMetrics,
    AlertManager,
)


class TestAlertType:
    """Tests for AlertType enum."""

    def test_all_types_exist(self):
        """Should have all expected alert types."""
        expected = [
            "HIGH_ERROR_RATE",
            "STUCK_PROCESS",
            "BUDGET_WARNING",
            "BUDGET_EXCEEDED",
            "COST_SPIKE",
            "NO_POLICIES",
            "CONNECTION_FAILURES",
            "LOW_SUCCESS_RATE",
            "EXCESSIVE_RETRIES",
            "MEMORY_WARNING",
            "RATE_LIMITED",
        ]
        for name in expected:
            assert hasattr(AlertType, name)


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_all_severities_exist(self):
        """Should have all expected severities."""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.ERROR.value == "error"
        assert AlertSeverity.CRITICAL.value == "critical"


class TestAlert:
    """Tests for Alert dataclass."""

    def test_create_alert(self):
        """Should create alert with all fields."""
        alert = Alert(
            alert_type=AlertType.HIGH_ERROR_RATE,
            severity=AlertSeverity.WARNING,
            message="High error rate detected",
            run_id="test_run_123",
            details={"error_rate": "25%"},
        )

        assert alert.alert_type == AlertType.HIGH_ERROR_RATE
        assert alert.severity == AlertSeverity.WARNING
        assert alert.message == "High error rate detected"
        assert alert.run_id == "test_run_123"
        assert alert.resolved is False
        assert alert.resolution_time is None

    def test_to_dict(self):
        """Should convert alert to dictionary."""
        alert = Alert(
            alert_type=AlertType.BUDGET_WARNING,
            severity=AlertSeverity.WARNING,
            message="Budget at 80%",
            details={"usage": "80%"},
        )

        data = alert.to_dict()

        assert data["alert_type"] == "budget_warning"
        assert data["severity"] == "warning"
        assert data["message"] == "Budget at 80%"
        assert data["details"] == {"usage": "80%"}
        assert data["resolved"] is False


class TestAlertThresholds:
    """Tests for AlertThresholds dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        thresholds = AlertThresholds()

        assert thresholds.error_rate_warning == 0.2
        assert thresholds.error_rate_critical == 0.4
        assert thresholds.success_rate_warning == 0.6
        assert thresholds.budget_warning_percent == 0.8
        assert thresholds.stuck_timeout_minutes == 30

    def test_from_dict(self):
        """Should create thresholds from dictionary."""
        data = {
            "error_rate_warning": 0.15,
            "error_rate_critical": 0.35,
            "budget_warning_percent": 0.75,
            "stuck_timeout_minutes": 45,
        }

        thresholds = AlertThresholds.from_dict(data)

        assert thresholds.error_rate_warning == 0.15
        assert thresholds.error_rate_critical == 0.35
        assert thresholds.budget_warning_percent == 0.75
        assert thresholds.stuck_timeout_minutes == 45

    def test_from_dict_uses_defaults(self):
        """Should use defaults for missing values."""
        thresholds = AlertThresholds.from_dict({})

        assert thresholds.error_rate_warning == 0.2
        assert thresholds.stuck_timeout_minutes == 30


class TestRunHealthMetrics:
    """Tests for RunHealthMetrics dataclass."""

    def test_initial_values(self):
        """Should initialize with zero values."""
        metrics = RunHealthMetrics(run_id="test_run")

        assert metrics.pages_attempted == 0
        assert metrics.pages_success == 0
        assert metrics.pages_error == 0
        assert metrics.consecutive_failures == 0
        assert metrics.error_rate == 0.0
        assert metrics.success_rate == 1.0

    def test_record_page_success(self):
        """Should track successful pages."""
        metrics = RunHealthMetrics(run_id="test_run")

        metrics.record_page_success("http://example.com/page1")
        metrics.record_page_success("http://example.com/page2")

        assert metrics.pages_attempted == 2
        assert metrics.pages_success == 2
        assert metrics.pages_error == 0
        assert metrics.consecutive_failures == 0
        assert metrics.success_rate == 1.0

    def test_record_page_error(self):
        """Should track error pages."""
        metrics = RunHealthMetrics(run_id="test_run")

        metrics.record_page_error("http://example.com/fail1", "timeout")
        metrics.record_page_error("http://example.com/fail2", "500")

        assert metrics.pages_attempted == 2
        assert metrics.pages_error == 2
        assert metrics.consecutive_failures == 2
        assert metrics.error_rate == 1.0

    def test_record_page_blocked(self):
        """Should track blocked pages."""
        metrics = RunHealthMetrics(run_id="test_run")

        metrics.record_page_blocked()
        metrics.record_page_blocked()

        assert metrics.pages_attempted == 2
        assert metrics.pages_blocked == 2

    def test_record_page_timeout(self):
        """Should track timeout pages."""
        metrics = RunHealthMetrics(run_id="test_run")

        metrics.record_page_timeout()

        assert metrics.pages_attempted == 1
        assert metrics.pages_timeout == 1
        assert metrics.consecutive_failures == 1

    def test_consecutive_failures_reset(self):
        """Should reset consecutive failures on success."""
        metrics = RunHealthMetrics(run_id="test_run")

        metrics.record_page_error("http://example.com/fail1", "500")
        metrics.record_page_error("http://example.com/fail2", "500")
        assert metrics.consecutive_failures == 2

        metrics.record_page_success("http://example.com/success")
        assert metrics.consecutive_failures == 0

    def test_error_rate_calculation(self):
        """Should calculate correct error rate."""
        metrics = RunHealthMetrics(run_id="test_run")

        # 3 successes, 2 errors = 40% error rate
        metrics.record_page_success("http://example.com/1")
        metrics.record_page_success("http://example.com/2")
        metrics.record_page_success("http://example.com/3")
        metrics.record_page_error("http://example.com/fail1", "500")
        metrics.record_page_timeout()

        assert metrics.pages_attempted == 5
        assert metrics.error_rate == pytest.approx(0.4, abs=0.01)

    def test_retry_tracking(self):
        """Should track retries by domain."""
        metrics = RunHealthMetrics(run_id="test_run")

        metrics.record_retry("domain_a")
        metrics.record_retry("domain_a")
        metrics.record_retry("domain_b")

        assert metrics.total_retries == 3
        assert metrics.retries_by_domain["domain_a"] == 2
        assert metrics.retries_by_domain["domain_b"] == 1

    def test_domain_tracking(self):
        """Should track domain completion."""
        metrics = RunHealthMetrics(run_id="test_run")

        metrics.record_domain_complete("domain_a", success=True)
        metrics.record_domain_complete("domain_b", success=False)
        metrics.record_domain_complete("domain_c", success=True)

        assert metrics.domains_complete == 3
        assert metrics.domains_failed == 1
        assert metrics.failed_domains == ["domain_b"]
        assert metrics.domain_failure_rate == pytest.approx(0.333, abs=0.01)


class TestAlertManager:
    """Tests for AlertManager class."""

    def test_check_error_rate_no_alert_below_threshold(self):
        """Should not alert when error rate is below threshold."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # 15 successes, 1 error = ~6% error rate (below 20% warning)
        for i in range(15):
            metrics.record_page_success(f"http://example.com/{i}")
        metrics.record_page_error("http://example.com/fail", "500")

        alert = manager.check_error_rate(metrics)
        assert alert is None

    def test_check_error_rate_warning(self):
        """Should trigger warning when error rate exceeds threshold."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # 7 successes, 3 errors = 30% error rate (above 20% warning)
        for i in range(7):
            metrics.record_page_success(f"http://example.com/{i}")
        for i in range(3):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")

        alert = manager.check_error_rate(metrics)

        assert alert is not None
        assert alert.alert_type == AlertType.HIGH_ERROR_RATE
        assert alert.severity == AlertSeverity.WARNING

    def test_check_error_rate_critical(self):
        """Should trigger critical when error rate is very high."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # 5 successes, 5 errors = 50% error rate (above 40% critical)
        for i in range(5):
            metrics.record_page_success(f"http://example.com/{i}")
        for i in range(5):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")

        alert = manager.check_error_rate(metrics)

        assert alert is not None
        assert alert.alert_type == AlertType.HIGH_ERROR_RATE
        assert alert.severity == AlertSeverity.CRITICAL

    def test_check_error_rate_min_pages(self):
        """Should not alert when below minimum pages."""
        manager = AlertManager(AlertThresholds(min_pages_for_rate=10))
        metrics = RunHealthMetrics(run_id="test_run")

        # 100% error rate but only 5 pages
        for i in range(5):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")

        alert = manager.check_error_rate(metrics)
        assert alert is None

    def test_check_success_rate_warning(self):
        """Should trigger warning when success rate is low."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # 5 successes, 5 errors = 50% success rate (below 60% warning)
        for i in range(5):
            metrics.record_page_success(f"http://example.com/{i}")
        for i in range(5):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")

        alert = manager.check_success_rate(metrics)

        assert alert is not None
        assert alert.alert_type == AlertType.LOW_SUCCESS_RATE
        assert alert.severity == AlertSeverity.WARNING

    def test_check_budget_no_alert(self):
        """Should not alert when under budget."""
        manager = AlertManager()

        alert = manager.check_budget(current_spend=30.0, monthly_budget=50.0)
        assert alert is None

    def test_check_budget_warning(self):
        """Should trigger warning at 80% budget."""
        manager = AlertManager()

        alert = manager.check_budget(current_spend=42.0, monthly_budget=50.0)

        assert alert is not None
        assert alert.alert_type == AlertType.BUDGET_WARNING
        assert alert.severity == AlertSeverity.WARNING

    def test_check_budget_exceeded(self):
        """Should trigger critical when budget exceeded."""
        manager = AlertManager()

        alert = manager.check_budget(current_spend=55.0, monthly_budget=50.0)

        assert alert is not None
        assert alert.alert_type == AlertType.BUDGET_EXCEEDED
        assert alert.severity == AlertSeverity.CRITICAL

    def test_check_budget_zero_budget(self):
        """Should not alert when budget is zero or negative."""
        manager = AlertManager()

        alert = manager.check_budget(current_spend=100.0, monthly_budget=0)
        assert alert is None

        alert = manager.check_budget(current_spend=100.0, monthly_budget=-10)
        assert alert is None

    def test_check_cost_spike(self):
        """Should detect cost spikes."""
        manager = AlertManager()

        # Current cost is 3x average
        alert = manager.check_cost_spike(
            current_cost=3.0,
            average_cost=1.0,
            run_id="test_run",
        )

        assert alert is not None
        assert alert.alert_type == AlertType.COST_SPIKE
        assert "3.0x" in alert.message

    def test_check_cost_spike_no_alert(self):
        """Should not alert for normal cost variations."""
        manager = AlertManager()

        alert = manager.check_cost_spike(
            current_cost=1.5,
            average_cost=1.0,
            run_id="test_run",
        )

        assert alert is None

    def test_check_connection_failures_consecutive(self):
        """Should detect consecutive connection failures."""
        manager = AlertManager(AlertThresholds(connection_failure_threshold=3))
        metrics = RunHealthMetrics(run_id="test_run")

        # Record consecutive failures
        for i in range(4):
            metrics.record_page_error(f"http://example.com/fail{i}", "connection_error")

        alert = manager.check_connection_failures(metrics)

        assert alert is not None
        assert alert.alert_type == AlertType.CONNECTION_FAILURES

    def test_check_rate_limiting(self):
        """Should detect rate limiting."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # Record rate limit errors
        for i in range(5):
            metrics.record_page_error(f"http://example.com/{i}", "429")

        alert = manager.check_rate_limiting(metrics)

        assert alert is not None
        assert alert.alert_type == AlertType.RATE_LIMITED

    def test_run_all_checks(self):
        """Should run all health checks."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # Create conditions for multiple alerts
        for i in range(5):
            metrics.record_page_success(f"http://example.com/{i}")
        for i in range(10):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")

        alerts = manager.run_all_checks(metrics)

        # Should trigger high error rate and low success rate
        alert_types = [a.alert_type for a in alerts]
        assert AlertType.HIGH_ERROR_RATE in alert_types or AlertType.LOW_SUCCESS_RATE in alert_types

    def test_resolve_alert(self):
        """Should mark alert as resolved."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # Create alert
        for i in range(10):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")
        alert = manager.check_error_rate(metrics)

        assert alert is not None
        assert alert.resolved is False

        manager.resolve_alert(alert)

        assert alert.resolved is True
        assert alert.resolution_time is not None

    def test_get_active_alerts(self):
        """Should return only unresolved alerts."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # Create multiple alerts
        for i in range(10):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")

        alerts = manager.run_all_checks(metrics)
        assert len(alerts) > 0

        # Resolve one
        manager.resolve_alert(alerts[0])

        active = manager.get_active_alerts()
        assert alerts[0] not in active

    def test_get_summary(self):
        """Should return summary of alerts."""
        manager = AlertManager()
        metrics = RunHealthMetrics(run_id="test_run")

        # Create alert
        for i in range(10):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")
        manager.run_all_checks(metrics)

        summary = manager.get_summary()

        assert "total_active" in summary
        assert "by_severity" in summary
        assert "by_type" in summary

    def test_format_summary(self):
        """Should format readable summary."""
        manager = AlertManager()

        summary = manager.format_summary()

        assert "ALERT SUMMARY" in summary
        assert "Active Alerts" in summary


class TestAlertPersistence:
    """Tests for alert history persistence."""

    def test_save_and_load_history(self, tmp_path):
        """Should persist alert history to file."""
        history_file = tmp_path / "alert_history.json"
        manager = AlertManager(history_file=str(history_file))

        # Create alert
        metrics = RunHealthMetrics(run_id="test_run")
        for i in range(10):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")
        manager.check_error_rate(metrics)

        assert history_file.exists()

        # Load in new manager
        manager2 = AlertManager(history_file=str(history_file))
        assert manager2.history_file.exists()


class TestCustomThresholds:
    """Tests for custom threshold configurations."""

    def test_custom_error_threshold(self):
        """Should use custom error threshold."""
        custom_thresholds = AlertThresholds(
            error_rate_warning=0.1,  # 10% instead of 20%
            min_pages_for_rate=5,
        )
        manager = AlertManager(custom_thresholds)
        metrics = RunHealthMetrics(run_id="test_run")

        # 8 successes, 2 errors = 20% error rate
        for i in range(8):
            metrics.record_page_success(f"http://example.com/{i}")
        for i in range(2):
            metrics.record_page_error(f"http://example.com/fail{i}", "500")

        alert = manager.check_error_rate(metrics)

        # Should trigger because 20% > 10% custom threshold
        assert alert is not None

    def test_custom_budget_threshold(self):
        """Should use custom budget threshold."""
        custom_thresholds = AlertThresholds(budget_warning_percent=0.5)  # 50%
        manager = AlertManager(custom_thresholds)

        # 60% usage should trigger with 50% threshold
        alert = manager.check_budget(current_spend=30.0, monthly_budget=50.0)

        assert alert is not None
