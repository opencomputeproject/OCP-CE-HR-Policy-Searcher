#!/usr/bin/env python3
"""OCP Heat Reuse Policy Searcher - Main entry point."""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config.loader import (
    load_settings,
    get_enabled_domains,
    get_available_domain_files,
    list_groups,
    list_domains,
    list_regions,
    warn_missing_regions,
    ConfigurationError,
    filter_domains,
    filter_domains_by_category,
    filter_domains_by_tag,
    filter_domains_by_policy_type,
    list_categories,
    list_tags,
    list_policy_types,
    get_domain_stats,
    load_rejected_sites,
    list_rejected_sites,
    is_url_rejected,
    VALID_CATEGORIES,
    VALID_TAGS,
    VALID_POLICY_TYPES,
    VALID_REGIONS,
)
from .analysis.url_filter import URLFilter, load_url_filters
from .cache.url_cache import URLCache, load_cache, save_cache, compute_content_hash
from .crawler.async_crawler import AsyncCrawler
from .analysis.keywords import KeywordMatcher
from .analysis.llm.client import (
    ClaudeClient,
    LLMError,
    LLMParseError,
    LLMAuthError,
    LLMRateLimitError,
    LLMContextTooLongError,
    LLMServiceError,
)
from .output.sheets import SheetsClient
from .logging.run_logger import (
    RunLogger,
    LogSection,
    RunStats,
    RunConfig,
    get_last_run_log,
    find_run_log,
    list_run_logs,
    load_run_log,
    format_last_run_summary,
    format_last_run_config,
)
from .models.crawl import PageStatus
from .models.policy import Policy, PolicyType
from .utils.chunking import split_into_chunks, get_chunk_by_spec, parse_chunk_spec
from .utils.costs import CostTracker, estimate_run_cost
from .utils.notifications import NotificationConfig, NotificationManager
from .utils.alerts import AlertManager, AlertThresholds, RunHealthMetrics


def parse_args():
    parser = argparse.ArgumentParser(
        description="Search for heat reuse policies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main --domains quick --dry-run    # Quick test scan
  python -m src.main --domains eu                 # Scan all EU domains
  python -m src.main reject-site --url URL        # Mark a site as rejected
  python -m src.main list-groups                  # Show available groups
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # reject-site subcommand
    reject_parser = subparsers.add_parser(
        "reject-site",
        help="Add a site to rejected sites"
    )
    reject_parser.add_argument("--url", required=True, help="URL of the rejected site")
    reject_parser.add_argument("--reason", required=True, help="Reason for rejection")
    reject_parser.add_argument("--evaluated-by", default=None, help="Your name (optional)")
    reject_parser.add_argument("--reconsider-if", default=None, help="Conditions to reconsider")
    reject_parser.add_argument("--replaced-by", default=None, help="Alternative domain ID if applicable")
    reject_parser.add_argument(
        "--file", default=None,
        help="Target file in config/rejected_sites/ (default: general.yaml)"
    )

    # list-rejected subcommand
    list_rejected_parser = subparsers.add_parser(
        "list-rejected",
        help="List all rejected sites"
    )
    list_rejected_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show full details including reasons"
    )

    # list-groups subcommand
    subparsers.add_parser("list-groups", help="List available domain groups")

    # list-domains subcommand
    subparsers.add_parser("list-domains", help="List all configured domains")

    # cost-history subcommand
    subparsers.add_parser("cost-history", help="Show Claude API cost history")

    # estimate-cost subcommand
    estimate_parser = subparsers.add_parser(
        "estimate-cost",
        help="Estimate cost for a planned scan"
    )
    estimate_parser.add_argument(
        "--domains", default="all",
        help="Domain group or file name to estimate (default: all)"
    )
    estimate_parser.add_argument(
        "--pages-per-domain", type=int, default=50,
        help="Estimated pages per domain (default: 50)"
    )

    # test-notifications subcommand
    subparsers.add_parser(
        "test-notifications",
        help="Test email notification configuration"
    )

    # alerts subcommand
    subparsers.add_parser(
        "alerts",
        help="Show current alert status and history"
    )

    # list-categories subcommand
    subparsers.add_parser(
        "list-categories",
        help="List available domain categories for filtering"
    )

    # list-tags subcommand
    subparsers.add_parser(
        "list-tags",
        help="List available domain tags for filtering"
    )

    # list-policy-types subcommand
    subparsers.add_parser(
        "list-policy-types",
        help="List available policy types for filtering"
    )

    # list-regions subcommand
    subparsers.add_parser(
        "list-regions",
        help="List available geographic regions for domain targeting"
    )

    # domain-stats subcommand
    subparsers.add_parser(
        "domain-stats",
        help="Show statistics about domain categorization"
    )

    # last-run subcommand
    last_run_parser = subparsers.add_parser(
        "last-run",
        help="Show summary and configuration of a run (default: most recent)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main last-run                    # Show most recent run
  python -m src.main last-run --log 2            # Show 2nd most recent run
  python -m src.main last-run --log 20260115     # Show run from specific date
  python -m src.main last-run --log run_20260115_143022  # Show specific run
  python -m src.main last-run -c                 # Show only configuration
"""
    )
    last_run_parser.add_argument(
        "--log", "-l", metavar="ID",
        help="Run to show: number (1=latest, 2=previous...), date (20260115), or run ID"
    )
    last_run_parser.add_argument(
        "--config-only", "-c", action="store_true",
        help="Show only the configuration (not the summary stats)"
    )
    last_run_parser.add_argument(
        "--summary-only", "-s", action="store_true",
        help="Show only the summary stats (not the configuration)"
    )

    # list-runs subcommand
    list_runs_parser = subparsers.add_parser(
        "list-runs",
        help="List recent run logs"
    )
    list_runs_parser.add_argument(
        "--all", "-a", action="store_true",
        help="Show all runs (default: last 10)"
    )

    # report subcommand
    report_parser = subparsers.add_parser(
        "report",
        help="Generate detailed run report with per-domain breakdown and suggestions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main report                            # Most recent run
  python -m src.main report --log 2                    # 2nd most recent
  python -m src.main report --log 20260203             # Run from date
  python -m src.main report --log run_20260203_164401  # Specific run ID
"""
    )
    report_parser.add_argument(
        "--log", "-l", metavar="ID",
        help="Run to report: number (1=latest, 2=previous...), date (20260115), or run ID"
    )

    # Main scan arguments (default command)
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--domains", default="all", help="Domain group, region, file name, or domain ID to scan (use 'list-groups' to see options)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Sheets")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM analysis")
    parser.add_argument("--verbose", "-v", action="store_true")

    # Cache options
    parser.add_argument("--no-cache", action="store_true", help="Disable URL result caching")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache before running")

    # Keyword filtering options (override config/keywords.yaml for this run)
    parser.add_argument(
        "--min-keyword-score", type=float, default=None,
        help="Minimum keyword score to pass to LLM (default: from keywords.yaml)"
    )
    parser.add_argument(
        "--require-combinations", type=str, choices=["true", "false"], default=None,
        help="Enable/disable required keyword combinations (default: from keywords.yaml)"
    )
    parser.add_argument(
        "--min-density", type=float, default=None,
        help="Minimum keyword density (matches per 1000 chars, default: from keywords.yaml)"
    )

    # Summary options
    parser.add_argument(
        "--verbose-summary", action="store_true",
        help="Show detailed run configuration in summary"
    )

    # Category/tag filtering options
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter by category (use 'list-categories' to see options)"
    )
    parser.add_argument(
        "--tag",
        type=str,
        action="append",
        dest="tags",
        help="Filter by tag (can be used multiple times, matches ANY tag)"
    )
    parser.add_argument(
        "--policy-type",
        type=str,
        action="append",
        dest="policy_types",
        help="Filter by policy type (can be used multiple times)"
    )
    parser.add_argument(
        "--match-all-tags",
        action="store_true",
        help="Require ALL specified tags (default: match ANY)"
    )

    # Chunking options
    parser.add_argument(
        "--chunk-size", type=int, default=None,
        help="Auto-chunk: process N domains at a time with pauses between batches"
    )
    parser.add_argument(
        "--chunk", type=str, default=None,
        help="Manual chunk: run specific chunk N/M (e.g., '2/4' for chunk 2 of 4)"
    )
    parser.add_argument(
        "--chunk-delay", type=int, default=30,
        help="Seconds to pause between chunks (default: 30)"
    )

    return parser.parse_args()


