"""Error detection and alerting system for policy searcher."""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from enum import Enum
from pathlib import Path
import json


class AlertType(Enum):
    """Types of alerts that can be triggered."""
    HIGH_ERROR_RATE = "high_error_rate"
    STUCK_PROCESS = "stuck_process"
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"
    COST_SPIKE = "cost_spike"
    NO_POLICIES = "no_policies"
    CONNECTION_FAILURES = "connection_failures"
    LOW_SUCCESS_RATE = "low_success_rate"
    EXCESSIVE_RETRIES = "excessive_retries"
    MEMORY_WARNING = "memory_warning"
    RATE_LIMITED = "rate_limited"


class AlertSeverity(Enum):
    """Severity levels for alerts."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Represents a triggered alert."""
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: Optional[str] = None
    details: dict = field(default_factory=dict)
    resolved: bool = False
    resolution_time: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert alert to dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "run_id": self.run_id,
            "details": self.details,
            "resolved": self.resolved,
            "resolution_time": self.resolution_time.isoformat() if self.resolution_time else None,
        }


@dataclass
class AlertThresholds:
    """Configurable thresholds for alert triggers."""
    # Error rate thresholds
    error_rate_warning: float = 0.2     # 20% error rate triggers warning
    error_rate_critical: float = 0.4    # 40% error rate triggers critical

    # Success rate thresholds
    success_rate_warning: float = 0.6   # Below 60% success triggers warning
    success_rate_critical: float = 0.3  # Below 30% success triggers critical

    # Budget thresholds
    budget_warning_percent: float = 0.8  # Warn at 80% of budget
    budget_critical_percent: float = 1.0  # Critical at 100% of budget

    # Cost spike detection
    cost_spike_multiplier: float = 2.0  # Alert if cost > 2x average

    # Stuck process detection
    stuck_timeout_minutes: int = 30     # No progress for 30 min

    # Retry thresholds
    max_retries_per_domain: int = 10    # Alert if retries exceed this
    retry_rate_warning: float = 0.3     # Alert if >30% of requests need retries

    # Connection thresholds
    connection_failure_threshold: int = 5  # Alert after 5 consecutive failures
    domains_failing_threshold: float = 0.5  # Alert if >50% of domains fail

    # Minimum pages for rate calculations
    min_pages_for_rate: int = 10  # Need at least 10 pages before calculating rates

    @classmethod
    def from_dict(cls, config: dict) -> "AlertThresholds":
        """Create thresholds from dictionary."""
        return cls(
            error_rate_warning=config.get("error_rate_warning", 0.2),
            error_rate_critical=config.get("error_rate_critical", 0.4),
            success_rate_warning=config.get("success_rate_warning", 0.6),
            success_rate_critical=config.get("success_rate_critical", 0.3),
            budget_warning_percent=config.get("budget_warning_percent", 0.8),
            budget_critical_percent=config.get("budget_critical_percent", 1.0),
            cost_spike_multiplier=config.get("cost_spike_multiplier", 2.0),
            stuck_timeout_minutes=config.get("stuck_timeout_minutes", 30),
            max_retries_per_domain=config.get("max_retries_per_domain", 10),
            retry_rate_warning=config.get("retry_rate_warning", 0.3),
            connection_failure_threshold=config.get("connection_failure_threshold", 5),
            domains_failing_threshold=config.get("domains_failing_threshold", 0.5),
            min_pages_for_rate=config.get("min_pages_for_rate", 10),
        )


