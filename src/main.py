#!/usr/bin/env python3
"""OCP Heat Reuse Policy Searcher - Main entry point."""

import argparse
import asyncio
import sys
from datetime import datetime

from .config.loader import load_settings, get_enabled_domains, ConfigurationError
from .crawler.async_crawler import AsyncCrawler
from .analysis.keywords import KeywordMatcher
from .analysis.llm.client import ClaudeClient
from .output.sheets import SheetsClient
from .logging.run_logger import RunLogger, LogSection, RunStats
from .models.crawl import PageStatus
from .models.policy import Policy, PolicyType


def parse_args():
    parser = argparse.ArgumentParser(description="Search for heat reuse policies")
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--domains", default="all",
                       choices=["all", "eu", "us", "apac",
                               "nordic", "eu_central", "eu_west", "us_states",
                               "federal", "leaders", "emerging",
                               "test", "quick", "sample_nordic", "sample_apac"],
                       help="Domain group to scan")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Sheets")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM analysis")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args()


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
    code = asyncio.run(run(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
