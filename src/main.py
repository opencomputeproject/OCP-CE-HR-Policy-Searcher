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
    list_groups,
    list_domains,
    ConfigurationError,
    filter_domains,
    filter_domains_by_category,
    filter_domains_by_tag,
    filter_domains_by_policy_type,
    list_categories,
    list_tags,
    list_policy_types,
    get_domain_stats,
    VALID_CATEGORIES,
    VALID_TAGS,
    VALID_POLICY_TYPES,
)
from .crawler.async_crawler import AsyncCrawler
from .analysis.keywords import KeywordMatcher
from .analysis.llm.client import ClaudeClient
from .output.sheets import SheetsClient
from .logging.run_logger import RunLogger, LogSection, RunStats
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
        help="Add a site to rejected_sites.yaml"
    )
    reject_parser.add_argument("--url", required=True, help="URL of the rejected site")
    reject_parser.add_argument("--reason", required=True, help="Reason for rejection")
    reject_parser.add_argument("--evaluated-by", default=None, help="Your name (optional)")
    reject_parser.add_argument("--reconsider-if", default=None, help="Conditions to reconsider")
    reject_parser.add_argument("--replaced-by", default=None, help="Alternative domain ID if applicable")

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
        help="Domain group to estimate (default: all)"
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

    # domain-stats subcommand
    subparsers.add_parser(
        "domain-stats",
        help="Show statistics about domain categorization"
    )

    # Main scan arguments (default command)
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--domains", default="all", help="Domain group to scan (use 'list-groups' to see options)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Sheets")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM analysis")
    parser.add_argument("--verbose", "-v", action="store_true")

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
    """Add a site to the rejected sites file."""
    rejected_file = Path("config/rejected_sites.yaml")

    # Load existing file
    if rejected_file.exists():
        with open(rejected_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Initialize rejected_sites list if needed
    if "rejected_sites" not in data or data["rejected_sites"] is None:
        data["rejected_sites"] = []

    # Check if URL already exists
    existing_urls = [site.get("url") for site in data["rejected_sites"] if site]
    if args.url in existing_urls:
        print(f"URL already in rejected sites: {args.url}")
        return 1

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
        # Write header comment
        f.write("# =============================================================================\n")
        f.write("# REJECTED SITES\n")
        f.write("# =============================================================================\n")
        f.write("# Sites that were evaluated but NOT included in the crawler.\n")
        f.write("#\n")
        f.write("# To add a site via CLI:\n")
        f.write('#   python -m src.main reject-site --url "https://example.gov" --reason "No policy content"\n')
        f.write("#\n")
        f.write("# Or edit this file directly.\n")
        f.write("# =============================================================================\n\n")

        # Write YAML content
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Added to rejected sites: {args.url}")
    print(f"  Reason: {args.reason}")
    return 0


def cmd_list_groups(args) -> int:
    """List available domain groups."""
    try:
        _, domains_config, _ = load_settings()
        groups = list_groups(domains_config)

        print("\nAvailable domain groups:\n")
        print(f"  {'Group':<20} {'Description'}")
        print(f"  {'-'*20} {'-'*50}")

        for name, desc in sorted(groups.items()):
            print(f"  {name:<20} {desc}")

        print(f"\nUsage: python -m src.main --domains <group_name>")
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


def cmd_domain_stats(args) -> int:
    """Show statistics about domain categorization."""
    _, domains_config, _ = load_settings()
    stats = get_domain_stats(domains_config)

    print("\n" + "=" * 60)
    print("  DOMAIN CATEGORIZATION STATS")
    print("=" * 60 + "\n")

    print(f"  Total domains:    {stats['total_domains']}")
    print(f"  Enabled domains:  {stats['enabled_domains']}")

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


async def run_batch(
    domains: list,
    settings,
    keyword_matcher,
    claude_client,
    sheets_client,
    logger,
    args,
) -> tuple[list, list]:
    """
    Run a single batch of domains.

    Returns:
        Tuple of (crawl_results, policies)
    """
    # Crawl
    crawler = AsyncCrawler(settings.crawl, domains, keyword_matcher, logger)
    crawl_results = await crawler.crawl_all()
    logger.info(f"Crawled {len(crawl_results)} pages")

    # Analyze
    policies = []

    for result in crawl_results:
        if not result.is_success:
            continue

        # Keyword check
        kw_result = keyword_matcher.match(result.content or "")
        if kw_result.score < settings.analysis.min_keyword_score:
            continue

        # LLM analysis
        if claude_client:
            try:
                analysis = await claude_client.analyze_policy(
                    result.content[:settings.analysis.max_content_length],
                    result.url,
                    result.language,
                )
                if analysis.is_relevant and analysis.relevance_score >= settings.analysis.min_relevance_score:
                    policy = claude_client.to_policy(analysis, result.url, result.language or "unknown")
                    if policy:
                        policies.append(policy)
                        logger.success(f"Policy: {policy.policy_name}")
            except Exception as e:
                logger.warning(f"LLM error for {result.url}: {e}")
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

    return crawl_results, policies


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

        if args.skip_llm:
            settings.analysis.enable_llm_analysis = False

        # Get domains by group first
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

        keyword_matcher = KeywordMatcher(keywords_config)
        logger.info(f"Keywords: {keyword_matcher.total_keywords} terms")

        if settings.analysis.enable_llm_analysis and settings.anthropic_api_key:
            claude_client = ClaudeClient(settings.anthropic_api_key, settings.analysis.llm_model)
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

            crawl_results, policies = await run_batch(
                batch_domains,
                settings,
                keyword_matcher,
                claude_client,
                sheets_client,
                logger,
                args,
            )

            all_crawl_results.extend(crawl_results)
            all_policies.extend(policies)

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
            llm_calls=claude_client.call_count if claude_client else 0,
            llm_tokens_input=claude_client.tokens_input if claude_client else 0,
            llm_tokens_output=claude_client.tokens_output if claude_client else 0,
        )
        logger.end_run(stats)

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
    elif args.command == "domain-stats":
        sys.exit(cmd_domain_stats(args))
    else:
        # Default: run scan
        code = asyncio.run(run(args))
        sys.exit(code)


if __name__ == "__main__":
    main()