@dataclass
class RunHealthMetrics:
    """Metrics tracked during a run for health monitoring."""
    run_id: str
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Page metrics
    pages_attempted: int = 0
    pages_success: int = 0
    pages_error: int = 0
    pages_blocked: int = 0
    pages_timeout: int = 0

    # Retry metrics
    total_retries: int = 0
    retries_by_domain: dict = field(default_factory=dict)

    # Connection metrics
    consecutive_failures: int = 0
    failed_domains: list = field(default_factory=list)
    connection_errors: dict = field(default_factory=dict)  # error_type -> count

    # Domain metrics
    domains_attempted: int = 0
    domains_complete: int = 0
    domains_failed: int = 0

    # Progress tracking
    last_activity_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_successful_page: Optional[str] = None

    # Cost tracking
    estimated_cost: float = 0.0
    api_calls: int = 0
    tokens_used: int = 0

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity_time = datetime.now(timezone.utc)

    def record_page_success(self, url: str) -> None:
        """Record a successful page crawl."""
        self.pages_attempted += 1
        self.pages_success += 1
        self.consecutive_failures = 0
        self.last_successful_page = url
        self.update_activity()

    def record_page_error(self, url: str, error_type: str) -> None:
        """Record a page error."""
        self.pages_attempted += 1
        self.pages_error += 1
        self.consecutive_failures += 1
        self.connection_errors[error_type] = self.connection_errors.get(error_type, 0) + 1
        self.update_activity()

    def record_page_blocked(self) -> None:
        """Record a blocked page."""
        self.pages_attempted += 1
        self.pages_blocked += 1
        self.update_activity()

    def record_page_timeout(self) -> None:
        """Record a timeout."""
        self.pages_attempted += 1
        self.pages_timeout += 1
        self.consecutive_failures += 1
        self.update_activity()

    def record_retry(self, domain_id: str) -> None:
        """Record a retry attempt."""
        self.total_retries += 1
        self.retries_by_domain[domain_id] = self.retries_by_domain.get(domain_id, 0) + 1
        self.update_activity()

    def record_domain_complete(self, domain_id: str, success: bool) -> None:
        """Record domain completion."""
        self.domains_complete += 1
        if not success:
            self.domains_failed += 1
            self.failed_domains.append(domain_id)
        self.update_activity()

    @property
    def error_rate(self) -> float:
        """Calculate current error rate."""
        if self.pages_attempted == 0:
            return 0.0
        return (self.pages_error + self.pages_timeout) / self.pages_attempted

    @property
    def success_rate(self) -> float:
        """Calculate current success rate."""
        if self.pages_attempted == 0:
            return 1.0
        return self.pages_success / self.pages_attempted

    @property
    def retry_rate(self) -> float:
        """Calculate retry rate."""
        if self.pages_attempted == 0:
            return 0.0
        return self.total_retries / self.pages_attempted

    @property
    def domain_failure_rate(self) -> float:
        """Calculate domain failure rate."""
        if self.domains_complete == 0:
            return 0.0
        return self.domains_failed / self.domains_complete

    @property
    def minutes_since_activity(self) -> float:
        """Get minutes since last activity."""
        delta = datetime.now(timezone.utc) - self.last_activity_time
        return delta.total_seconds() / 60

    @property
    def run_duration_minutes(self) -> float:
        """Get total run duration in minutes."""
        delta = datetime.now(timezone.utc) - self.start_time
        return delta.total_seconds() / 60