def cmd_reject_site(args) -> int:
    """Add a site to the rejected sites directory."""
    rejected_dir = Path("config/rejected_sites")

    # Determine target file
    target_filename = args.file if args.file else "general.yaml"
    if not target_filename.endswith(".yaml"):
        target_filename += ".yaml"

    # Handle subdirectories in the filename (e.g., "uk/evaluated.yaml")
    rejected_file = rejected_dir / target_filename

    # Create directory structure if needed
    rejected_file.parent.mkdir(parents=True, exist_ok=True)

    # Check if URL already exists anywhere in rejected sites
    try:
        if is_url_rejected(args.url):
            print(f"URL already in rejected sites: {args.url}")
            return 1
    except Exception:
        pass  # If we can't load, continue anyway

    # Load existing file or create new
    if rejected_file.exists():
        with open(rejected_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Initialize rejected_sites list if needed
    if "rejected_sites" not in data or data["rejected_sites"] is None:
        data["rejected_sites"] = []

    # Create new entry
    entry = {
        "url": args.url,
        "evaluated_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reason": args.reason,
    }

    if args.evaluated_by:
        entry["evaluated_by"] = args.evaluated_by
    if args.reconsider_if:
        entry["reconsider_if"] = args.reconsider_if
    if args.replaced_by:
        entry["replaced_by"] = args.replaced_by

    # Add to list
    data["rejected_sites"].append(entry)

    # Write back
    with open(rejected_file, "w", encoding="utf-8") as f:
        # Write YAML content
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Added to rejected sites: {args.url}")
    print(f"  File: {rejected_file}")
    print(f"  Reason: {args.reason}")
    return 0


def cmd_list_rejected(args) -> int:
    """List all rejected sites."""
    try:
        rejected = list_rejected_sites()

        if not rejected:
            print("\nNo rejected sites found.")
            print("Add sites with: python -m src.main reject-site --url URL --reason REASON")
            return 0

        print(f"\nRejected sites ({len(rejected)} total):\n")

        if args.verbose:
            # Verbose output with full details
            for site in rejected:
                print(f"  URL: {site['url']}")
                print(f"    Reason: {site['reason']}")
                if site['evaluated_date']:
                    print(f"    Date: {site['evaluated_date']}")
                if site['evaluated_by']:
                    print(f"    By: {site['evaluated_by']}")
                if site['reconsider_if']:
                    print(f"    Reconsider if: {site['reconsider_if']}")
                if site['source_file']:
                    print(f"    Source: {site['source_file']}")
                print()
        else:
            # Compact output
            print(f"  {'URL':<60} {'Reason':<30} {'File'}")
            print(f"  {'-'*60} {'-'*30} {'-'*20}")
            for site in rejected:
                url = site['url'][:58] + ".." if len(site['url']) > 60 else site['url']
                reason = site['reason'][:28] + ".." if len(site['reason']) > 30 else site['reason']
                source = site['source_file'][:18] + ".." if len(site['source_file']) > 20 else site['source_file']
                print(f"  {url:<60} {reason:<30} {source}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_list_groups(args) -> int:
    """List available domain groups, regions, and file names."""
    try:
        _, domains_config, _ = load_settings()
        groups = list_groups(domains_config)
        all_domains = domains_config.get("domains", [])

        print("\nAvailable domain groups:\n")
        print(f"  {'Group':<20} {'Description'}")
        print(f"  {'-'*20} {'-'*50}")

        for name, desc in sorted(groups.items()):
            # Count how many extra domains the region field adds
            group_ids = set(
                domains_config.get("groups", {}).get(name, {}).get("domains", [])
            )
            region_ids = {
                d["id"] for d in all_domains
                if name in d.get("region", [])
            }
            region_only = region_ids - group_ids
            suffix = f"  (+{len(region_only)} via region)" if region_only else ""
            print(f"  {name:<20} {desc}{suffix}")

        # Show regions that aren't group names
        regions = list_regions()
        region_only_names = {r for r in regions if r not in groups}
        if region_only_names:
            print("\nGeographic regions (also usable with --domains):\n")
            print(f"  {'Region':<20} {'Domains':<10} {'Description'}")
            print(f"  {'-'*20} {'-'*10} {'-'*40}")
            for name in sorted(region_only_names):
                count = len([
                    d for d in all_domains
                    if name in d.get("region", []) and d.get("enabled", True)
                ])
                print(f"  {name:<20} {count:<10} {regions[name]}")

        # Show domain files that aren't already group names
        file_counts = get_available_domain_files(domains_config)
        file_only = {f: c for f, c in file_counts.items() if f not in groups}
        if file_only:
            print("\nDomain files (also usable with --domains):\n")
            print(f"  {'File':<20} {'Domains'}")
            print(f"  {'-'*20} {'-'*10}")
            for name, count in sorted(file_only.items()):
                print(f"  {name:<20} {count} domain{'s' if count != 1 else ''}")

        print("\nUsage: python -m src.main --domains <group_or_region_or_file>")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_list_domains(args) -> int:
    """List all configured domains."""
    try:
        _, domains_config, _ = load_settings()
        domains = domains_config.get("domains", [])

        print(f"\nConfigured domains ({len(domains)} total):\n")
        print(f"  {'ID':<25} {'Enabled':<10} {'Name'}")
        print(f"  {'-'*25} {'-'*10} {'-'*40}")

        for d in sorted(domains, key=lambda x: x["id"]):
            enabled = "Yes" if d.get("enabled", True) else "No"
            print(f"  {d['id']:<25} {enabled:<10} {d['name'][:40]}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_cost_history(args) -> int:
    """Show Claude API cost history."""
    try:
        tracker = CostTracker()
        history = tracker.get_history()

        if not history.runs:
            print("\nNo cost history found.")
            print("Run a scan with LLM analysis to start tracking costs.")
            return 0

        print(history.format_summary())

        # Check for budget warnings
        warning = tracker.check_budget_warning(monthly_budget=50.0)
        if warning:
            print(f"\n  WARNING: {warning}\n")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_estimate_cost(args) -> int:
    """Estimate cost for a planned scan."""
    try:
        _, domains_config, _ = load_settings()
        domains = get_enabled_domains(domains_config, args.domains)
        domain_count = len(domains)

        pages_per_domain = getattr(args, 'pages_per_domain', 50)

        estimate = estimate_run_cost(
            domains=domain_count,
            pages_per_domain=pages_per_domain,
        )

        print(f"""
{'='*60}
  COST ESTIMATE
{'='*60}

  Domain group:        {args.domains}
  Domains to scan:     {estimate['domains']}
  Est. pages to crawl: {estimate['estimated_pages']:,}
  Est. pages analyzed: {estimate['estimated_analyzed']:,}

  Model:               {estimate['model']}
  Est. input tokens:   {estimate['estimated_input_tokens']:,}
  Est. output tokens:  {estimate['estimated_output_tokens']:,}

  ESTIMATED COST:      ${estimate['estimated_cost_usd']:.2f}

{'='*60}

  Note: Actual costs depend on keyword filter pass rate
        and content length. This estimate assumes 10%
        of pages pass keyword filtering.
""")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def load_notification_config() -> NotificationConfig:
    """Load notification configuration from config file."""
    config_path = Path("config/notifications.yaml")
    if not config_path.exists():
        return NotificationConfig()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        email_config = data.get("email", {})
        prefs = data.get("preferences", {})
        thresholds = data.get("thresholds", {})

        return NotificationConfig(
            email_enabled=email_config.get("enabled", False),
            smtp_host=email_config.get("smtp_host", "smtp.gmail.com"),
            smtp_port=email_config.get("smtp_port", 587),
            smtp_username=email_config.get("smtp_username", ""),
            smtp_password=email_config.get("smtp_password", ""),
            smtp_use_tls=email_config.get("smtp_use_tls", True),
            from_email=email_config.get("from_email", ""),
            to_emails=email_config.get("to_emails", []),
            notify_on_success=prefs.get("notify_on_success", True),
            notify_on_error=prefs.get("notify_on_error", True),
            notify_on_warning=prefs.get("notify_on_warning", True),
            error_rate_threshold=thresholds.get("error_rate_warning", 0.2),
            cost_spike_threshold=thresholds.get("cost_spike_multiplier", 2.0),
            stuck_timeout_minutes=thresholds.get("stuck_timeout_minutes", 30),
        )
    except Exception:
        return NotificationConfig()


def load_alert_thresholds() -> AlertThresholds:
    """Load alert thresholds from config file."""
    config_path = Path("config/notifications.yaml")
    if not config_path.exists():
        return AlertThresholds()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        thresholds = data.get("thresholds", {})
        return AlertThresholds.from_dict(thresholds)
    except Exception:
        return AlertThresholds()


def cmd_test_notifications(args) -> int:
    """Test notification configuration by sending a test email."""
    print("\n" + "=" * 60)
    print("  NOTIFICATION TEST")
    print("=" * 60 + "\n")

    config = load_notification_config()

    if not config.email_enabled:
        print("  [!] Email notifications are DISABLED")
        print("      Edit config/notifications.yaml to enable them")
        print("")
        return 1

    print(f"  Email Configuration:")
    print(f"    SMTP Host:     {config.smtp_host}:{config.smtp_port}")
    print(f"    From:          {config.from_email or '(not set)'}")
    print(f"    To:            {', '.join(config.to_emails) or '(not set)'}")
    print(f"    TLS:           {'Yes' if config.smtp_use_tls else 'No'}")
    print("")

    if not config.to_emails:
        print("  [!] No recipient emails configured")
        print("      Add emails to config/notifications.yaml")
        return 1

    if not config.smtp_username or not config.smtp_password:
        print("  [!] SMTP credentials not configured")
        print("      Set smtp_username and smtp_password in config/notifications.yaml")
        return 1

    print("  Sending test email...")

    manager = NotificationManager(config)
    success, message = manager.test_connection()

    if success:
        print(f"  [OK] {message}")
        print("")
        print("=" * 60 + "\n")
        return 0
    else:
        print(f"  [FAILED] {message}")
        print("")
        print("=" * 60 + "\n")
        return 1


def cmd_alerts(args) -> int:
    """Show current alert status and history."""
    alert_manager = AlertManager(load_alert_thresholds())
    print(alert_manager.format_summary())

    # Show recent alerts from history
    history_file = Path("logs/alert_history.json")
    if history_file.exists():
        try:
            import json
            with open(history_file, "r") as f:
                history = json.load(f)

            if history:
                print("  Recent Alerts (last 10):")
                print("  " + "-" * 56)
                for alert in history[-10:]:
                    severity = alert.get("severity", "unknown").upper()
                    alert_type = alert.get("alert_type", "unknown")
                    timestamp = alert.get("timestamp", "")[:19]  # Trim to datetime
                    print(f"  [{severity:8}] {timestamp} - {alert_type}")
                print("")
        except Exception:
            pass

    return 0


def cmd_list_categories(args) -> int:
    """List available domain categories."""
    print("\n" + "=" * 60)
    print("  DOMAIN CATEGORIES")
    print("=" * 60 + "\n")
    print("  Use --category <name> to filter domains by category.\n")

    categories = list_categories()
    for cat, desc in sorted(categories.items()):
        print(f"  {cat:20} - {desc}")

    print("\n" + "=" * 60 + "\n")
    return 0


def cmd_list_tags(args) -> int:
    """List available domain tags."""
    print("\n" + "=" * 60)
    print("  DOMAIN TAGS")
    print("=" * 60 + "\n")
    print("  Use --tag <name> to filter domains (can use multiple times).\n")

    tags = list_tags()
    for tag, desc in sorted(tags.items()):
        print(f"  {tag:12} - {desc}")

    print("\n" + "=" * 60 + "\n")
    return 0


def cmd_list_policy_types(args) -> int:
    """List available policy types."""
    print("\n" + "=" * 60)
    print("  POLICY TYPES")
    print("=" * 60 + "\n")
    print("  Use --policy-type <name> to filter domains.\n")

    policy_types = list_policy_types()
    for pt, desc in sorted(policy_types.items()):
        print(f"  {pt:12} - {desc}")

    print("\n" + "=" * 60 + "\n")
    return 0


def cmd_list_regions(args) -> int:
    """List available geographic regions."""
    try:
        _, domains_config, _ = load_settings()
        all_domains = domains_config.get("domains", [])
        enabled = [d for d in all_domains if d.get("enabled", True)]

        print("\n" + "=" * 60)
        print("  GEOGRAPHIC REGIONS")
        print("=" * 60 + "\n")
        print("  Use --domains <region> to target domains by region.\n")

        regions = list_regions()
        for name, desc in sorted(regions.items()):
            count = len([d for d in enabled if name in d.get("region", [])])
            print(f"  {name:12} ({count:2} domains) - {desc}")

        # Show domains without a region
        no_region = [d for d in enabled if not d.get("region")]
        if no_region:
            print(f"\n  WARNING: {len(no_region)} enabled domain(s) have no region:")
            for d in no_region:
                print(f"    - {d['id']} (from {d.get('_source_file', 'unknown')}.yaml)")

        print("\n" + "=" * 60 + "\n")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_domain_stats(args) -> int:
    """Show statistics about domain categorization."""
    _, domains_config, _ = load_settings()
    stats = get_domain_stats(domains_config)

    print("\n" + "=" * 60)
    print("  DOMAIN CATEGORIZATION STATS")
    print("=" * 60 + "\n")

    print(f"  Total domains:    {stats['total_domains']}")
    print(f"  Enabled domains:  {stats['enabled_domains']}")

    print("\n  By Region:")
    print("  " + "-" * 40)
    if stats['by_region']:
        for region, count in sorted(stats['by_region'].items(), key=lambda x: -x[1]):
            print(f"    {region:24} {count:3}")
    else:
        print("    (no regions assigned yet)")

    print("\n  By Category:")
    print("  " + "-" * 40)
    if stats['by_category']:
        for cat, count in sorted(stats['by_category'].items(), key=lambda x: -x[1]):
            print(f"    {cat:24} {count:3}")
    else:
        print("    (no domains categorized yet)")

    print("\n  By Tag:")
    print("  " + "-" * 40)
    if stats['by_tag']:
        for tag, count in sorted(stats['by_tag'].items(), key=lambda x: -x[1]):
            print(f"    {tag:24} {count:3}")
    else:
        print("    (no domains tagged yet)")

    print("\n  By Policy Type:")
    print("  " + "-" * 40)
    if stats['by_policy_type']:
        for pt, count in sorted(stats['by_policy_type'].items(), key=lambda x: -x[1]):
            print(f"    {pt:24} {count:3}")
    else:
        print("    (no policy types assigned yet)")

    print("\n" + "=" * 60 + "\n")
    return 0


def _safe_print(text: str) -> None:
    """Print text, handling Windows console encoding issues."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace unencodable characters for console display
        print(text.encode('ascii', errors='replace').decode('ascii'))


def cmd_last_run(args) -> int:
    """Show summary and configuration of a run (default: most recent)."""
    log_pattern = getattr(args, 'log', None)

    # Find the log file
    if log_pattern:
        log_file = find_run_log(log_pattern)
        if not log_file:
            print(f"\nNo run log found matching: {log_pattern}")
            print("")
            print("Use one of these formats:")
            print("  --log 1              # Most recent run")
            print("  --log 2              # Second most recent run")
            print("  --log 20260115       # Run from specific date")
            print("  --log run_20260115_143022  # Full run ID")
            print("")
            print("Use 'list-runs' to see available runs:")
            print("  python -m src.main list-runs")
            print("")
            return 1
    else:
        log_file = get_last_run_log()
        if not log_file:
            print("\nNo run logs found.")
            print("Run a scan first: python -m src.main --domains quick --dry-run")
            print("")
            return 1

    # Extract run ID from filename (e.g., run_20260116_034018.json -> run_20260116_034018)
    run_id = log_file.stem

    # Load the run data
    run_data = load_run_log(log_file)
    if not run_data:
        print(f"\nCould not read run data from: {log_file}")
        print("The log file may be corrupted or incomplete.")
        print("")
        return 1

    config_only = getattr(args, 'config_only', False)
    summary_only = getattr(args, 'summary_only', False)

    # Default: show both summary and config
    show_summary = not config_only
    show_config = not summary_only

    # Print summary if requested
    if show_summary:
        _safe_print(format_last_run_summary(run_data, run_id))

    # Print configuration if available and requested
    config = run_data.get("config")
    if show_config:
        if config:
            _safe_print(format_last_run_config(config, run_data))
        else:
            # No config saved (older run or --verbose-summary wasn't used)
            if not show_summary:
                # Only show this message if we're not showing summary
                print("\nNo configuration data available for this run.")
                print("Configuration is saved when running with --verbose-summary.")
                print(f"\nRun ID: {run_id}")
                print(f"Log file: {log_file}")
                print("")
            else:
                print("\n  Note: Configuration not saved for this run.")
                print("  Use --verbose-summary on your next run to save configuration.")
                print("")

    return 0


def cmd_list_runs(args) -> int:
    """List recent run logs with summary info."""
    from datetime import datetime

    show_all = getattr(args, 'all', False)
    limit = 0 if show_all else 10

    runs = list_run_logs(limit=limit)

    if not runs:
        print("\nNo run logs found.")
        print("Run a scan first: python -m src.main --domains quick --dry-run")
        print("")
        return 1

    print("")
    print("=" * 78)
    print("  AVAILABLE RUN LOGS")
    print("=" * 78)
    print("")
    print(f"  {'#':<3} {'Run ID':<24} {'Date':<12} {'Domains':<8} {'Policies':<9} {'Cost':<8}")
    print("  " + "-" * 72)

    for idx, log_file, summary in runs:
        run_id = log_file.stem

        # Parse timestamp
        timestamp = summary.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                date_str = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                date_str = timestamp[:10] if len(timestamp) >= 10 else "?"
        else:
            date_str = "?"

        domains = summary.get("domains_scanned", 0)
        policies = summary.get("policies_found", 0)
        cost = summary.get("estimated_cost_usd", 0)

        # Format nicely
        cost_str = f"${cost:.4f}" if cost > 0 else "-"
        domains_str = str(domains) if domains > 0 else "-"
        policies_str = str(policies) if policies > 0 else "-"

        print(f"  {idx:<3} {run_id:<24} {date_str:<12} {domains_str:<8} {policies_str:<9} {cost_str:<8}")

    print("")
    print("  Usage: python -m src.main last-run --log <#>")
    print("  Example: python -m src.main last-run --log 2")
    print("")

    if not show_all and len(runs) >= 10:
        print("  (showing last 10 runs - use --all to see all)")
        print("")

    return 0


def cmd_report(args) -> int:
    """Generate detailed run report with per-domain breakdown."""
    import json as _json
    from .reporting.run_report import load_run_events, parse_run_events, format_report

    log_pattern = getattr(args, 'log', None)

    if log_pattern:
        log_file = find_run_log(log_pattern)
        if not log_file:
            print(f"\nNo run log found matching: {log_pattern}")
            print("")
            print("Use one of these formats:")
            print("  --log 1              # Most recent run")
            print("  --log 2              # Second most recent run")
            print("  --log 20260115       # Run from specific date")
            print("  --log run_20260115_143022  # Full run ID")
            print("")
            print("Use 'list-runs' to see available runs:")
            print("  python -m src.main list-runs")
            print("")
            return 1
    else:
        log_file = get_last_run_log()
        if not log_file:
            print("\nNo run logs found.")
            print("Run a scan first: python -m src.main --domains quick --dry-run")
            print("")
            return 1

    run_id = log_file.stem

    try:
        events = load_run_events(log_file)
    except (_json.JSONDecodeError, IOError) as e:
        print(f"\nError reading log file: {e}")
        return 1

    report = parse_run_events(events, run_id)
    output = format_report(report)
    _safe_print(output)
    return 0


def _short_url(url: str, max_len: int = 45) -> str:
    """Extract URL path and truncate for display.

    Args:
        url: Full URL string
        max_len: Maximum length of returned string

    Returns:
        URL path, truncated with '..' if too long
    """
    from urllib.parse import urlparse
    try:
        path = urlparse(url).path
    except Exception:
        path = url
    if len(path) > max_len:
        return path[:max_len - 2] + ".."
    return path


async def run_batch(
    domains: list,
    settings,
    keyword_matcher,
    claude_client,
    sheets_client,
    logger,
    args,
    url_filter: URLFilter = None,
    url_cache: URLCache = None,
) -> tuple[list, list]:
    """
    Run a single batch of domains.

    Returns:
        Tuple of (crawl_results, policies)
    """
    verbose = getattr(args, 'verbose', False)

    # Crawl
    skip_exts = url_filter.config.skip_extensions if url_filter else None
    crawl_blocked = url_filter.config.crawl_blocked_patterns if url_filter else None
    crawler = AsyncCrawler(settings.crawl, domains, keyword_matcher, logger, skip_exts, crawl_blocked)
    crawl_results = await crawler.crawl_all()
    logger.info(f"Crawled {len(crawl_results)} pages")

    # Analyze
    policies = []
    urls_filtered = 0
    keywords_passed = 0
    cache_hits = 0
    cache_skipped_not_relevant = 0

    # Verbose collection lists
    if verbose:
        filtered_details = []       # (url, FilterResult)
        blocked_details = []        # (url, status_value, error_message, used_playwright)
        kw_passed_details = []      # (url, KeywordMatchResult)
        kw_failed_reasons = {}      # reason -> count
        kw_near_misses = []         # (url, KeywordMatchResult, reason)
        screening_details = []      # (url, ScreeningResult, passed)
        analysis_details = []       # (url, PolicyAnalysis, accepted)

        # Near-miss threshold: 60% of min score
        min_score = keyword_matcher.thresholds.get("minimum_keyword_score", 5.0)
        near_miss_threshold = min_score * 0.6

    for result in crawl_results:
        if not result.is_success:
            if verbose and result.is_blocked:
                blocked_details.append((
                    result.url, result.status.value,
                    result.error_message or "unknown", result.used_playwright,
                ))
            continue

        # URL pre-filtering (skip obviously irrelevant URLs before LLM)
        if url_filter:
            filter_result = url_filter.check_url(result.url)
            if filter_result.should_skip:
                urls_filtered += 1
                if verbose:
                    filtered_details.append((result.url, filter_result))
                continue

        # Keyword check (with stricter requirements)
        content = result.content or ""
        kw_result = keyword_matcher.match(content)
        if not keyword_matcher.is_relevant(kw_result, len(content)):
            if verbose:
                reason = keyword_matcher.get_failure_reason(kw_result, len(content))
                kw_failed_reasons[reason] = kw_failed_reasons.get(reason, 0) + 1
                # Track near-misses: pages with score >= 60% of threshold
                if kw_result.final_score >= near_miss_threshold and len(kw_near_misses) < 15:
                    kw_near_misses.append((result.url, kw_result, reason))
            continue

        keywords_passed += 1
        if verbose:
            kw_passed_details.append((result.url, kw_result))

        # Check URL cache before LLM analysis
        content_hash = compute_content_hash(content) if url_cache else ""
        if url_cache:
            cache_entry = url_cache.get(result.url, content_hash=content_hash)
            if cache_entry:
                cache_hits += 1
                if not cache_entry.is_relevant:
                    # Previously analyzed as not relevant - skip
                    cache_skipped_not_relevant += 1
                    continue
                # Previously relevant - still need to process for policy extraction
                # (We don't cache full policy data, just relevance)

        # LLM analysis
        if claude_client:
            try:
                # Two-stage analysis: Haiku screening -> Sonnet extraction
                if settings.analysis.enable_two_stage:
                    screening = await claude_client.screen_relevance(
                        content,
                        result.url,
                        screening_model=settings.analysis.screening_model,
                        min_confidence=settings.analysis.screening_min_confidence,
                    )
                    screening_passed = screening.relevant and screening.confidence >= settings.analysis.screening_min_confidence
                    if verbose:
                        screening_details.append((result.url, screening, screening_passed))
                    if not screening_passed:
                        # Screened out - cache as not relevant and skip
                        if url_cache:
                            url_cache.set(
                                result.url,
                                is_relevant=False,
                                relevance_score=screening.confidence,
                                content_hash=content_hash,
                            )
                        continue

                # Full analysis with Sonnet
                analysis = await claude_client.analyze_policy(
                    result.content[:settings.analysis.max_content_length],
                    result.url,
                    result.language,
                )

                # Cache the analysis result
                if url_cache:
                    url_cache.set(
                        result.url,
                        is_relevant=analysis.is_relevant,
                        relevance_score=analysis.relevance_score,
                        content_hash=content_hash,
                        policy_type=analysis.policy_type if analysis.is_relevant else "",
                    )

                accepted = analysis.is_relevant and analysis.relevance_score >= settings.analysis.min_relevance_score
                if verbose:
                    analysis_details.append((result.url, analysis, accepted))

                if accepted:
                    policy = claude_client.to_policy(analysis, result.url, result.language or "unknown")
                    if policy:
                        policies.append(policy)
                        logger.success(f"Policy: {policy.policy_name}")

            except LLMAuthError as e:
                # Authentication failed - this is fatal
                logger.error(f"Authentication failed: {e}")
                logger.error("Check your ANTHROPIC_API_KEY environment variable")
                raise  # Re-raise to stop the run

            except LLMRateLimitError as e:
                # Rate limited even after retries
                logger.warning(f"Rate limited for {result.url}: {e}")
                if e.retry_after:
                    logger.info(f"  Suggested wait: {e.retry_after:.0f}s")

            except LLMContextTooLongError as e:
                # Content too long even after truncation
                logger.warning(f"Content too long for {result.url}: {e.content_length} chars")

            except LLMParseError as e:
                # Parse/validation errors
                logger.warning(f"LLM parse error for {result.url}: {e}")
                if verbose and e.raw_response:
                    logger.info(f"  Raw response: {e.raw_response[:200]}...")

            except LLMServiceError as e:
                # Service unavailable
                logger.warning(f"Service error for {result.url}: {e}")
                if e.status_code:
                    logger.info(f"  Status code: {e.status_code}")

            except LLMError as e:
                # Other LLM errors
                logger.warning(f"LLM error for {result.url}: {e}")

            except Exception as e:
                # Unexpected errors
                logger.warning(f"Unexpected error for {result.url}: {type(e).__name__}: {e}")
        else:
            # Keyword-only mode
            policy = Policy(
                url=result.url,
                policy_name=result.title or "Unknown",
                jurisdiction="Unknown",
                policy_type=PolicyType.UNKNOWN,
                summary="Keyword match - needs review",
                relevance_score=int(kw_result.score),
                source_language=result.language or "unknown",
            )
            policies.append(policy)

    # Log URL filter stats if any URLs were filtered
    if urls_filtered > 0:
        logger.info(f"URL pre-filter: skipped {urls_filtered} URLs")

    # Log keyword check stats
    success_count = sum(1 for r in crawl_results if r.is_success)
    after_filter = success_count - urls_filtered
    logger.info(f"Keywords: {keywords_passed}/{after_filter} pages passed stricter check")

    # Log cache stats
    if url_cache and cache_hits > 0:
        logger.info(f"Cache: {cache_hits} hits, {cache_skipped_not_relevant} skipped (not relevant)")

    # Log screening stats if two-stage was used
    if claude_client and settings.analysis.enable_two_stage:
        screening_stats = claude_client.get_screening_stats()
        if screening_stats["calls"] > 0:
            logger.info(
                f"Screening: {screening_stats['calls']} calls, "
                f"{screening_stats['tokens_input']} input tokens"
            )

    # ── Verbose output blocks ──────────────────────────────────────────
    if verbose:
        # URL pre-filter details
        if filtered_details:
            logger.info(f"URL pre-filter: skipped {len(filtered_details)} URLs (details)")
            for url, fr in filtered_details:
                reason_str = fr.reason or fr.rule_type or "unknown"
                logger.detail(f"{_short_url(url):<47} -> {reason_str}")

        # Blocked pages details
        if blocked_details:
            logger.info(f"Blocked pages: {len(blocked_details)} (details)")
            # Group by status
            by_status: dict[str, list] = {}
            for url, status_val, msg, pw in blocked_details:
                by_status.setdefault(status_val, []).append((url, msg, pw))
            for status_val, entries in by_status.items():
                logger.detail(f"{status_val.upper()} ({len(entries)}):")
                for url, msg, pw in entries:
                    pw_note = " [playwright]" if pw else ""
                    logger.detail(f"  {_short_url(url):<45} {msg}{pw_note}")

            # Actionable suggestions
            suggestions = []
            cf_count = sum(1 for _, _, m, pw in blocked_details if "cloudflare" in m.lower() and not pw)
            if cf_count:
                suggestions.append(
                    f"Cloudflare bot protection ({cf_count} pages): "
                    "try requires_playwright: true in domain config"
                )
            cf_pw_count = sum(1 for _, _, m, pw in blocked_details if "cloudflare" in m.lower() and pw)
            if cf_pw_count:
                suggestions.append(
                    f"Cloudflare blocking Playwright too ({cf_pw_count} pages): "
                    "site may block headless browsers -- flag for manual review"
                )
            captcha_count = sum(1 for _, sv, _, _ in blocked_details if sv == "captcha")
            if captcha_count:
                suggestions.append(
                    f"CAPTCHA ({captcha_count} pages): requires human review"
                )
            rl_count = sum(1 for _, sv, _, _ in blocked_details if sv == "rate_limited")
            if rl_count:
                suggestions.append(
                    f"Rate limited ({rl_count} pages): "
                    "try increasing rate_limit_seconds in domain config"
                )
            if suggestions:
                logger.detail("")
                logger.detail("Suggestions:")
                for s in suggestions:
                    logger.detail(f"  {s}")

        # Keyword filtering details
        kw_min_score = keyword_matcher.thresholds.get("minimum_keyword_score", 5.0)
        kw_min_matches = keyword_matcher.thresholds.get("minimum_matches", 2)
        combo_cfg = keyword_matcher.stricter.get("required_combinations", {})
        combo_enabled = combo_cfg.get("enabled", False)

        logger.info(f"Keywords: {keywords_passed}/{after_filter} pages passed (details)")
        logger.detail(
            f"Thresholds: score>={kw_min_score}  matches>={kw_min_matches}  "
            f"combinations={'required' if combo_enabled else 'disabled'}"
        )

        if kw_passed_details:
            logger.detail("")
            logger.detail(f"PASSED ({len(kw_passed_details)}):")
            for url, kr in kw_passed_details:
                cats = ",".join(sorted(kr.categories_matched))
                boost_str = f"  boost=+{kr.boost_applied}" if kr.boost_applied > 0 else ""
                penalty_str = f"  penalty=-{kr.penalty_applied}" if kr.penalty_applied > 0 else ""
                logger.detail(
                    f"  {_short_url(url):<45} score={kr.final_score:<5.1f} "
                    f"matches={kr.unique_matches}  cats={{{cats}}}{boost_str}{penalty_str}"
                )

        if kw_failed_reasons:
            logger.detail("")
            logger.detail("FAILED by reason:")
            for reason, count in sorted(kw_failed_reasons.items(), key=lambda x: -x[1]):
                logger.detail(f"  {reason:<45} {count} pages")

        if kw_near_misses:
            logger.detail("")
            logger.detail(f"Near misses (score>={near_miss_threshold:.1f}, {len(kw_near_misses)} pages):")
            for url, kr, reason in kw_near_misses:
                cats = ",".join(sorted(kr.categories_matched)) if kr.categories_matched else "none"
                logger.detail(
                    f"  {_short_url(url):<45} score={kr.final_score:<5.1f} "
                    f"matches={kr.unique_matches}  cats={{{cats}}}  [{reason}]"
                )

        # Screening details
        if screening_details:
            logger.info(f"Screening: {len(screening_details)} pages (details)")
            for url, sr, passed in screening_details:
                status = "PASS" if passed else "FAIL"
                threshold_note = "" if passed else f"  [below threshold {settings.analysis.screening_min_confidence}]"
                logger.detail(
                    f"  {status} {_short_url(url):<43} confidence={sr.confidence}{threshold_note}"
                )

        # Analysis details
        if analysis_details:
            logger.info(f"Analysis: {len(analysis_details)} pages (details)")
            for url, ar, accepted in analysis_details:
                status = "PASS" if accepted else "FAIL"
                explanation = ""
                if hasattr(ar, 'relevance_explanation') and ar.relevance_explanation:
                    explanation = f'  "{ar.relevance_explanation[:60]}"'
                logger.detail(
                    f"  {status} {_short_url(url):<43} relevance={ar.relevance_score}{explanation}"
                )

    # Return batch stats along with results
    batch_stats = {
        "urls_filtered": urls_filtered,
        "keywords_passed": keywords_passed,
        "cache_hits": cache_hits,
        "cache_skipped": cache_skipped_not_relevant,
    }

    return crawl_results, policies, batch_stats


async def run(args) -> int:
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    logger = RunLogger(run_id)
    logger.start_run()

    claude_client = None
    notification_manager = None
    alert_manager = None
    health_metrics = None

    try:
        # Load config
        logger.section(LogSection.CONFIG)
        settings, domains_config, keywords_config = load_settings()

        # Initialize notification and alert systems
        notif_config = load_notification_config()
        if notif_config.email_enabled:
            notification_manager = NotificationManager(notif_config)
            logger.info("Notifications: Enabled")

        alert_thresholds = load_alert_thresholds()
        alert_manager = AlertManager(alert_thresholds)
        health_metrics = RunHealthMetrics(run_id=run_id)
        logger.info("Health monitoring: Enabled")

        # Warn about domains missing region field
        region_warnings = warn_missing_regions(domains_config)
        for warning in region_warnings:
            logger.warning(f"Missing region: {warning}")

        if args.skip_llm:
            settings.analysis.enable_llm_analysis = False

        # Get domains by group, region, or file
        all_domains = get_enabled_domains(domains_config, args.domains)

        # Apply category/tag/policy-type filtering if specified
        category = getattr(args, 'category', None)
        tags = getattr(args, 'tags', None)
        policy_types = getattr(args, 'policy_types', None)
        match_all_tags = getattr(args, 'match_all_tags', False)

        if category or tags or policy_types:
            # Build a filtered domains_config with only the group-selected domains
            filtered_config = {"domains": all_domains}
            all_domains = filter_domains(
                filtered_config,
                category=category,
                tags=tags,
                policy_types=policy_types,
                match_all_tags=match_all_tags,
            )

            # Log what filters were applied
            filter_desc = []
            if category:
                filter_desc.append(f"category={category}")
            if tags:
                tag_mode = "ALL" if match_all_tags else "ANY"
                filter_desc.append(f"tags={','.join(tags)} ({tag_mode})")
            if policy_types:
                filter_desc.append(f"policy_types={','.join(policy_types)}")
            logger.info(f"Filters: {', '.join(filter_desc)}")

        total_domain_count = len(all_domains)

        if total_domain_count == 0:
            logger.warning("No domains match the specified filters")
            return 0

        # Handle chunking
        chunk_size = getattr(args, 'chunk_size', None)
        chunk_spec = getattr(args, 'chunk', None)
        chunk_delay = getattr(args, 'chunk_delay', 30)

        # Determine which domains to process
        if chunk_spec:
            # Manual chunk: process only the specified chunk
            current, total = parse_chunk_spec(chunk_spec)
            domains_to_process = get_chunk_by_spec(all_domains, current, total)
            logger.info(f"Chunk {current}/{total}: {len(domains_to_process)} of {total_domain_count} domains")
            batches = [domains_to_process]
        elif chunk_size and chunk_size < len(all_domains):
            # Auto-chunk: split into batches
            batches = split_into_chunks(all_domains, chunk_size)
            logger.info(f"Auto-chunking: {len(batches)} batches of up to {chunk_size} domains")
        else:
            # No chunking: process all at once
            batches = [all_domains]
            logger.info(f"Domains: {len(all_domains)} enabled")

        # Apply CLI overrides to keywords config
        if getattr(args, 'min_keyword_score', None) is not None:
            if 'thresholds' not in keywords_config:
                keywords_config['thresholds'] = {}
            keywords_config['thresholds']['minimum_keyword_score'] = args.min_keyword_score
            logger.info(f"Override: min_keyword_score = {args.min_keyword_score}")

        if getattr(args, 'require_combinations', None) is not None:
            enabled = args.require_combinations.lower() == 'true'
            if 'stricter_requirements' not in keywords_config:
                keywords_config['stricter_requirements'] = {}
            if 'required_combinations' not in keywords_config['stricter_requirements']:
                keywords_config['stricter_requirements']['required_combinations'] = {}
            keywords_config['stricter_requirements']['required_combinations']['enabled'] = enabled
            logger.info(f"Override: required_combinations = {enabled}")

        if getattr(args, 'min_density', None) is not None:
            if 'stricter_requirements' not in keywords_config:
                keywords_config['stricter_requirements'] = {}
            if 'density' not in keywords_config['stricter_requirements']:
                keywords_config['stricter_requirements']['density'] = {}
            keywords_config['stricter_requirements']['density']['min_density'] = args.min_density
            keywords_config['stricter_requirements']['density']['enabled'] = args.min_density > 0
            logger.info(f"Override: min_density = {args.min_density}")

        keyword_matcher = KeywordMatcher(keywords_config)
        logger.info(f"Keywords: {keyword_matcher.total_keywords} terms")

        # Load URL pre-filter
        url_filter_config = load_url_filters()
        url_filter = URLFilter(url_filter_config)
        filter_count = (
            len(url_filter_config.skip_paths)
            + len(url_filter_config.skip_patterns)
            + len(url_filter_config.skip_extensions)
        )
        if filter_count > 0:
            logger.info(f"URL filters: {filter_count} rules loaded")

        # Initialize URL cache
        url_cache = None
        use_cache = not getattr(args, 'no_cache', False)
        clear_cache = getattr(args, 'clear_cache', False)

        if use_cache:
            url_cache = load_cache()
            if clear_cache:
                url_cache.clear()
                logger.info("Cache: Cleared")
            else:
                # Clean expired entries on startup
                expired = url_cache.clean_expired()
                if expired > 0:
                    logger.info(f"Cache: Removed {expired} expired entries")
                if url_cache.stats.total_entries > 0:
                    logger.info(f"Cache: {url_cache.stats.total_entries} entries loaded")

        if settings.analysis.enable_llm_analysis and settings.anthropic_api_key:
            claude_client = ClaudeClient(settings.anthropic_api_key, settings.analysis.llm_model)
            if settings.analysis.enable_two_stage:
                logger.info(f"LLM: {settings.analysis.screening_model} (screening) -> {settings.analysis.llm_model} (analysis)")
            else:
                logger.info(f"LLM: {settings.analysis.llm_model}")

        sheets_client = None
        if not args.dry_run and settings.spreadsheet_id and settings.google_credentials:
            sheets_client = SheetsClient(settings.google_credentials, settings.spreadsheet_id)
            sheets_client.connect()
            logger.info("Sheets: Connected")

        # Process batches
        all_crawl_results = []
        all_policies = []
        total_batches = len(batches)

        # Accumulate filter stats across batches
        total_urls_filtered = 0
        total_keywords_passed = 0
        total_cache_hits = 0
        total_cache_skipped = 0

        for batch_num, batch_domains in enumerate(batches, 1):
            if total_batches > 1:
                logger.section(LogSection.CRAWL)
                domain_ids = [d.get('id', d.get('name', 'unknown')) for d in batch_domains]
                logger.info(f"")
                logger.info(f"{'='*60}")
                logger.info(f"  BATCH {batch_num}/{total_batches}")
                logger.info(f"  Domains: {', '.join(domain_ids[:5])}{'...' if len(domain_ids) > 5 else ''}")
                logger.info(f"{'='*60}")
                logger.info(f"")
            else:
                logger.section(LogSection.CRAWL)

            crawl_results, policies, batch_stats = await run_batch(
                batch_domains,
                settings,
                keyword_matcher,
                claude_client,
                sheets_client,
                logger,
                args,
                url_filter,
                url_cache,
            )

            all_crawl_results.extend(crawl_results)
            all_policies.extend(policies)

            # Accumulate batch stats
            total_urls_filtered += batch_stats.get("urls_filtered", 0)
            total_keywords_passed += batch_stats.get("keywords_passed", 0)
            total_cache_hits += batch_stats.get("cache_hits", 0)
            total_cache_skipped += batch_stats.get("cache_skipped", 0)

            # Update health metrics for this batch
            if health_metrics:
                for result in crawl_results:
                    if result.is_success:
                        health_metrics.record_page_success(result.url)
                    elif result.is_blocked:
                        health_metrics.record_page_blocked()
                    elif result.status == PageStatus.TIMEOUT:
                        health_metrics.record_page_timeout()
                    else:
                        health_metrics.record_page_error(result.url, str(result.status.value))

                # Check for alerts after each batch
                if alert_manager:
                    alerts = alert_manager.run_all_checks(health_metrics)
                    for alert in alerts:
                        logger.warning(f"ALERT: {alert.message}")
                        # Send notification if configured
                        if notification_manager and alert.severity.value in ["error", "critical"]:
                            notification_manager.notify_high_error_rate(
                                run_id=run_id,
                                error_rate=health_metrics.error_rate,
                                errors=health_metrics.pages_error,
                                total=health_metrics.pages_attempted,
                                threshold=alert_thresholds.error_rate_warning,
                            )

            # Output policies for this batch
            if sheets_client and policies:
                existing = sheets_client.get_existing_urls()
                new_policies = [p for p in policies if p.url not in existing]
                if new_policies:
                    count = sheets_client.append_policies(new_policies)
                    logger.success(f"Added {count} policies to Staging")

            # Pause between batches (not after the last one)
            if batch_num < total_batches and chunk_delay > 0:
                logger.info(f"")
                logger.info(f"Batch {batch_num}/{total_batches} complete. Pausing {chunk_delay}s before next batch...")
                logger.info(f"")
                await asyncio.sleep(chunk_delay)

        # Final analysis section
        logger.section(LogSection.ANALYSIS)
        logger.info(f"Found {len(all_policies)} relevant policies across all batches")

        # Output summary
        logger.section(LogSection.OUTPUT)
        if args.dry_run:
            logger.info(f"Dry run - would add {len(all_policies)} policies")
        elif not sheets_client:
            logger.info("Sheets not configured - skipping output")

        # Summary
        logger.section(LogSection.SUMMARY)

        # Calculate stats
        new_count = 0
        dup_count = 0
        if sheets_client and all_policies:
            existing = sheets_client.get_existing_urls()
            new_policies = [p for p in all_policies if p.url not in existing]
            new_count = len(new_policies)
            dup_count = len(all_policies) - new_count
        elif args.dry_run:
            new_count = len(all_policies)

        # Get screening stats from client
        screening_stats = claude_client.get_screening_stats() if claude_client else {}

        stats = RunStats(
            domains_scanned=sum(len(batch) for batch in batches),
            pages_crawled=len(all_crawl_results),
            pages_success=sum(1 for r in all_crawl_results if r.is_success),
            pages_blocked=sum(1 for r in all_crawl_results if r.is_blocked),
            pages_error=sum(1 for r in all_crawl_results if r.status == PageStatus.UNKNOWN_ERROR),
            keywords_matched=sum(1 for r in all_crawl_results if r.is_success),  # Approximate
            policies_found=len(all_policies),
            policies_new=new_count,
            policies_duplicate=dup_count,
            # Full analysis (Sonnet) stats
            llm_calls=claude_client.call_count if claude_client else 0,
            llm_tokens_input=claude_client.tokens_input if claude_client else 0,
            llm_tokens_output=claude_client.tokens_output if claude_client else 0,
            # Screening (Haiku) stats
            screening_calls=screening_stats.get("calls", 0),
            screening_tokens_input=screening_stats.get("tokens_input", 0),
            screening_tokens_output=screening_stats.get("tokens_output", 0),
            # Filter stats
            urls_filtered=total_urls_filtered,
            keywords_passed=total_keywords_passed,
            cache_hits=total_cache_hits,
            cache_skipped=total_cache_skipped,
        )

        # Build RunConfig (always, for last-run command; display only if --verbose-summary)
        # Extract keyword config values
        kw_thresholds = keywords_config.get('thresholds', {})
        stricter = keywords_config.get('stricter_requirements', {})
        req_combos = stricter.get('required_combinations', {})
        density_cfg = stricter.get('density', {})

        run_config = RunConfig(
            # Domain selection
            domain_group=args.domains,
            category_filter=category,
            tag_filters=tags,
            policy_type_filters=policy_types,
            domains_count=total_domain_count,

            # Keyword settings
            min_keyword_score=kw_thresholds.get('minimum_keyword_score', 5.0),
            min_keyword_matches=kw_thresholds.get('minimum_keyword_matches', 2),
            required_combinations_enabled=req_combos.get('enabled', True),
            min_density=density_cfg.get('min_density', 1.0),
            density_enabled=density_cfg.get('enabled', True),
            boost_keywords_enabled=keywords_config.get('boost_keywords', {}).get('enabled', True),
            penalty_keywords_enabled=keywords_config.get('penalty_keywords', {}).get('enabled', True),

            # LLM settings
            enable_llm=settings.analysis.enable_llm_analysis,
            enable_two_stage=settings.analysis.enable_two_stage,
            screening_model=settings.analysis.screening_model,
            analysis_model=settings.analysis.llm_model,
            screening_min_confidence=settings.analysis.screening_min_confidence,
            min_relevance_score=settings.analysis.min_relevance_score,

            # Cache settings
            cache_enabled=use_cache,
            cache_cleared=clear_cache,

            # Other options
            dry_run=args.dry_run,
            chunking=chunk_spec if chunk_spec else (f"{chunk_size} per batch" if chunk_size else None),
        )

        # Pass run_config for JSON logging; only show verbose output if requested
        show_verbose = getattr(args, 'verbose_summary', False)
        logger.end_run(stats, run_config if show_verbose else None, save_config=run_config)

        # Log LLM error summary if there were errors
        if claude_client:
            error_summary = claude_client.get_error_summary()
            if error_summary["total"] > 0:
                logger.info("")
                logger.info("LLM Error Summary:")
                logger.info(f"  Total errors: {error_summary['total']}")
                if error_summary["parse"]:
                    logger.info(f"  Parse errors: {error_summary['parse']}")
                if error_summary["validation"]:
                    logger.info(f"  Validation errors: {error_summary['validation']}")
                if error_summary["rate_limit"]:
                    logger.info(f"  Rate limit errors: {error_summary['rate_limit']}")
                if error_summary["context_too_long"]:
                    logger.info(f"  Context too long: {error_summary['context_too_long']}")
                if error_summary["connection"]:
                    logger.info(f"  Connection errors: {error_summary['connection']}")
                if error_summary["timeout"]:
                    logger.info(f"  Timeout errors: {error_summary['timeout']}")
                if error_summary["service"]:
                    logger.info(f"  Service errors: {error_summary['service']}")
                if error_summary["retries"]:
                    logger.info(f"  Total retries: {error_summary['retries']}")

        # Record cost to history (if LLM was used)
        if claude_client and claude_client.call_count > 0:
            cost_tracker = CostTracker()
            cost_tracker.record_run(
                run_id=run_id,
                model=settings.analysis.llm_model,
                input_tokens=claude_client.tokens_input,
                output_tokens=claude_client.tokens_output,
                api_calls=claude_client.call_count,
                domains_scanned=stats.domains_scanned,
                policies_found=stats.policies_found,
            )

            # Check budget warning
            warning = cost_tracker.check_budget_warning(monthly_budget=50.0)
            if warning:
                logger.warning(warning)
                # Send budget notification
                if notification_manager:
                    current_cost = cost_tracker.history.get_cost_since(30)
                    notification_manager.notify_budget_warning(
                        current_cost=current_cost,
                        budget=50.0,
                        percentage=(current_cost / 50.0) * 100,
                    )

            # Check for cost spike
            if alert_manager and len(cost_tracker.history.runs) > 1:
                recent_costs = [r.total_cost_usd for r in cost_tracker.history.runs[:-1]]
                if recent_costs:
                    avg_cost = sum(recent_costs) / len(recent_costs)
                    if avg_cost > 0 and stats.estimated_cost_usd > avg_cost * alert_thresholds.cost_spike_multiplier:
                        alert = alert_manager.check_cost_spike(
                            current_cost=stats.estimated_cost_usd,
                            average_cost=avg_cost,
                            run_id=run_id,
                        )
                        if alert:
                            logger.warning(f"ALERT: {alert.message}")
                            if notification_manager:
                                notification_manager.notify_cost_spike(
                                    run_id=run_id,
                                    current_cost=stats.estimated_cost_usd,
                                    average_cost=avg_cost,
                                    multiplier=stats.estimated_cost_usd / avg_cost,
                                )

        # Check if no policies found
        if len(all_policies) == 0 and stats.domains_scanned > 0:
            if notification_manager:
                notification_manager.notify_no_policies(
                    run_id=run_id,
                    domains_scanned=stats.domains_scanned,
                    pages_crawled=stats.pages_crawled,
                )

        # Send success notification
        if notification_manager:
            notification_manager.notify_run_complete(
                run_id=run_id,
                domains_scanned=stats.domains_scanned,
                policies_found=stats.policies_found,
                policies_new=stats.policies_new,
                duration_seconds=stats.duration_seconds,
                cost_usd=stats.estimated_cost_usd,
            )

        # Save URL cache
        if url_cache:
            save_cache(url_cache)
            cache_stats = url_cache.get_stats()
            if cache_stats.hits > 0 or cache_stats.total_entries > 0:
                logger.info(f"Cache saved: {cache_stats.total_entries} entries ({cache_stats.format()})")

        return 0

    except ConfigurationError as e:
        logger.error(f"Config error: {e}")
        # Send failure notification
        if notification_manager:
            notification_manager.notify_run_failed(
                run_id=run_id,
                error_message=str(e),
                error_type="ConfigurationError",
            )
        return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        # Send failure notification
        if notification_manager:
            notification_manager.notify_run_failed(
                run_id=run_id,
                error_message=str(e),
                error_type=type(e).__name__,
            )
        return 1
    finally:
        if claude_client:
            await claude_client.close()


def main():
    args = parse_args()

    # Handle subcommands
    if args.command == "reject-site":
        sys.exit(cmd_reject_site(args))
    elif args.command == "list-rejected":
        sys.exit(cmd_list_rejected(args))
    elif args.command == "list-groups":
        sys.exit(cmd_list_groups(args))
    elif args.command == "list-domains":
        sys.exit(cmd_list_domains(args))
    elif args.command == "cost-history":
        sys.exit(cmd_cost_history(args))
    elif args.command == "estimate-cost":
        sys.exit(cmd_estimate_cost(args))
    elif args.command == "test-notifications":
        sys.exit(cmd_test_notifications(args))
    elif args.command == "alerts":
        sys.exit(cmd_alerts(args))
    elif args.command == "list-categories":
        sys.exit(cmd_list_categories(args))
    elif args.command == "list-tags":
        sys.exit(cmd_list_tags(args))
    elif args.command == "list-policy-types":
        sys.exit(cmd_list_policy_types(args))
    elif args.command == "list-regions":
        sys.exit(cmd_list_regions(args))
    elif args.command == "domain-stats":
        sys.exit(cmd_domain_stats(args))
    elif args.command == "last-run":
        sys.exit(cmd_last_run(args))
    elif args.command == "list-runs":
        sys.exit(cmd_list_runs(args))
    elif args.command == "report":
        sys.exit(cmd_report(args))
    else:
        # Default: run scan
        code = asyncio.run(run(args))
        sys.exit(code)


if __name__ == "__main__":
    main()
