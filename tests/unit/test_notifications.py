"""Unit tests for notification system."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from src.utils.notifications import (
    NotificationType,
    NotificationPriority,
    NotificationConfig,
    Notification,
    EmailNotifier,
    NotificationManager,
)


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_all_types_exist(self):
        """Should have all expected notification types."""
        expected = [
            "RUN_COMPLETE",
            "RUN_FAILED",
            "BUDGET_WARNING",
            "BUDGET_EXCEEDED",
            "HIGH_ERROR_RATE",
            "STUCK_PROCESS",
            "NO_POLICIES_FOUND",
            "COST_SPIKE",
            "CONNECTION_ERRORS",
        ]
        for name in expected:
            assert hasattr(NotificationType, name)

    def test_values_are_strings(self):
        """Should have string values."""
        assert NotificationType.RUN_COMPLETE.value == "run_complete"
        assert NotificationType.RUN_FAILED.value == "run_failed"


class TestNotificationPriority:
    """Tests for NotificationPriority enum."""

    def test_all_priorities_exist(self):
        """Should have all expected priorities."""
        assert NotificationPriority.LOW.value == "low"
        assert NotificationPriority.MEDIUM.value == "medium"
        assert NotificationPriority.HIGH.value == "high"
        assert NotificationPriority.CRITICAL.value == "critical"


class TestNotificationConfig:
    """Tests for NotificationConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = NotificationConfig()

        assert config.email_enabled is False
        assert config.smtp_host == "smtp.gmail.com"
        assert config.smtp_port == 587
        assert config.smtp_use_tls is True
        assert config.notify_on_success is True
        assert config.notify_on_error is True
        assert config.error_rate_threshold == 0.3

    def test_from_dict(self):
        """Should create config from dictionary."""
        data = {
            "email_enabled": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_username": "user@example.com",
            "smtp_password": "secret",
            "to_emails": ["alert@example.com"],
            "min_priority": "high",
        }

        config = NotificationConfig.from_dict(data)

        assert config.email_enabled is True
        assert config.smtp_host == "smtp.example.com"
        assert config.smtp_port == 465
        assert config.smtp_username == "user@example.com"
        assert config.to_emails == ["alert@example.com"]
        assert config.min_priority == NotificationPriority.HIGH

    def test_from_dict_defaults(self):
        """Should use defaults for missing values."""
        config = NotificationConfig.from_dict({})

        assert config.email_enabled is False
        assert config.smtp_host == "smtp.gmail.com"
        assert config.min_priority == NotificationPriority.LOW


class TestNotification:
    """Tests for Notification dataclass."""

    def test_create_notification(self):
        """Should create notification with all fields."""
        notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Test Subject",
            body="Test body",
            run_id="test_run_123",
            details={"key": "value"},
        )

        assert notif.type == NotificationType.RUN_COMPLETE
        assert notif.priority == NotificationPriority.LOW
        assert notif.subject == "Test Subject"
        assert notif.body == "Test body"
        assert notif.run_id == "test_run_123"
        assert notif.details == {"key": "value"}
        assert notif.timestamp is not None

    def test_should_send_respects_priority(self):
        """Should respect minimum priority setting."""
        config = NotificationConfig(min_priority=NotificationPriority.HIGH)

        low_notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Low",
            body="Low priority",
        )
        high_notif = Notification(
            type=NotificationType.RUN_FAILED,
            priority=NotificationPriority.HIGH,
            subject="High",
            body="High priority",
        )

        assert low_notif.should_send(config) is False
        assert high_notif.should_send(config) is True

    def test_should_send_respects_success_preference(self):
        """Should respect notify_on_success setting."""
        config = NotificationConfig(notify_on_success=False)

        success_notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Success",
            body="Run completed",
        )

        assert success_notif.should_send(config) is False

    def test_should_send_respects_error_preference(self):
        """Should respect notify_on_error setting."""
        config = NotificationConfig(notify_on_error=False)

        error_notif = Notification(
            type=NotificationType.RUN_FAILED,
            priority=NotificationPriority.HIGH,
            subject="Error",
            body="Run failed",
        )

        assert error_notif.should_send(config) is False


class TestEmailNotifier:
    """Tests for EmailNotifier class."""

    def test_disabled_returns_false(self):
        """Should return False when email is disabled."""
        config = NotificationConfig(email_enabled=False)
        notifier = EmailNotifier(config)

        notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Test",
            body="Test",
        )

        assert notifier.send(notif) is False

    def test_no_recipients_returns_false(self):
        """Should return False when no recipients configured."""
        config = NotificationConfig(email_enabled=True, to_emails=[])
        notifier = EmailNotifier(config)

        notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Test",
            body="Test",
        )

        assert notifier.send(notif) is False

    def test_format_subject_includes_priority(self):
        """Should include priority prefix in subject."""
        config = NotificationConfig()
        notifier = EmailNotifier(config)

        # Test different priorities
        low_notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Test",
            body="Test",
        )
        high_notif = Notification(
            type=NotificationType.RUN_FAILED,
            priority=NotificationPriority.HIGH,
            subject="Test",
            body="Test",
        )
        critical_notif = Notification(
            type=NotificationType.STUCK_PROCESS,
            priority=NotificationPriority.CRITICAL,
            subject="Test",
            body="Test",
        )

        assert "[ERROR]" not in notifier._format_subject(low_notif)
        assert "[ERROR]" in notifier._format_subject(high_notif)
        assert "[CRITICAL]" in notifier._format_subject(critical_notif)

    def test_format_text_body(self):
        """Should format readable text body."""
        config = NotificationConfig()
        notifier = EmailNotifier(config)

        notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Scan Complete",
            body="Your scan finished successfully.",
            run_id="test_run_123",
            details={"Policies": 5},
        )

        body = notifier._format_text_body(notif)

        assert "run_complete" in body
        assert "test_run_123" in body
        assert "Your scan finished successfully" in body
        assert "Policies" in body

    def test_format_html_body(self):
        """Should format HTML body with styling."""
        config = NotificationConfig()
        notifier = EmailNotifier(config)

        notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Scan Complete",
            body="Your scan finished successfully.",
        )

        body = notifier._format_html_body(notif)

        assert "<html>" in body
        assert "OCP Heat Reuse Policy Searcher" in body
        assert "Scan Complete" in body


