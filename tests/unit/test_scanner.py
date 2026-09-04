"""Tests for DomainScanner pipeline with mocked dependencies."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.cache import URLCache
from src.core.instruments import InstrumentIndex
from src.core.models import (
    CrawlResult, PageStatus, Policy, PolicyType, PolicyAnalysis,
    ScreeningResult, KeywordResult, KeywordMatch, ExtractedContent,
    DEFAULT_SCREENER_REJECT_KINDS,
    DEFAULT_SCREENER_SOFT_REJECT_KINDS,
)
from src.core.scanner import DomainScanner, screening_decision
from src.core.scope import REQUIRED


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


def _make_crawl_result(
    url="https://example.gov/page",
    content="<html><body><p>Policy content about data center heat reuse requirements</p></body></html>",
    title=None,
):
    return CrawlResult(
        url=url,
        status=PageStatus.SUCCESS,
        content=content,
        content_length=len(content),
        title=title,
    )


def _make_extracted():
    return ExtractedContent(
        text="Policy content about data center heat reuse requirements " * 10,
        title="Policy Page",
        language="en",
        word_count=80,
    )


class TestScreeningDecision:
    """The pure gate function behind Stage 5a (WP-5, ADR-0011): hard kinds
    drop, soft kinds drop only without evidence, everything else proceeds,
    and a fallback (kind None) always proceeds."""

    REJECT_KINDS = list(DEFAULT_SCREENER_REJECT_KINDS)
    SOFT_KINDS = list(DEFAULT_SCREENER_SOFT_REJECT_KINDS)

    def _decide(self, **kw):
        kw.setdefault("relevant", True)
        kw.setdefault("confidence", 7)
        result = ScreeningResult(**kw)
        return screening_decision(result, self.REJECT_KINDS, self.SOFT_KINDS)

    @pytest.mark.small
    def test_a_fallback_with_no_kind_always_proceeds(self):
        assert self._decide(kind=None) == "proceed"

    @pytest.mark.small
    def test_a_question_drops_even_with_both_quotes(self):
        assert self._decide(kind="question", dc_quote="a data centre", heat_quote="waste heat") == "drop_kind"

    @pytest.mark.small
    def test_a_speech_drops(self):
        assert self._decide(kind="speech") == "drop_kind"

    @pytest.mark.small
    def test_a_report_without_evidence_drops(self):
        assert self._decide(kind="report") == "drop_kind"

    @pytest.mark.small
    def test_a_report_with_a_data_centre_quote_escalates(self):
        assert self._decide(kind="report", dc_quote="Operators of data centres must report.") == "escalate"

    @pytest.mark.small
    def test_an_article_with_only_a_heat_quote_escalates(self):
        assert self._decide(kind="article", heat_quote="Waste heat will warm 1,000 homes.") == "escalate"

    @pytest.mark.small
    def test_a_bill_with_no_quotes_proceeds_because_quotes_are_evidence_not_a_gate(self):
        """Lesson PL-008: the replay showed the model failing to quote a
        data-centre sentence on 14 of 23 kept pages the regex had matched."""
        assert self._decide(kind="bill") == "proceed"

    @pytest.mark.small
    def test_custom_lists_are_honoured(self):
        result = ScreeningResult(relevant=True, confidence=7, kind="grant")
        assert screening_decision(result, ["grant"], []) == "drop_kind"
        assert screening_decision(result, [], ["grant"]) == "drop_kind"
        result_with_quote = ScreeningResult(relevant=True, confidence=7, kind="grant", dc_quote="x")
        assert screening_decision(result_with_quote, [], ["grant"]) == "escalate"

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
        # WP-5: the classifier is a second cheap call; by default it falls
        # open (kind None), which screening_decision always lets through.
        llm_client.classify_document = AsyncMock(
            return_value=ScreeningResult(relevant=True, confidence=5, kind=None),
        )
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

        # LLM screening passes: a real kind (not on the reject list) plus
        # both quotes, so the page proceeds to analysis under WP-5's gate
        # the same way a bare relevant=True did before it.
        llm_client.screen_relevance = AsyncMock(
            return_value=ScreeningResult(
                relevant=True, confidence=8, kind="act",
                dc_quote="This act applies to data centers.",
                heat_quote="Operators must reuse waste heat.",
            ),
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
    async def test_structured_source_bypasses_keyword_and_short_gates(self, scanner_deps):
        """A LegiScan/GovInfo hit is a one-line bill already matched by the
        source's own query. The web-page keyword gate and the <50-word
        short-content gate must NOT drop it — it goes straight to LLM
        screening/analysis."""
        # Thin content (a bill title) that would fail both crawl gates:
        scanner_deps["extractor"].extract.return_value = ExtractedContent(
            text="Data centers: waste heat energy.",
            title="AB1095", language="en", word_count=5,
        )
        scanner_deps["keyword_matcher"].is_relevant.return_value = False

        scanner = DomainScanner(
            domain=_make_domain(source_type="legiscan"),
            scan_id="scan_1",
            **scanner_deps,
        )
        result = _make_crawl_result(url="https://leginfo.ca.gov/AB1095")
        policies = await scanner._process_page_isolated(result)

        assert len(policies) == 1                      # reached analysis
        assert scanner.progress.filtered_keywords == 0
        assert scanner.progress.filtered_short_content == 0

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
        # kind="bill" (not on the reject list) with no dc_quote: this drops
        # under WP-5's drop_no_dc rule, the same filtered_screening counter
        # a bare relevant=False rejection used before it.
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
        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(relevant=False, confidence=3, kind="bill"),
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

    # --- WP-5: the screener asks three narrow questions ---

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_report_kind_increments_screened_kind_and_skips_analysis(self, scanner_deps):
        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(
                relevant=True, confidence=9, kind="report",
                dc_quote=None,
                heat_quote=None,
            ),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.screened_kind == 1
        scanner_deps["llm_client"].analyze_policy.assert_not_awaited()

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_report_kind_logged_and_cached_by_kind(self, scanner_deps, caplog):
        import logging as _logging

        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(
                relevant=True, confidence=9, kind="report",
                dc_quote=None,
                heat_quote=None,
            ),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        with caplog.at_level(_logging.INFO, logger="src.core.scanner"):
            await scanner.scan()
        assert any(
            "document kind: report" in r.message.lower() and "example.gov" in r.message
            for r in caplog.records
        )
        cached = scanner_deps["cache"].get(
            "https://example.gov/page",
            scanner_deps["cache"]._entries["https://example.gov/page"].content_hash,
        )
        assert cached.policy_type == "report"
        assert cached.is_relevant is False

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_bill_with_both_quotes_proceeds_to_analysis(self, scanner_deps):
        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(
                relevant=True, confidence=8, kind="bill",
                dc_quote="This bill concerns data centers.",
                heat_quote="Operators must reuse waste heat.",
            ),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 1
        scanner_deps["llm_client"].analyze_policy.assert_awaited_once()

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_missing_quotes_are_evidence_not_a_gate_for_a_bill(self, scanner_deps):
        """Lesson PL-008: a bill the model could not quote still proceeds;
        the deterministic scope gate is the data-centre rule."""
        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(
                relevant=True, confidence=9, kind="bill",
                dc_quote=None, heat_quote=None,
            ),
        )
        scanner = DomainScanner(
            domain=_make_domain(), scan_id="s1",
            scope_setting=REQUIRED, **scanner_deps,
        )
        policies = await scanner.scan()
        assert len(policies) == 1
        assert scanner.progress.filtered_screening == 0
        assert scanner.progress.screened_kind == 0
        assert scanner_deps["llm_client"].analyze_policy.await_count == 1

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_a_report_without_evidence_drops_at_the_screener(self, scanner_deps):
        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(relevant=False, confidence=8, kind="report"),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.screened_kind == 1
        assert scanner_deps["llm_client"].analyze_policy.await_count == 0

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_an_article_with_evidence_escalates_to_analysis(self, scanner_deps):
        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(
                relevant=False, confidence=7, kind="article",
                dc_quote="DOE announces $40 million for data center cooling.",
            ),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 1
        assert scanner.progress.screened_kind == 0
        assert scanner_deps["llm_client"].analyze_policy.await_count == 1

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_evidence_lands_on_the_produced_policy(self, scanner_deps):
        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(
                relevant=True, confidence=8, kind="act",
                dc_quote="This act concerns data centers.",
                heat_quote="Operators must reuse waste heat.",
                quote_verified=True,
            ),
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        policies = await scanner.scan()
        assert len(policies) == 1
        assert policies[0].evidence == {
            "kind": "act",
            "dc_quote": "This act concerns data centers.",
            "heat_quote": "Operators must reuse waste heat.",
            "quote_verified": True,
        }

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_custom_reject_kinds_are_honored(self, scanner_deps):
        """screener_reject_kinds is configurable per scanner, not a
        hardcoded list - a kind added to the list must start dropping."""
        scanner_deps["llm_client"].classify_document = AsyncMock(
            return_value=ScreeningResult(
                relevant=True, confidence=9, kind="grant",
                dc_quote="A data centre is named here.",
                heat_quote="Heat is reused here.",
            ),
        )
        scanner = DomainScanner(
            domain=_make_domain(), scan_id="s1",
            screener_reject_kinds=["grant"], **scanner_deps,
        )
        policies = await scanner.scan()
        assert len(policies) == 0
        assert scanner.progress.screened_kind == 1

    @pytest.mark.small
    def test_changing_reject_kinds_changes_the_rules_fingerprint(self, tmp_path):
        """analysis.screener_reject_kinds lives inside the analysis block,
        so changing it must expire every cached verdict - the same
        mechanism that already covers data_center_required and the
        prompts (src/core/rules_version.py)."""
        import yaml

        from src.core import rules_version

        (tmp_path / "keywords.yaml").write_text("subject: []\n", encoding="utf-8")

        def _fingerprint(reject_kinds):
            (tmp_path / "settings.yaml").write_text(
                yaml.safe_dump({"analysis": {"screener_reject_kinds": reject_kinds}}),
                encoding="utf-8",
            )
            return rules_version.rules_fingerprint(rules_version.default_parts(tmp_path))

        before = _fingerprint(["report", "article"])
        after = _fingerprint(["report", "article", "speech"])
        assert before != after

    @pytest.mark.asyncio
    async def test_api_source_domain_bypasses_crawler(self, scanner_deps):
        """A domain with source_type != crawl fetches via its PolicySource
        and never touches the crawler; results flow through the pipeline."""
        from src.sources import SOURCE_REGISTRY
        from src.sources.base import PolicySource

        class _StubSource(PolicySource):
            id = "stub_bills"

            async def fetch(self, domain):
                return [_make_crawl_result(url="https://parliament.example.gov/bill/7")]

        SOURCE_REGISTRY["stub_bills"] = _StubSource
        try:
            scanner = DomainScanner(
                domain=_make_domain(source_type="stub_bills"),
                scan_id="s1", **scanner_deps,
            )
            policies = await scanner.scan()
        finally:
            SOURCE_REGISTRY.pop("stub_bills", None)

        scanner_deps["crawler"].crawl_domain.assert_not_awaited()
        assert len(policies) == 1

    @pytest.mark.asyncio
    @pytest.mark.medium
    async def test_source_dropped_doc_type_is_added_to_progress(self, scanner_deps):
        """A structured source's own document-type allow-list (DIP,
        Folketing; WP-3) counts its drops on the domain's progress, so the
        cost of the rule is visible rather than silent."""
        from src.sources import SOURCE_REGISTRY
        from src.sources.base import PolicySource

        class _StubSourceWithDrops(PolicySource):
            id = "stub_doc_type_drops"

            async def fetch(self, domain):
                self.dropped_doc_type = 3
                return [_make_crawl_result(url="https://parliament.example.gov/bill/11")]

        SOURCE_REGISTRY["stub_doc_type_drops"] = _StubSourceWithDrops
        try:
            scanner = DomainScanner(
                domain=_make_domain(source_type="stub_doc_type_drops"),
                scan_id="s1", **scanner_deps,
            )
            await scanner.scan()
        finally:
            SOURCE_REGISTRY.pop("stub_doc_type_drops", None)

        assert scanner.progress.filtered_doc_type == 3

    @pytest.mark.asyncio
    async def test_source_lifecycle_stage_lands_on_policy(self, scanner_deps):
        """A source-declared stage (e.g. bill status) overrides analysis."""
        from src.sources import SOURCE_REGISTRY
        from src.sources.base import PolicySource

        result = _make_crawl_result(url="https://parliament.example.gov/bill/9")
        result.lifecycle_stage = "in_committee"

        class _StubSource(PolicySource):
            id = "stub_stage"

            async def fetch(self, domain):
                return [result]

        real_policy = Policy(
            url="https://parliament.example.gov/bill/9", policy_name="Bill 9",
            jurisdiction="US", policy_type=PolicyType.LAW, summary="x",
            relevance_score=7,
        )
        scanner_deps["llm_client"].to_policies.return_value = [real_policy]

        SOURCE_REGISTRY["stub_stage"] = _StubSource
        try:
            scanner = DomainScanner(
                domain=_make_domain(source_type="stub_stage"),
                scan_id="s1", **scanner_deps,
            )
            policies = await scanner.scan()
        finally:
            SOURCE_REGISTRY.pop("stub_stage", None)

        assert policies[0].lifecycle_stage == "in_committee"

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

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_same_instrument_duplicate_is_folded_before_screening(self, scanner_deps):
        """WP-4: a crawl page describing an instrument already kept under a
        different URL folds into it instead of reaching the model.

        FAILS TODAY (before instrument_index wiring): the page proceeds all
        the way to Sonnet analysis like any other new page - screen_relevance
        is called and a policy comes back. After: filtered_duplicate counts
        it, scanner.duplicates records the fold, and screen_relevance is
        never awaited.
        """
        existing_url = "https://www.gesetze-im-internet.de/enefg/"
        index = InstrumentIndex.from_rows([
            {"policy_name": "Energy Efficiency Act (EnEfG)", "url": existing_url},
        ])
        page_url = "https://bundestag.de/referentenentwurf-enefg"
        result = _make_crawl_result(
            url=page_url,
            title="Energieeffizienzgesetz (EnEfG) - Referentenentwurf",
        )

        scanner = DomainScanner(
            domain=_make_domain(), scan_id="s1",
            instrument_index=index, **scanner_deps,
        )
        policies = await scanner._process_page_isolated(result)

        assert policies == []
        assert scanner.progress.filtered_duplicate == 1
        assert scanner.duplicates == [(existing_url, page_url)]
        scanner_deps["llm_client"].screen_relevance.assert_not_awaited()

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_instrument_index_off_by_default_keeps_old_behavior(self, scanner_deps):
        """No instrument_index passed (every construction site that
        predates WP-4) means the check never runs, even for a title that
        would otherwise match nothing anyway - this just pins that the
        default keeps every old call site working."""
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        result = _make_crawl_result(title="Some Other Act (SOA)")
        policies = await scanner._process_page_isolated(result)

        assert len(policies) == 1
        assert scanner.progress.filtered_duplicate == 0
        assert scanner.duplicates == []

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_soft_404_page_is_dropped_before_screening(self, scanner_deps):
        scanner_deps["extractor"].extract.return_value = ExtractedContent(
            text="Page not found. Sorry, the page you requested does not exist.",
            title="404", language="en", word_count=11,
        )
        scanner = DomainScanner(domain=_make_domain(), scan_id="s1", **scanner_deps)
        result = _make_crawl_result(url="https://example.gov/missing")
        policies = await scanner._process_page_isolated(result)

        assert policies == []
        assert scanner.progress.filtered_link == 1
        scanner_deps["llm_client"].screen_relevance.assert_not_awaited()

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_soft_404_never_checked_for_structured_records(self, scanner_deps):
        """Structured records are API records, never pages - the link
        check must not run for them, even when their thin content would
        otherwise look exactly like a soft 404. Mentions a data centre so
        the scope gate (an unrelated, later stage) does not also drop it,
        keeping this test isolated to the link check alone."""
        scanner_deps["extractor"].extract.return_value = ExtractedContent(
            text="404 data center bill", title="404", language="en", word_count=4,
        )
        scanner = DomainScanner(
            domain=_make_domain(source_type="legiscan"), scan_id="s1", **scanner_deps,
        )
        result = _make_crawl_result(url="https://leginfo.ca.gov/AB1")
        policies = await scanner._process_page_isolated(result)

        assert scanner.progress.filtered_link == 0
        assert len(policies) == 1  # reached analysis, same as any structured hit

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_two_policies_from_one_page_with_same_keys_fold_into_one(self, scanner_deps):
        page_url = "https://example.gov/index-page"
        scanner_deps["llm_client"].to_policies.return_value = [
            Policy(
                url=page_url, policy_name="Heat Recovery Act (HRA)",
                jurisdiction="US", policy_type=PolicyType.LAW,
                summary="x", relevance_score=7,
            ),
            Policy(
                url=page_url, policy_name="Heat Recovery Act (HRA)",
                jurisdiction="US", policy_type=PolicyType.LAW,
                summary="x", relevance_score=7,
            ),
        ]
        scanner = DomainScanner(
            domain=_make_domain(), scan_id="s1",
            instrument_index=InstrumentIndex(), **scanner_deps,
        )
        result = _make_crawl_result(url=page_url)
        policies = await scanner._process_page_isolated(result)

        assert len(policies) == 1
        assert scanner.progress.filtered_duplicate == 1

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_policy_matching_an_existing_row_is_dropped_and_recorded(self, scanner_deps):
        existing_url = "https://www.gesetze-im-internet.de/enefg/"
        index = InstrumentIndex.from_rows([
            {"policy_name": "Energy Efficiency Act (EnEfG)", "url": existing_url},
        ])
        page_url = "https://example.gov/enefg-news"
        scanner_deps["llm_client"].to_policies.return_value = [Policy(
            url=page_url, policy_name="Energieeffizienzgesetz (EnEfG)",
            jurisdiction="Germany", policy_type=PolicyType.LAW,
            summary="x", relevance_score=6,
        )]
        scanner = DomainScanner(
            domain=_make_domain(), scan_id="s1",
            instrument_index=index, **scanner_deps,
        )
        result = _make_crawl_result(url=page_url)
        policies = await scanner._process_page_isolated(result)

        assert policies == []
        assert scanner.progress.filtered_duplicate == 1
        assert scanner.duplicates == [(existing_url, page_url)]

    @pytest.mark.medium
    @pytest.mark.asyncio
    async def test_surviving_policy_is_added_so_a_later_page_folds_into_it(self, scanner_deps):
        """A policy that survives Stage 6b is registered in the shared
        index, so the second LegiScan copy of the same act - found on a
        later page in the same scan - folds into the first."""
        index = InstrumentIndex()
        first_url = "https://example.gov/first-copy"
        scanner_deps["llm_client"].to_policies.return_value = [Policy(
            url=first_url, policy_name="Shared Act (SHA)",
            jurisdiction="US", policy_type=PolicyType.LAW,
            summary="x", relevance_score=7,
        )]
        scanner = DomainScanner(
            domain=_make_domain(), scan_id="s1", instrument_index=index, **scanner_deps,
        )
        first_result = _make_crawl_result(url=first_url)
        first_policies = await scanner._process_page_isolated(first_result)
        assert len(first_policies) == 1

        second_url = "https://example.gov/second-copy"
        scanner_deps["llm_client"].to_policies.return_value = [Policy(
            url=second_url, policy_name="Shared Act (SHA)",
            jurisdiction="US", policy_type=PolicyType.LAW,
            summary="x", relevance_score=7,
        )]
        second_result = _make_crawl_result(url=second_url)
        second_policies = await scanner._process_page_isolated(second_result)

        assert second_policies == []
        assert scanner.duplicates == [(first_url, second_url)]
