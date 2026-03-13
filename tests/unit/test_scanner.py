"""Tests for DomainScanner pipeline with mocked dependencies."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.cache import URLCache
from src.core.models import (
    CrawlResult, PageStatus, Policy, PolicyType, PolicyAnalysis,
    ScreeningResult, KeywordResult, KeywordMatch, ExtractedContent,
)
from src.core.scanner import DomainScanner


def _make_domain(**overrides):
    defaults = {
        "id": "test_domain",
        "name": "Test Domain",
        "base_url": "https://example.gov",
        "start_paths": ["/"],
        "region": ["us"],
    }
    defaults.update(overrides)
    return defaults


def _make_crawl_result(url="https://example.gov/page", content="<html><body><p>Policy content about data center heat reuse requirements</p></body></html>"):
    return CrawlResult(
        url=url,
        status=PageStatus.SUCCESS,
        content=content,
        content_length=len(content),
    )


def _make_extracted():
    return ExtractedContent(
        text="Policy content about data center heat reuse requirements " * 10,
        title="Policy Page",
        language="en",
        word_count=80,
    )


class TestDomainScannerInit:
    def test_creates_progress(self):
        scanner = DomainScanner(
            domain=_make_domain(),
            crawler=MagicMock(),
            extractor=MagicMock(),
            keyword_matcher=MagicMock(),
            llm_client=None,
            cache=URLCache(),
            verifier=MagicMock(),
            scan_id="scan_1",
        )
        assert scanner.domain_id == "test_domain"
        assert scanner.progress.domain_name == "Test Domain"
        assert scanner.scan_id == "scan_1"


class TestDomainScannerScan:
    @pytest.fixture
    def scanner_deps(self):
        """Create mocked dependencies for DomainScanner."""
        crawler = AsyncMock()
        extractor = MagicMock()
        keyword_matcher = MagicMock()
        llm_client = MagicMock()
        cache = URLCache()
        verifier = MagicMock()

        # Default: crawler returns one successful page
        crawler.crawl_domain = AsyncMock(return_value=[_make_crawl_result()])

        # Extractor returns content with enough words
        extractor.extract.return_value = _make_extracted()

        # Keywords match
        kw_result = KeywordResult(
            score=6.0,
            matches=[
                KeywordMatch(term="heat reuse", category="heat_recovery", weight=3.0, language="en"),
                KeywordMatch(term="data center", category="data_center", weight=3.0, language="en"),
            ],
            categories_matched=["heat_recovery", "data_center"],
        )
        keyword_matcher.match.return_value = kw_result
        keyword_matcher.is_relevant.return_value = True
        keyword_matcher.check_near_miss.return_value = False

        # LLM screening passes
        llm_client.screen_relevance = AsyncMock(
            return_value=ScreeningResult(relevant=True, confidence=8),
        )
        # LLM analysis returns a relevant policy
        analysis = PolicyAnalysis(
            is_relevant=True,
            relevance_score=8,
            policy_type="law",
            policy_name="Heat Recovery Act",
            jurisdiction="US",
            summary="A law about heat recovery",
        )
        llm_client.analyze_policy = AsyncMock(return_value=analysis)
        llm_client.to_policy.return_value = Policy(
            url="https://example.gov/page",
            policy_name="Heat Recovery Act",
            jurisdiction="US",
            policy_type=PolicyType.LAW,
            summary="A law about heat recovery",
            relevance_score=8,
            domain_id="test_domain",
            scan_id="scan_1",
        )

        # Verifier returns no flags
        verifier.verify_batch.return_value = {}

        return {
            "crawler": crawler,
            "extractor": extractor,
            "keyword_matcher": keyword_matcher,
            "llm_client": llm_client,
            "cache": cache,
            "verifier": verifier,
        }

    @pytest.mark.asyncio
    async def test_full_pipeline_finds_policy(self, scanner_deps):
        scanner = DomainScanner(
            domain=_make_domain(),
            scan_id="scan_1",
            **scanner_deps,
        )
        policies = await scanner.scan()
        assert len(policies) == 1
        assert policies[0].policy_name == "Heat Recovery Act"
        assert scanner.progress.policies_found == 1
        assert scanner.progress.status.value == "completed"

    @pytest.mark.asyncio
    async def test_skips_failed_pages(self, scanner_deps):
        scanner_deps["crawler"].crawl_domain = AsyncMock(return_value=[
            CrawlResult(url="https://example.gov/denied", status=PageStatus.ACCESS_DENIED),
        ])
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.errors == 1

    @pytest.mark.asyncio
    async def test_filters_short_content(self, scanner_deps):
        scanner_deps["extractor"].extract.return_value = ExtractedContent(
            text="Too short", word_count=2,
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.pages_filtered == 1

    @pytest.mark.asyncio
    async def test_filters_excluded_content(self, scanner_deps):
        scanner_deps["keyword_matcher"].match.return_value = KeywordResult(
            score=0.0, is_excluded=True,
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.pages_filtered == 1

    @pytest.mark.asyncio
    async def test_filters_low_keyword_score(self, scanner_deps):
        scanner_deps["keyword_matcher"].is_relevant.return_value = False
        scanner_deps["keyword_matcher"].check_near_miss.return_value = False
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0

    @pytest.mark.asyncio
    async def test_skips_llm_when_disabled(self, scanner_deps):
        scanner = DomainScanner(
            domain=_make_domain(),
            scan_id="s1",
            skip_llm=True,
            **scanner_deps,
        )
        policies = await scanner.scan()
        # With skip_llm, no policies are produced (cached as needs-LLM)
        assert len(policies) == 0
        scanner_deps["llm_client"].screen_relevance.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_screening_rejection(self, scanner_deps):
        scanner_deps["llm_client"].screen_relevance = AsyncMock(
            return_value=ScreeningResult(relevant=False, confidence=8),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        scanner_deps["llm_client"].analyze_policy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_llm(self, scanner_deps):
        # Pre-populate cache
        scanner_deps["cache"].set(
            "https://example.gov/page",
            is_relevant=True,
            relevance_score=8,
            content_hash="",  # Will match any hash
        )
        # Ensure cache.get returns a valid (non-expired, content-matching) entry
        # We need to set with a content hash that will match
        from src.core.cache import compute_content_hash
        text = _make_extracted().text
        content_hash = compute_content_hash(text)
        scanner_deps["cache"].set(
            "https://example.gov/page",
            is_relevant=True,
            relevance_score=8,
            content_hash=content_hash,
        )

        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        # Cache hit means we skip LLM and return no policy (already have it)
        assert len(policies) == 0
        scanner_deps["llm_client"].screen_relevance.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_scan_error_gracefully(self, scanner_deps):
        scanner_deps["crawler"].crawl_domain = AsyncMock(side_effect=Exception("Network error"))
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.status.value == "failed"
        assert "Network error" in scanner.progress.error_message

    @pytest.mark.asyncio
    async def test_emits_events(self, scanner_deps):
        events = []

        async def capture_event(event):
            events.append(event)

        scanner = DomainScanner(
            domain=_make_domain(),
            scan_id="s1",
            on_event=capture_event,
            **scanner_deps,
        )
        await scanner.scan()
        event_types = [e.type for e in events]
        assert "domain_started" in event_types
        assert "domain_complete" in event_types

    @pytest.mark.asyncio
    async def test_no_llm_client(self, scanner_deps):
        scanner_deps["llm_client"] = None
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0

    @pytest.mark.asyncio
    async def test_no_llm_client_logs_info(self, scanner_deps, caplog):
        """When LLM is unavailable, keyword matches should be logged (not silent)."""
        import logging
        scanner_deps["llm_client"] = None
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        with caplog.at_level(logging.INFO, logger="src.core.scanner"):
            await scanner.scan()
        assert any("keyword match" in r.message.lower() and "unavailable" in r.message.lower()
                    for r in caplog.records)

    @pytest.mark.asyncio
    async def test_skip_llm_logs_info(self, scanner_deps, caplog):
        """When LLM is explicitly skipped, keyword matches should be logged."""
        import logging
        scanner = DomainScanner(
            domain=_make_domain(), scan_id="s1", skip_llm=True, **scanner_deps,
        )
        with caplog.at_level(logging.INFO, logger="src.core.scanner"):
            await scanner.scan()
        assert any("keyword match" in r.message.lower() and "disabled" in r.message.lower()
                    for r in caplog.records)

    @pytest.mark.asyncio
    async def test_verifier_called_on_policies(self, scanner_deps):
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        await scanner.scan()
        scanner_deps["verifier"].verify_batch.assert_called_once()
        args = scanner_deps["verifier"].verify_batch.call_args
        assert len(args[0][0]) == 1  # One policy verified
        assert args[0][1] == ["us"]  # Domain regions passed
