"""Email notification system for policy searcher."""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import datetime, timezone


class NotificationType(Enum):
    """Types of notifications that can be sent."""
    RUN_COMPLETE = "run_complete"
    RUN_FAILED = "run_failed"
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"
    HIGH_ERROR_RATE = "high_error_rate"
    STUCK_PROCESS = "stuck_process"
    NO_POLICIES_FOUND = "no_policies_found"
    COST_SPIKE = "cost_spike"
    CONNECTION_ERRORS = "connection_errors"


class NotificationPriority(Enum):
    """Priority levels for notifications."""
    LOW = "low"          # Informational only
    MEDIUM = "medium"    # Warnings, non-critical
    HIGH = "high"        # Errors, requires attention
    CRITICAL = "critical"  # System failures, immediate action needed


@dataclass
class NotificationConfig:
    """Configuration for the notification system."""
    # Email settings
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""  # App password for Gmail
    smtp_use_tls: bool = True
    from_email: str = ""
    to_emails: list[str] = field(default_factory=list)

    # What to notify about
    notify_on_success: bool = True
    notify_on_error: bool = True
    notify_on_warning: bool = True

    # Thresholds for automatic alerts
    error_rate_threshold: float = 0.3  # Alert if >30% errors
    min_policies_warning: int = 0      # Alert if fewer policies found
    cost_spike_threshold: float = 2.0  # Alert if cost > 2x average
    stuck_timeout_minutes: int = 30    # Alert if no progress for 30min

    # Priority filtering
    min_priority: NotificationPriority = NotificationPriority.LOW

    @classmethod
    def from_dict(cls, config: dict) -> "NotificationConfig":
        """Create config from dictionary (e.g., from YAML)."""
        # Handle priority conversion
        min_priority_str = config.get("min_priority", "low")
        min_priority = NotificationPriority(min_priority_str.lower())

        return cls(
            email_enabled=config.get("email_enabled", False),
            smtp_host=config.get("smtp_host", "smtp.gmail.com"),
            smtp_port=config.get("smtp_port", 587),
            smtp_username=config.get("smtp_username", ""),
            smtp_password=config.get("smtp_password", ""),
            smtp_use_tls=config.get("smtp_use_tls", True),
            from_email=config.get("from_email", ""),
            to_emails=config.get("to_emails", []),
            notify_on_success=config.get("notify_on_success", True),
            notify_on_error=config.get("notify_on_error", True),
            notify_on_warning=config.get("notify_on_warning", True),
            error_rate_threshold=config.get("error_rate_threshold", 0.3),
            min_policies_warning=config.get("min_policies_warning", 0),
            cost_spike_threshold=config.get("cost_spike_threshold", 2.0),
            stuck_timeout_minutes=config.get("stuck_timeout_minutes", 30),
            min_priority=min_priority,
        )


@dataclass
class Notification:
    """A notification to be sent."""
    type: NotificationType
    priority: NotificationPriority
    subject: str
    body: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: Optional[str] = None
    details: dict = field(default_factory=dict)

    def should_send(self, config: NotificationConfig) -> bool:
        """Check if this notification should be sent based on config."""
        # Check priority threshold
        priority_order = [
            NotificationPriority.LOW,
            NotificationPriority.MEDIUM,
            NotificationPriority.HIGH,
            NotificationPriority.CRITICAL,
        ]
        if priority_order.index(self.priority) < priority_order.index(config.min_priority):
            return False

        # Check notification type preferences
        if self.type == NotificationType.RUN_COMPLETE and not config.notify_on_success:
            return False
        if self.type == NotificationType.RUN_FAILED and not config.notify_on_error:
            return False
        if self.priority == NotificationPriority.MEDIUM and not config.notify_on_warning:
            return False

        return True


