#!/usr/bin/env python3
"""OCP Heat Reuse Policy Searcher - Main entry point."""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config.loader import load_settings, get_enabled_domains, list_groups, ConfigurationError
from .crawler.async_crawler import AsyncCrawler
from .analysis.keywords import KeywordMatcher
from .analysis.llm.client import ClaudeClient
from .output.sheets import SheetsClient
from .logging.run_logger import RunLogger, LogSection, RunStats
from .models.crawl import PageStatus
from .models.policy import Policy, PolicyType


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

    # Main scan arguments (default command)
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--domains", default="all", help="Domain group to scan (use 'list-groups' to see options)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Sheets")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM analysis")
    parser.add_argument("--verbose", "-v", action="store_true")

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


async def run(args) -> int:
    run_id = f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    logger = RunLogger(run_id)
    logger.start_run()

    try:
        # Load config
        logger.section(LogSection.CONFIG)
        settings, domains_config, keywords_config = load_settings()

        if args.skip_llm:
            settings.analysis.enable_llm_analysis = False

        domains = get_enabled_domains(domains_config, args.domains)
        logger.info(f"Domains: {len(domains)} enabled")

        keyword_matcher = KeywordMatcher(keywords_config)
        logger.info(f"Keywords: {keyword_matcher.total_keywords} terms")

        claude_client = None
        if settings.analysis.enable_llm_analysis and settings.anthropic_api_key:
            claude_client = ClaudeClient(settings.anthropic_api_key, settings.analysis.llm_model)
            logger.info(f"LLM: {settings.analysis.llm_model}")

        sheets_client = None
        if not args.dry_run and settings.spreadsheet_id and settings.google_credentials:
            sheets_client = SheetsClient(settings.google_credentials, settings.spreadsheet_id)
            sheets_client.connect()
            logger.info("Sheets: Connected")

        # Crawl
        logger.section(LogSection.CRAWL)
        crawler = AsyncCrawler(settings.crawl, domains, keyword_matcher, logger)
        crawl_results = await crawler.crawl_all()
        logger.info(f"Crawled {len(crawl_results)} pages")

        # Analyze
        logger.section(LogSection.ANALYSIS)
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

        logger.info(f"Found {len(policies)} relevant policies")

        # Output
        logger.section(LogSection.OUTPUT)
        if sheets_client and policies:
            existing = sheets_client.get_existing_urls()
            new_policies = [p for p in policies if p.url not in existing]

            if new_policies:
                count = sheets_client.append_policies(new_policies)
                logger.success(f"Added {count} policies to Staging")
            else:
                logger.info("No new policies (all duplicates)")
        elif args.dry_run:
            logger.info(f"Dry run - would add {len(policies)} policies")

        # Summary
        logger.section(LogSection.SUMMARY)
        stats = RunStats(
            pages_crawled=len(crawl_results),
            pages_success=sum(1 for r in crawl_results if r.is_success),
            pages_blocked=sum(1 for r in crawl_results if r.is_blocked),
            pages_error=sum(1 for r in crawl_results if r.status == PageStatus.UNKNOWN_ERROR),
            policies_found=len(policies),
        )
        logger.end_run(stats)

        return 0

    except ConfigurationError as e:
        logger.error(f"Config error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}")
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
    else:
        # Default: run scan
        code = asyncio.run(run(args))
        sys.exit(code)


if __name__ == "__main__":
    main()