class TestNotificationManager:
    """Tests for NotificationManager class."""

    def test_no_config_returns_false(self):
        """Should return False when no config provided."""
        manager = NotificationManager()

        result = manager.notify(Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Test",
            body="Test",
        ))

        assert result is False

    def test_queue_and_send(self):
        """Should queue notifications and send them."""
        config = NotificationConfig(email_enabled=False)  # Disabled, won't actually send
        manager = NotificationManager(config)

        notif1 = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Test 1",
            body="Test 1",
        )
        notif2 = Notification(
            type=NotificationType.RUN_FAILED,
            priority=NotificationPriority.HIGH,
            subject="Test 2",
            body="Test 2",
        )

        manager.queue(notif1)
        manager.queue(notif2)

        assert len(manager._pending_notifications) == 2

        # Send will return 0 since email is disabled
        sent = manager.send_queued()
        assert sent == 0
        assert len(manager._pending_notifications) == 0

    def test_notify_run_complete(self):
        """Should create correct notification for run completion."""
        config = NotificationConfig(email_enabled=False)
        manager = NotificationManager(config)

        # This won't actually send since email is disabled
        result = manager.notify_run_complete(
            run_id="test_run",
            domains_scanned=10,
            policies_found=5,
            policies_new=3,
            duration_seconds=150,
            cost_usd=0.25,
        )

        assert result is False  # Email disabled

    def test_notify_run_failed(self):
        """Should create correct notification for run failure."""
        config = NotificationConfig(email_enabled=False)
        manager = NotificationManager(config)

        result = manager.notify_run_failed(
            run_id="test_run",
            error_message="Connection timeout",
            error_type="TimeoutError",
        )

        assert result is False  # Email disabled

    def test_notify_budget_warning(self):
        """Should create correct notification for budget warning."""
        config = NotificationConfig(email_enabled=False)
        manager = NotificationManager(config)

        result = manager.notify_budget_warning(
            current_cost=42.50,
            budget=50.0,
            percentage=85.0,
        )

        assert result is False  # Email disabled

    def test_notify_high_error_rate(self):
        """Should create correct notification for high error rate."""
        config = NotificationConfig(email_enabled=False)
        manager = NotificationManager(config)

        result = manager.notify_high_error_rate(
            run_id="test_run",
            error_rate=0.35,
            errors=35,
            total=100,
            threshold=0.3,
        )

        assert result is False  # Email disabled

    def test_test_connection_disabled(self):
        """Should report disabled when email is off."""
        config = NotificationConfig(email_enabled=False)
        manager = NotificationManager(config)

        success, message = manager.test_connection()

        assert success is False
        assert "disabled" in message.lower()

    def test_test_connection_no_recipients(self):
        """Should report no recipients when none configured."""
        config = NotificationConfig(email_enabled=True, to_emails=[])
        manager = NotificationManager(config)

        success, message = manager.test_connection()

        assert success is False
        assert "recipient" in message.lower()


class TestNotificationIntegration:
    """Integration tests for notification system."""

    def test_full_notification_flow(self):
        """Test complete notification creation and filtering."""
        config = NotificationConfig(
            email_enabled=True,
            notify_on_success=True,
            notify_on_error=True,
            min_priority=NotificationPriority.MEDIUM,
            to_emails=["test@example.com"],
        )

        # Low priority should be filtered
        low_notif = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Success",
            body="Completed",
        )
        assert low_notif.should_send(config) is False

        # High priority should pass
        high_notif = Notification(
            type=NotificationType.RUN_FAILED,
            priority=NotificationPriority.HIGH,
            subject="Failure",
            body="Failed",
        )
        assert high_notif.should_send(config) is True

    def test_priority_ordering(self):
        """Test that priority ordering is correct."""
        priorities = [
            NotificationPriority.LOW,
            NotificationPriority.MEDIUM,
            NotificationPriority.HIGH,
            NotificationPriority.CRITICAL,
        ]

        # Create config with each minimum priority
        for i, min_priority in enumerate(priorities):
            config = NotificationConfig(min_priority=min_priority)

            # All priorities at or above should pass
            for j, priority in enumerate(priorities):
                notif = Notification(
                    type=NotificationType.RUN_COMPLETE,
                    priority=priority,
                    subject="Test",
                    body="Test",
                )

                expected = j >= i
                assert notif.should_send(config) == expected, \
                    f"Priority {priority} with min {min_priority} should be {expected}"