class EmailNotifier:
    """Handles sending email notifications."""

    def __init__(self, config: NotificationConfig):
        self.config = config

    def send(self, notification: Notification) -> bool:
        """
        Send an email notification.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.config.email_enabled:
            return False

        if not notification.should_send(self.config):
            return False

        if not self.config.to_emails:
            return False

        try:
            msg = self._create_message(notification)
            self._send_smtp(msg)
            return True
        except Exception as e:
            # Log but don't raise - notifications shouldn't break the main process
            print(f"[WARN] Failed to send email notification: {e}")
            return False

    def _create_message(self, notification: Notification) -> MIMEMultipart:
        """Create the email message."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = self._format_subject(notification)
        msg["From"] = self.config.from_email
        msg["To"] = ", ".join(self.config.to_emails)

        # Plain text version
        text_body = self._format_text_body(notification)
        msg.attach(MIMEText(text_body, "plain"))

        # HTML version
        html_body = self._format_html_body(notification)
        msg.attach(MIMEText(html_body, "html"))

        return msg

    def _format_subject(self, notification: Notification) -> str:
        """Format the email subject line."""
        priority_prefix = {
            NotificationPriority.LOW: "",
            NotificationPriority.MEDIUM: "[WARNING] ",
            NotificationPriority.HIGH: "[ERROR] ",
            NotificationPriority.CRITICAL: "[CRITICAL] ",
        }
        prefix = priority_prefix.get(notification.priority, "")
        return f"{prefix}OCP Policy Searcher: {notification.subject}"

    def _format_text_body(self, notification: Notification) -> str:
        """Format plain text email body."""
        lines = [
            f"OCP Heat Reuse Policy Searcher Notification",
            f"=" * 50,
            f"",
            f"Type: {notification.type.value}",
            f"Priority: {notification.priority.value.upper()}",
            f"Time: {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]

        if notification.run_id:
            lines.append(f"Run ID: {notification.run_id}")

        lines.extend([
            f"",
            f"-" * 50,
            f"",
            notification.body,
            f"",
        ])

        if notification.details:
            lines.append("-" * 50)
            lines.append("Details:")
            for key, value in notification.details.items():
                lines.append(f"  {key}: {value}")

        lines.extend([
            f"",
            f"-" * 50,
            f"This is an automated message from OCP Heat Reuse Policy Searcher.",
            f"To change notification settings, edit config/notifications.yaml",
        ])

        return "\n".join(lines)

    def _format_html_body(self, notification: Notification) -> str:
        """Format HTML email body."""
        priority_colors = {
            NotificationPriority.LOW: "#28a745",      # Green
            NotificationPriority.MEDIUM: "#ffc107",   # Yellow
            NotificationPriority.HIGH: "#dc3545",     # Red
            NotificationPriority.CRITICAL: "#721c24", # Dark red
        }
        color = priority_colors.get(notification.priority, "#333")

        details_html = ""
        if notification.details:
            details_rows = "".join(
                f"<tr><td style='padding: 5px; border-bottom: 1px solid #eee;'><strong>{k}</strong></td>"
                f"<td style='padding: 5px; border-bottom: 1px solid #eee;'>{v}</td></tr>"
                for k, v in notification.details.items()
            )
            details_html = f"""
            <h3 style='color: #333; margin-top: 20px;'>Details</h3>
            <table style='width: 100%; border-collapse: collapse;'>
                {details_rows}
            </table>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 20px; border-radius: 8px 8px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">OCP Heat Reuse Policy Searcher</h1>
            </div>

            <div style="background: #f8f9fa; padding: 20px; border: 1px solid #dee2e6; border-top: none;">
                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                    <span style="background: {color}; color: white; padding: 5px 12px; border-radius: 4px; font-weight: bold; text-transform: uppercase; font-size: 12px;">
                        {notification.priority.value}
                    </span>
                    <span style="margin-left: 10px; color: #666; font-size: 14px;">
                        {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
                    </span>
                </div>

                <h2 style="color: #333; margin-top: 0;">{notification.subject}</h2>

                {f'<p style="color: #666; font-size: 14px;">Run ID: <code>{notification.run_id}</code></p>' if notification.run_id else ''}

                <div style="background: white; padding: 15px; border-radius: 4px; border-left: 4px solid {color};">
                    <p style="margin: 0; white-space: pre-line;">{notification.body}</p>
                </div>

                {details_html}
            </div>

            <div style="background: #e9ecef; padding: 15px; border-radius: 0 0 8px 8px; text-align: center; font-size: 12px; color: #666;">
                This is an automated message from OCP Heat Reuse Policy Searcher.<br>
                To change notification settings, edit <code>config/notifications.yaml</code>
            </div>
        </body>
        </html>
        """

    def _send_smtp(self, msg: MIMEMultipart) -> None:
        """Send the email via SMTP."""
        context = ssl.create_default_context()

        if self.config.smtp_use_tls:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.config.smtp_username, self.config.smtp_password)
                server.sendmail(
                    self.config.from_email,
                    self.config.to_emails,
                    msg.as_string()
                )
        else:
            with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, context=context) as server:
                server.login(self.config.smtp_username, self.config.smtp_password)
                server.sendmail(
                    self.config.from_email,
                    self.config.to_emails,
                    msg.as_string()
                )