class AlertManager:
    """Manages alert detection and tracking."""

    def __init__(
        self,
        thresholds: Optional[AlertThresholds] = None,
        history_file: str = "logs/alert_history.json",
    ):
        self.thresholds = thresholds or AlertThresholds()
        self.history_file = Path(history_file)
        self.active_alerts: list[Alert] = []
        self.alert_history: list[Alert] = []
        self._load_history()

    def _load_history(self) -> None:
        """Load alert history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    # We just track that history exists, don't reconstruct Alert objects
                    self.alert_history = []
            except (json.JSONDecodeError, KeyError):
                self.alert_history = []

    def _save_history(self) -> None:
        """Save alert history to file."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        history_data = [alert.to_dict() for alert in self.alert_history[-100:]]  # Keep last 100
        with open(self.history_file, "w") as f:
            json.dump(history_data, f, indent=2)

    def _create_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        run_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> Alert:
        """Create and track a new alert."""
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            run_id=run_id,
            details=details or {},
        )
        self.active_alerts.append(alert)
        self.alert_history.append(alert)
        self._save_history()
        return alert

    def check_error_rate(self, metrics: RunHealthMetrics) -> Optional[Alert]:
        """Check if error rate exceeds thresholds."""
        if metrics.pages_attempted < self.thresholds.min_pages_for_rate:
            return None

        error_rate = metrics.error_rate

        if error_rate >= self.thresholds.error_rate_critical:
            return self._create_alert(
                AlertType.HIGH_ERROR_RATE,
                AlertSeverity.CRITICAL,
                f"Critical error rate: {error_rate:.1%} of pages failed",
                run_id=metrics.run_id,
                details={
                    "error_rate": f"{error_rate:.1%}",
                    "pages_attempted": metrics.pages_attempted,
                    "pages_error": metrics.pages_error,
                    "pages_timeout": metrics.pages_timeout,
                    "threshold": f"{self.thresholds.error_rate_critical:.1%}",
                }
            )
        elif error_rate >= self.thresholds.error_rate_warning:
            return self._create_alert(
                AlertType.HIGH_ERROR_RATE,
                AlertSeverity.WARNING,
                f"High error rate: {error_rate:.1%} of pages failed",
                run_id=metrics.run_id,
                details={
                    "error_rate": f"{error_rate:.1%}",
                    "pages_attempted": metrics.pages_attempted,
                    "pages_error": metrics.pages_error,
                    "pages_timeout": metrics.pages_timeout,
                    "threshold": f"{self.thresholds.error_rate_warning:.1%}",
                }
            )
        return None

    def check_success_rate(self, metrics: RunHealthMetrics) -> Optional[Alert]:
        """Check if success rate is below thresholds."""
        if metrics.pages_attempted < self.thresholds.min_pages_for_rate:
            return None

        success_rate = metrics.success_rate

        if success_rate <= self.thresholds.success_rate_critical:
            return self._create_alert(
                AlertType.LOW_SUCCESS_RATE,
                AlertSeverity.CRITICAL,
                f"Critical success rate: Only {success_rate:.1%} of pages succeeded",
                run_id=metrics.run_id,
                details={
                    "success_rate": f"{success_rate:.1%}",
                    "pages_success": metrics.pages_success,
                    "pages_attempted": metrics.pages_attempted,
                    "threshold": f"{self.thresholds.success_rate_critical:.1%}",
                }
            )
        elif success_rate <= self.thresholds.success_rate_warning:
            return self._create_alert(
                AlertType.LOW_SUCCESS_RATE,
                AlertSeverity.WARNING,
                f"Low success rate: Only {success_rate:.1%} of pages succeeded",
                run_id=metrics.run_id,
                details={
                    "success_rate": f"{success_rate:.1%}",
                    "pages_success": metrics.pages_success,
                    "pages_attempted": metrics.pages_attempted,
                    "threshold": f"{self.thresholds.success_rate_warning:.1%}",
                }
            )
        return None

    def check_stuck_process(self, metrics: RunHealthMetrics) -> Optional[Alert]:
        """Check if process appears stuck (no activity for timeout period)."""
        minutes_inactive = metrics.minutes_since_activity

        if minutes_inactive >= self.thresholds.stuck_timeout_minutes:
            return self._create_alert(
                AlertType.STUCK_PROCESS,
                AlertSeverity.CRITICAL,
                f"Process appears stuck: No activity for {minutes_inactive:.0f} minutes",
                run_id=metrics.run_id,
                details={
                    "minutes_inactive": f"{minutes_inactive:.0f}",
                    "last_activity": metrics.last_activity_time.isoformat(),
                    "last_successful_page": metrics.last_successful_page,
                    "timeout_threshold": self.thresholds.stuck_timeout_minutes,
                }
            )
        return None

    def check_budget(
        self,
        current_spend: float,
        monthly_budget: float,
    ) -> Optional[Alert]:
        """Check budget usage against thresholds."""
        if monthly_budget <= 0:
            return None

        usage_percent = current_spend / monthly_budget

        if usage_percent >= self.thresholds.budget_critical_percent:
            return self._create_alert(
                AlertType.BUDGET_EXCEEDED,
                AlertSeverity.CRITICAL,
                f"Budget EXCEEDED: ${current_spend:.2f} / ${monthly_budget:.2f} ({usage_percent:.1%})",
                details={
                    "current_spend": f"${current_spend:.2f}",
                    "monthly_budget": f"${monthly_budget:.2f}",
                    "usage_percent": f"{usage_percent:.1%}",
                }
            )
        elif usage_percent >= self.thresholds.budget_warning_percent:
            return self._create_alert(
                AlertType.BUDGET_WARNING,
                AlertSeverity.WARNING,
                f"Budget warning: ${current_spend:.2f} / ${monthly_budget:.2f} ({usage_percent:.1%})",
                details={
                    "current_spend": f"${current_spend:.2f}",
                    "monthly_budget": f"${monthly_budget:.2f}",
                    "usage_percent": f"{usage_percent:.1%}",
                }
            )
        return None

    def check_cost_spike(
        self,
        current_cost: float,
        average_cost: float,
        run_id: Optional[str] = None,
    ) -> Optional[Alert]:
        """Check if current run cost is significantly higher than average."""
        if average_cost <= 0:
            return None

        multiplier = current_cost / average_cost

        if multiplier >= self.thresholds.cost_spike_multiplier:
            return self._create_alert(
                AlertType.COST_SPIKE,
                AlertSeverity.WARNING,
                f"Cost spike detected: ${current_cost:.4f} is {multiplier:.1f}x the average",
                run_id=run_id,
                details={
                    "current_cost": f"${current_cost:.4f}",
                    "average_cost": f"${average_cost:.4f}",
                    "multiplier": f"{multiplier:.1f}x",
                    "threshold": f"{self.thresholds.cost_spike_multiplier:.1f}x",
                }
            )
        return None

    def check_connection_failures(self, metrics: RunHealthMetrics) -> Optional[Alert]:
        """Check for excessive connection failures."""
        # Check consecutive failures
        if metrics.consecutive_failures >= self.thresholds.connection_failure_threshold:
            return self._create_alert(
                AlertType.CONNECTION_FAILURES,
                AlertSeverity.ERROR,
                f"Connection failures: {metrics.consecutive_failures} consecutive failures",
                run_id=metrics.run_id,
                details={
                    "consecutive_failures": metrics.consecutive_failures,
                    "threshold": self.thresholds.connection_failure_threshold,
                    "error_types": metrics.connection_errors,
                    "failed_domains": metrics.failed_domains[-5:],  # Last 5
                }
            )

        # Check domain failure rate
        if (metrics.domains_complete >= 3 and
            metrics.domain_failure_rate >= self.thresholds.domains_failing_threshold):
            return self._create_alert(
                AlertType.CONNECTION_FAILURES,
                AlertSeverity.WARNING,
                f"High domain failure rate: {metrics.domain_failure_rate:.1%} of domains failed",
                run_id=metrics.run_id,
                details={
                    "domain_failure_rate": f"{metrics.domain_failure_rate:.1%}",
                    "domains_failed": metrics.domains_failed,
                    "domains_complete": metrics.domains_complete,
                    "failed_domains": metrics.failed_domains,
                }
            )
        return None

    def check_retry_rate(self, metrics: RunHealthMetrics) -> Optional[Alert]:
        """Check if retry rate is excessive."""
        if metrics.pages_attempted < self.thresholds.min_pages_for_rate:
            return None

        if metrics.retry_rate >= self.thresholds.retry_rate_warning:
            # Find domains with most retries
            top_retry_domains = sorted(
                metrics.retries_by_domain.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            return self._create_alert(
                AlertType.EXCESSIVE_RETRIES,
                AlertSeverity.WARNING,
                f"Excessive retries: {metrics.retry_rate:.1%} retry rate ({metrics.total_retries} retries)",
                run_id=metrics.run_id,
                details={
                    "retry_rate": f"{metrics.retry_rate:.1%}",
                    "total_retries": metrics.total_retries,
                    "top_domains": dict(top_retry_domains),
                    "threshold": f"{self.thresholds.retry_rate_warning:.1%}",
                }
            )
        return None

    def check_rate_limiting(self, metrics: RunHealthMetrics) -> Optional[Alert]:
        """Check for signs of rate limiting (429 errors)."""
        rate_limit_errors = metrics.connection_errors.get("429", 0) + \
                          metrics.connection_errors.get("rate_limit", 0) + \
                          metrics.connection_errors.get("too_many_requests", 0)

        if rate_limit_errors >= 3:
            return self._create_alert(
                AlertType.RATE_LIMITED,
                AlertSeverity.WARNING,
                f"Rate limiting detected: {rate_limit_errors} rate limit responses",
                run_id=metrics.run_id,
                details={
                    "rate_limit_errors": rate_limit_errors,
                    "all_errors": metrics.connection_errors,
                }
            )
        return None

    def run_all_checks(self, metrics: RunHealthMetrics) -> list[Alert]:
        """Run all health checks and return triggered alerts."""
        alerts = []

        checks = [
            self.check_error_rate(metrics),
            self.check_success_rate(metrics),
            self.check_stuck_process(metrics),
            self.check_connection_failures(metrics),
            self.check_retry_rate(metrics),
            self.check_rate_limiting(metrics),
        ]

        for alert in checks:
            if alert:
                alerts.append(alert)

        return alerts

    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> list[Alert]:
        """Get all active (unresolved) alerts, optionally filtered by severity."""
        alerts = [a for a in self.active_alerts if not a.resolved]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts

    def resolve_alert(self, alert: Alert) -> None:
        """Mark an alert as resolved."""
        alert.resolved = True
        alert.resolution_time = datetime.now(timezone.utc)
        self._save_history()

    def resolve_all(self) -> int:
        """Resolve all active alerts. Returns count resolved."""
        count = 0
        for alert in self.active_alerts:
            if not alert.resolved:
                self.resolve_alert(alert)
                count += 1
        return count

    def get_summary(self) -> dict:
        """Get a summary of current alert status."""
        active = self.get_active_alerts()

        by_severity = {}
        for severity in AlertSeverity:
            count = len([a for a in active if a.severity == severity])
            if count > 0:
                by_severity[severity.value] = count

        by_type = {}
        for alert in active:
            type_name = alert.alert_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

        return {
            "total_active": len(active),
            "by_severity": by_severity,
            "by_type": by_type,
            "total_historical": len(self.alert_history),
        }

    def format_summary(self) -> str:
        """Format alert summary for display."""
        summary = self.get_summary()
        lines = [
            "",
            "=" * 60,
            "  ALERT SUMMARY",
            "=" * 60,
            "",
            f"  Active Alerts: {summary['total_active']}",
        ]

        if summary['by_severity']:
            lines.append("")
            lines.append("  By Severity:")
            for severity, count in summary['by_severity'].items():
                lines.append(f"    {severity.upper()}: {count}")

        if summary['by_type']:
            lines.append("")
            lines.append("  By Type:")
            for alert_type, count in summary['by_type'].items():
                lines.append(f"    {alert_type}: {count}")

        lines.append("")
        lines.append("=" * 60)
        lines.append("")

        return "\n".join(lines)
