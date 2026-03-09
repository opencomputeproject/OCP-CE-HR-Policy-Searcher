"""Parallel scan manager — dispatches domain workers, tracks progress, broadcasts events."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from ..core.cache import URLCache
from ..core.config import ConfigLoader
from ..core.crawler import AsyncCrawler
from ..core.extractor import HtmlExtractor
from ..core.keywords import KeywordMatcher
from ..core.llm import ClaudeClient
from ..core.models import (
    Policy, ScanJob, ScanStatus, ScanProgress, DomainProgress,
    DomainScanStatus, ScanEvent,
)
from ..core.scanner import DomainScanner
from ..core.verifier import Verifier
from .auditor import Auditor
from .events import EventBroadcaster

logger = logging.getLogger(__name__)


class ScanManager:
    """Manages parallel domain scanning with progress tracking."""

    def __init__(
        self,
        config: ConfigLoader,
        broadcaster: EventBroadcaster,
        api_key: Optional[str] = None,
        data_dir: str = "data",
    ):
        self.config = config
        self.broadcaster = broadcaster
        self.api_key = api_key
        self.data_dir = data_dir

        self._jobs: dict[str, ScanJob] = {}
        self._policies: dict[str, list[Policy]] = {}  # scan_id → policies
        self._tasks: dict[str, asyncio.Task] = {}

    @property
    def jobs(self) -> dict[str, ScanJob]:
        return self._jobs

    def get_policies(self, scan_id: str) -> list[Policy]:
        return self._policies.get(scan_id, [])

    def get_all_policies(self) -> list[Policy]:
        """Get all policies across all scans."""
        all_policies = []
        for policies in self._policies.values():
            all_policies.extend(policies)
        return all_policies

    async def start_scan(
        self,
        domains_group: str = "quick",
        max_concurrent: int = 5,
        skip_llm: bool = False,
        dry_run: bool = False,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        policy_type: Optional[str] = None,
    ) -> ScanJob:
        """Start a new parallel scan. Returns immediately with scan_id."""
        scan_id = str(uuid.uuid4())[:8]

        # Resolve domains
        domains = self.config.get_enabled_domains(domains_group)

        # Apply additional filters
        if category:
            domains = [d for d in domains if d.get("category") == category]
        if tags:
            domains = [
                d for d in domains
                if any(t in d.get("tags", []) for t in tags)
            ]
        if policy_type:
            domains = [
                d for d in domains
                if policy_type in d.get("policy_types", [])
            ]

        job = ScanJob(
            scan_id=scan_id,
            status=ScanStatus.RUNNING,
            started_at=datetime.utcnow(),
            domain_group=domains_group,
            domain_count=len(domains),
            progress=ScanProgress(
                total_domains=len(domains),
                domains=[
                    DomainProgress(
                        domain_id=d["id"],
                        domain_name=d.get("name", d["id"]),
                    )
                    for d in domains
                ],
            ),
            options={
                "max_concurrent": max_concurrent,
                "skip_llm": skip_llm,
                "dry_run": dry_run,
            },
        )

        self._jobs[scan_id] = job
        self._policies[scan_id] = []

        if dry_run:
            job.status = ScanStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            return job

        # Launch background task
        task = asyncio.create_task(
            self._run_scan(scan_id, domains, max_concurrent, skip_llm)
        )
        self._tasks[scan_id] = task
        return job

    async def _run_scan(
        self,
        scan_id: str,
        domains: list[dict],
        max_concurrent: int,
        skip_llm: bool,
    ) -> None:
        """Run the parallel scan (background task)."""
        job = self._jobs[scan_id]

        await self.broadcaster.broadcast(ScanEvent(
            scan_id=scan_id,
            type="scan_started",
            data={"domain_count": len(domains)},
        ))

        # Shared resources
        settings = self.config.settings
        cache = URLCache.load(
            cache_path=__import__("pathlib").Path(self.data_dir) / "url_cache.json"
        )
        extractor = HtmlExtractor(settings.config_dir)
        keyword_matcher = KeywordMatcher(self.config.keywords_config)
        verifier = Verifier()

        llm_client = None
        if not skip_llm and self.api_key:
            llm_client = ClaudeClient(
                api_key=self.api_key,
                analysis_model=settings.analysis.analysis_model,
                screening_model=settings.analysis.screening_model,
            )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def scan_domain(domain: dict) -> list[Policy]:
            async with semaphore:
                crawler = AsyncCrawler(
                    max_depth=domain.get("max_depth", settings.crawl.max_depth),
                    max_pages=domain.get("max_pages", settings.crawl.max_pages_per_domain),
                    delay_seconds=settings.crawl.delay_seconds,
                    timeout_seconds=settings.crawl.timeout_seconds,
                    user_agent=settings.crawl.user_agent,
                    max_retries=settings.crawl.max_retries,
                    skip_extensions=self.config.get_skip_extensions(),
                    crawl_blocked_patterns=self.config.get_crawl_blocked_patterns()
                        + domain.get("blocked_path_patterns", []),
                    url_skip_paths=self.config.get_url_skip_paths(),
                    url_skip_patterns=self.config.get_url_skip_patterns(),
                )

                scanner = DomainScanner(
                    domain=domain,
                    crawler=crawler,
                    extractor=extractor,
                    keyword_matcher=keyword_matcher,
                    llm_client=llm_client,
                    cache=cache,
                    verifier=verifier,
                    scan_id=scan_id,
                    skip_llm=skip_llm,
                    on_event=self.broadcaster.broadcast,
                )

                try:
                    policies = await scanner.scan()

                    # Update job progress
                    for dp in job.progress.domains:
                        if dp.domain_id == domain["id"]:
                            dp.status = scanner.progress.status
                            dp.pages_crawled = scanner.progress.pages_crawled
                            dp.pages_filtered = scanner.progress.pages_filtered
                            dp.keywords_matched = scanner.progress.keywords_matched
                            dp.policies_found = scanner.progress.policies_found
                            dp.errors = scanner.progress.errors
                            dp.error_message = scanner.progress.error_message
                            break

                    job.progress.completed_domains += 1
                    return policies

                except Exception as e:
                    logger.error(f"Domain {domain['id']} failed: {e}")
                    for dp in job.progress.domains:
                        if dp.domain_id == domain["id"]:
                            dp.status = DomainScanStatus.FAILED
                            dp.error_message = str(e)
                            break
                    job.progress.completed_domains += 1
                    return []

                finally:
                    await crawler.close()

        try:
            # Run all domains in parallel (bounded by semaphore)
            tasks = [scan_domain(d) for d in domains]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_policies = []
            for result in results:
                if isinstance(result, list):
                    all_policies.extend(result)

            self._policies[scan_id] = all_policies
            job.policy_count = len(all_policies)

            # Update LLM cost
            if llm_client:
                llm_client.update_cost_estimate()
                job.cost = llm_client.cost

            # Post-scan verification summary
            flagged = [p for p in all_policies if p.verification_flags]
            await self.broadcaster.broadcast(ScanEvent(
                scan_id=scan_id,
                type="verification_complete",
                data={
                    "flagged": len(flagged),
                    "passed": len(all_policies) - len(flagged),
                },
            ))

            # Post-scan auditor (1 LLM call)
            if not skip_llm and self.api_key and all_policies:
                try:
                    auditor = Auditor(api_key=self.api_key)
                    advisory = await auditor.generate_advisory(
                        scan_summary={
                            "scan_id": scan_id,
                            "domains_scanned": len(domains),
                            "policies_found": len(all_policies),
                            "cost": job.cost.model_dump() if job.cost else {},
                        },
                        domain_results=[
                            dp.model_dump() for dp in job.progress.domains
                        ],
                        flagged_issues=[
                            {
                                "url": p.url,
                                "policy_name": p.policy_name,
                                "flags": [f.value for f in p.verification_flags],
                            }
                            for p in flagged
                        ],
                    )
                    job.audit_advisory = advisory
                    await self.broadcaster.broadcast(ScanEvent(
                        scan_id=scan_id,
                        type="audit_complete",
                        data={"advisory": advisory or "No advisory generated"},
                    ))
                    await auditor.close()
                except Exception as e:
                    logger.warning(f"Auditor failed: {e}")

            # Save cache
            cache.save()

            # Export to Google Sheets (if configured)
            output_cfg = self.config.settings.output
            if output_cfg.spreadsheet_id and output_cfg.google_credentials_b64 and all_policies:
                try:
                    from ..output.sheets import SheetsClient
                    sheets = SheetsClient(
                        credentials_b64=output_cfg.google_credentials_b64,
                        spreadsheet_id=output_cfg.spreadsheet_id,
                    )
                    sheets.connect()
                    existing_urls = sheets.get_existing_urls(output_cfg.staging_sheet_name)
                    new_policies = [p for p in all_policies if p.url not in existing_urls]
                    if new_policies:
                        count = sheets.append_policies(new_policies, output_cfg.staging_sheet_name)
                        logger.info(f"Exported {count} new policies to Google Sheets")
                except Exception as e:
                    logger.warning(f"Google Sheets export failed: {e}")

            job.status = ScanStatus.COMPLETED
            job.completed_at = datetime.utcnow()

            await self.broadcaster.broadcast(ScanEvent(
                scan_id=scan_id,
                type="scan_complete",
                data={
                    "total_policies": len(all_policies),
                    "cost_usd": job.cost.total_usd if job.cost else 0,
                },
            ))

        except asyncio.CancelledError:
            job.status = ScanStatus.CANCELLED
            job.completed_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"Scan {scan_id} failed: {e}")
            job.status = ScanStatus.FAILED
            job.completed_at = datetime.utcnow()
            await self.broadcaster.broadcast(ScanEvent(
                scan_id=scan_id,
                type="error",
                data={"error": str(e)},
            ))
        finally:
            if llm_client:
                await llm_client.close()

    async def stop_scan(self, scan_id: str) -> bool:
        """Cancel a running scan."""
        task = self._tasks.get(scan_id)
        if task and not task.done():
            task.cancel()
            job = self._jobs.get(scan_id)
            if job:
                job.status = ScanStatus.CANCELLED
                job.completed_at = datetime.utcnow()
            return True
        return False

    def estimate_cost(self, domains_group: str) -> dict:
        """Estimate API costs for a scan."""
        domains = self.config.get_enabled_domains(domains_group)
        settings = self.config.settings

        est_pages_per_domain = settings.crawl.max_pages_per_domain // 2
        total_pages = len(domains) * est_pages_per_domain
        keyword_pass_rate = 0.10
        screening_pass_rate = 0.50

        keyword_passes = int(total_pages * keyword_pass_rate)
        screening_calls = keyword_passes
        analysis_calls = int(screening_calls * screening_pass_rate)

        # Haiku: ~$0.25/M input, ~$1.25/M output
        # Sonnet: ~$3/M input, ~$15/M output
        haiku_cost = screening_calls * (2000 * 0.25 + 50 * 1.25) / 1_000_000
        sonnet_cost = analysis_calls * (20000 * 3.0 + 1000 * 15.0) / 1_000_000
        auditor_cost = (5000 * 3.0 + 2000 * 15.0) / 1_000_000

        return {
            "domain_count": len(domains),
            "estimated_pages": total_pages,
            "estimated_keyword_passes": keyword_passes,
            "estimated_screening_calls": screening_calls,
            "estimated_analysis_calls": analysis_calls,
            "estimated_cost_usd": round(haiku_cost + sonnet_cost + auditor_cost, 2),
        }
