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
        llm_client.to_policies.return_value = [Policy(
            url="https://example.gov/page",
            policy_name="Heat Recovery Act",
            jurisdiction="US",
            policy_type=PolicyType.LAW,
            summary="A law about heat recovery",
            relevance_score=8,
            domain_id="test_domain",
            scan_id="scan_1",
        )]

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
        assert scanner.progress.filtered_short_content == 1

    @pytest.mark.asyncio
    async def test_filters_excluded_content(self, scanner_deps):
        scanner_deps["keyword_matcher"].match.return_value = KeywordResult(
            score=0.0, is_excluded=True,
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.pages_filtered == 1
        assert scanner.progress.filtered_excluded == 1

    @pytest.mark.asyncio
    async def test_filters_low_keyword_score(self, scanner_deps):
        scanner_deps["keyword_matcher"].is_relevant.return_value = False
        scanner_deps["keyword_matcher"].check_near_miss.return_value = False
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.filtered_keywords == 1

    @pytest.mark.asyncio
    async def test_keyword_rejection_is_logged_visibly(self, scanner_deps, caplog):
        """A dropped page must leave a trace at INFO, the default log level."""
        import logging as _logging

        scanner_deps["keyword_matcher"].is_relevant.return_value = False
        scanner_deps["keyword_matcher"].check_near_miss.return_value = False
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        with caplog.at_level(_logging.INFO, logger="src.core.scanner"):
            await scanner.scan()
        assert any(
            "keyword gate" in r.message.lower() and "example.gov" in r.message
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_near_miss_counted_and_logged(self, scanner_deps, caplog):
        import logging as _logging

        scanner_deps["keyword_matcher"].is_relevant.return_value = False
        scanner_deps["keyword_matcher"].check_near_miss.return_value = True
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        with caplog.at_level(_logging.INFO, logger="src.core.scanner"):
            await scanner.scan()
        assert scanner.progress.near_misses == 1
        assert any("near miss" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_screening_rejection_counted(self, scanner_deps):
        scanner_deps["llm_client"].screen_relevance = AsyncMock(
            return_value=ScreeningResult(relevant=False, confidence=9),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        await scanner.scan()
        assert scanner.progress.filtered_screening == 1

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
    async def test_low_confidence_rejection_escalates_to_analysis(self, scanner_deps):
        """A barely-confident Haiku rejection must not be final: below
        screening_min_confidence the page escalates to Sonnet analysis."""
        scanner_deps["llm_client"].screen_relevance = AsyncMock(
            return_value=ScreeningResult(relevant=False, confidence=3),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        scanner_deps["llm_client"].analyze_policy.assert_awaited_once()
        assert len(policies) == 1

    @pytest.mark.asyncio
    async def test_screening_min_confidence_is_configurable(self, scanner_deps):
        scanner_deps["llm_client"].screen_relevance = AsyncMock(
            return_value=ScreeningResult(relevant=False, confidence=3),
        )
        scanner = DomainScanner(
            domain=_make_domain(), scan_id="s1",
            screening_min_confidence=2, **scanner_deps,
        )
        policies = await scanner.scan()
        assert len(policies) == 0
        scanner_deps["llm_client"].analyze_policy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_multiple_policies_from_one_page(self, scanner_deps):
        """An index page listing several laws yields several records."""
        def _policy(name):
            return Policy(
                url="https://example.gov/page", policy_name=name,
                jurisdiction="US", policy_type=PolicyType.LAW,
                summary="x", relevance_score=7,
            )
        scanner_deps["llm_client"].to_policies.return_value = [
            _policy("Act One"), _policy("Act Two"), _policy("Act Three"),
        ]
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 3
        assert scanner.progress.policies_found == 3

    @pytest.mark.asyncio
    async def test_referenced_urls_are_followed(self, scanner_deps):
        """Same-site referenced_urls from analysis feed back into the scan."""
        scanner_deps["llm_client"].to_policies.return_value = [Policy(
            url="https://example.gov/page", policy_name="Heat Recovery Act",
            jurisdiction="US", policy_type=PolicyType.LAW, summary="x",
            relevance_score=8,
            referenced_urls=[
                "https://example.gov/related-act",   # same site: follow
                "https://elsewhere.org/other",        # cross-site: skip
            ],
        )]
        followup = _make_crawl_result(url="https://example.gov/related-act")
        scanner_deps["crawler"].fetch_url = AsyncMock(return_value=followup)

        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        await scanner.scan()

        fetched = [c.args[0] for c in scanner_deps["crawler"].fetch_url.await_args_list]
        assert "https://example.gov/related-act" in fetched
        assert not any("elsewhere.org" in u for u in fetched)

    @pytest.mark.asyncio
    async def test_llm_error_on_one_page_does_not_abort_domain(self, scanner_deps):
        """Rate-limit exhaustion on one page must not lose the rest of the
        domain's pages."""
        from src.core.llm import LLMRateLimitError

        page1 = _make_crawl_result(url="https://example.gov/fails")
        page2 = _make_crawl_result(url="https://example.gov/works")
        scanner_deps["crawler"].crawl_domain = AsyncMock(return_value=[page1, page2])
        scanner_deps["llm_client"].analyze_policy = AsyncMock(
            side_effect=[
                LLMRateLimitError("rate limit after retries"),
                PolicyAnalysis(
                    is_relevant=True, relevance_score=8, policy_type="law",
                    policy_name="Heat Recovery Act", jurisdiction="US",
                    summary="A law about heat recovery",
                ),
            ],
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 1
        assert scanner.progress.errors == 1
        assert scanner.progress.status.value == "completed"

    @pytest.mark.asyncio
    async def test_auth_error_still_aborts_domain(self, scanner_deps):
        """An invalid API key affects every page: continuing is pointless."""
        from src.core.llm import LLMAuthError

        scanner_deps["llm_client"].analyze_policy = AsyncMock(
            side_effect=LLMAuthError("bad key"),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.status.value == "failed"

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