class NotificationManager:
    """Manages notifications across the application."""

    def __init__(self, config: Optional[NotificationConfig] = None):
        self.config = config or NotificationConfig()
        self.email_notifier = EmailNotifier(self.config) if config else None
        self._pending_notifications: list[Notification] = []

    def notify(self, notification: Notification) -> bool:
        """Send a notification immediately."""
        if not self.email_notifier:
            return False
        return self.email_notifier.send(notification)

    def queue(self, notification: Notification) -> None:
        """Queue a notification for later sending."""
        self._pending_notifications.append(notification)

    def send_queued(self) -> int:
        """Send all queued notifications. Returns count sent."""
        sent = 0
        for notification in self._pending_notifications:
            if self.notify(notification):
                sent += 1
        self._pending_notifications.clear()
        return sent

    def notify_run_complete(
        self,
        run_id: str,
        domains_scanned: int,
        policies_found: int,
        policies_new: int,
        duration_seconds: float,
        cost_usd: float,
    ) -> bool:
        """Send notification for successful run completion."""
        mins = int(duration_seconds // 60)
        secs = int(duration_seconds % 60)

        notification = Notification(
            type=NotificationType.RUN_COMPLETE,
            priority=NotificationPriority.LOW,
            subject="Scan Completed Successfully",
            body=f"""Your policy scan has completed successfully!

Scanned {domains_scanned} domains and found {policies_found} relevant policies ({policies_new} new).

The scan took {mins}m {secs}s and cost approximately ${cost_usd:.4f}.""",
            run_id=run_id,
            details={
                "Domains Scanned": domains_scanned,
                "Policies Found": policies_found,
                "New Policies": policies_new,
                "Duration": f"{mins}m {secs}s",
                "Estimated Cost": f"${cost_usd:.4f}",
            }
        )
        return self.notify(notification)

    def notify_run_failed(
        self,
        run_id: str,
        error_message: str,
        error_type: str = "Unknown",
    ) -> bool:
        """Send notification for failed run."""
        notification = Notification(
            type=NotificationType.RUN_FAILED,
            priority=NotificationPriority.HIGH,
            subject="Scan Failed",
            body=f"""Your policy scan has failed with an error.

Error Type: {error_type}
Error Message: {error_message}

Please check the logs for more details.""",
            run_id=run_id,
            details={
                "Error Type": error_type,
                "Error Message": error_message,
            }
        )
        return self.notify(notification)

    def notify_budget_warning(
        self,
        current_cost: float,
        budget: float,
        percentage: float,
    ) -> bool:
        """Send notification for budget warning."""
        priority = NotificationPriority.HIGH if percentage >= 100 else NotificationPriority.MEDIUM
        notif_type = NotificationType.BUDGET_EXCEEDED if percentage >= 100 else NotificationType.BUDGET_WARNING
        subject = "Budget Exceeded!" if percentage >= 100 else "Budget Warning"

        notification = Notification(
            type=notif_type,
            priority=priority,
            subject=subject,
            body=f"""Your Claude API spending has {"exceeded" if percentage >= 100 else "reached"} {percentage:.1f}% of your monthly budget.

Current Spend: ${current_cost:.2f}
Monthly Budget: ${budget:.2f}

{"Consider pausing scans or increasing your budget." if percentage < 100 else "Scans may be blocked until the budget is increased or reset."}""",
            details={
                "Current Spend": f"${current_cost:.2f}",
                "Monthly Budget": f"${budget:.2f}",
                "Usage": f"{percentage:.1f}%",
            }
        )
        return self.notify(notification)

    def notify_high_error_rate(
        self,
        run_id: str,
        error_rate: float,
        errors: int,
        total: int,
        threshold: float,
    ) -> bool:
        """Send notification for high error rate."""
        notification = Notification(
            type=NotificationType.HIGH_ERROR_RATE,
            priority=NotificationPriority.HIGH,
            subject="High Error Rate Detected",
            body=f"""Your scan is experiencing a high error rate.

Error Rate: {error_rate:.1%} ({errors}/{total} pages)
Threshold: {threshold:.1%}

This could indicate:
- Network connectivity issues
- Target sites blocking requests
- Rate limiting being applied
- Configuration problems

Consider investigating the cause before continuing.""",
            run_id=run_id,
            details={
                "Error Rate": f"{error_rate:.1%}",
                "Failed Pages": errors,
                "Total Pages": total,
                "Threshold": f"{threshold:.1%}",
            }
        )
        return self.notify(notification)

    def notify_cost_spike(
        self,
        run_id: str,
        current_cost: float,
        average_cost: float,
        multiplier: float,
    ) -> bool:
        """Send notification for cost spike."""
        notification = Notification(
            type=NotificationType.COST_SPIKE,
            priority=NotificationPriority.MEDIUM,
            subject="Cost Spike Detected",
            body=f"""This scan cost significantly more than average.

This Run Cost: ${current_cost:.4f}
Average Cost: ${average_cost:.4f}
Multiplier: {multiplier:.1f}x

This could be due to:
- More pages passing keyword filtering
- Longer page content being analyzed
- Scanning more domains than usual

Review the run to ensure this was expected.""",
            run_id=run_id,
            details={
                "This Run": f"${current_cost:.4f}",
                "Average": f"${average_cost:.4f}",
                "Multiplier": f"{multiplier:.1f}x",
            }
        )
        return self.notify(notification)

    def notify_no_policies(
        self,
        run_id: str,
        domains_scanned: int,
        pages_crawled: int,
    ) -> bool:
        """Send notification when no policies were found."""
        notification = Notification(
            type=NotificationType.NO_POLICIES_FOUND,
            priority=NotificationPriority.MEDIUM,
            subject="No Policies Found",
            body=f"""Your scan completed but found no relevant policies.

Domains Scanned: {domains_scanned}
Pages Crawled: {pages_crawled}

This could indicate:
- Keyword configuration needs adjustment
- Target sites have changed
- Relevance thresholds are too high
- All relevant policies were already found

Consider reviewing your configuration.""",
            run_id=run_id,
            details={
                "Domains Scanned": domains_scanned,
                "Pages Crawled": pages_crawled,
                "Policies Found": 0,
            }
        )
        return self.notify(notification)

    def notify_connection_errors(
        self,
        run_id: str,
        failed_domains: list[str],
        error_counts: dict[str, int],
    ) -> bool:
        """Send notification for connection errors."""
        domain_list = ", ".join(failed_domains[:5])
        if len(failed_domains) > 5:
            domain_list += f" (+{len(failed_domains) - 5} more)"

        error_summary = "\n".join(f"  - {err}: {count}" for err, count in error_counts.items())

        notification = Notification(
            type=NotificationType.CONNECTION_ERRORS,
            priority=NotificationPriority.HIGH,
            subject="Connection Errors Detected",
            body=f"""Multiple domains failed to connect during the scan.

Failed Domains: {domain_list}

Error Summary:
{error_summary}

These domains may be:
- Temporarily unavailable
- Blocking automated access
- Experiencing server issues

Consider manually checking these domains or adjusting retry settings.""",
            run_id=run_id,
            details={
                "Failed Domains": len(failed_domains),
                **error_counts,
            }
        )
        return self.notify(notification)

    def test_connection(self) -> tuple[bool, str]:
        """
        Test the email configuration by sending a test email.

        Returns:
            Tuple of (success, message)
        """
        if not self.config.email_enabled:
            return False, "Email notifications are disabled"

        if not self.config.to_emails:
            return False, "No recipient email addresses configured"

        try:
            notification = Notification(
                type=NotificationType.RUN_COMPLETE,
                priority=NotificationPriority.LOW,
                subject="Test Notification",
                body="This is a test notification to verify your email configuration is working correctly.",
                details={
                    "Test": "Successful",
                    "Configuration": "Valid",
                }
            )

            if self.email_notifier and self.email_notifier.send(notification):
                return True, f"Test email sent to {', '.join(self.config.to_emails)}"
            else:
                return False, "Failed to send test email"
        except Exception as e:
            return False, f"Error: {str(e)}"
