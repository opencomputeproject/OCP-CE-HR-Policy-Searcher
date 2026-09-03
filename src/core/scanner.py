"""Single-domain scanning pipeline — the unit of parallelism.

Pipeline stages:
  crawl → extract → url_filter → keywords → cache_check
  → haiku_screen → sonnet_analyze → verify
"""

import logging
from typing import Optional, Callable, Awaitable
from urllib.parse import urlparse

from .cache import URLCache, compute_content_hash
from .instruments import InstrumentIndex, instrument_keys
from .scope import DEFAULT_SETTING as DEFAULT_SCOPE
from .scope import OUT_OF_SCOPE, scope_verdict
from .soft404 import looks_like_soft_404
from .crawler import AsyncCrawler
from .extractor import HtmlExtractor
from .keywords import KeywordMatcher
from .llm import ClaudeClient, LLMAuthError
from .models import (
    CrawlResult, Policy, DomainProgress, DomainScanStatus,
    ScanEvent, ScreeningResult, DEFAULT_SCREENER_REJECT_KINDS,
    DEFAULT_SCREENER_SOFT_REJECT_KINDS,
)
from .verifier import Verifier

logger = logging.getLogger(__name__)


def screening_decision(
    result: ScreeningResult,
    reject_kinds: list[str],
    soft_reject_kinds: list[str],
) -> str:
    """Where a classified page goes next: ``drop_kind``, ``escalate`` or
    ``proceed`` (WP-5, ADR-0011). Applied to the classifier's answer, after
    the original screening gate has already passed the page.

    A pure function so Stage 5a and the recorded-fixture replay test
    (tests/unit/test_screening_replay.py) share the exact same gate rather
    than two copies that can drift apart. Checked in order:

    0. ``kind`` is ``None`` - a parsing/API fallback, never a real verdict -
       always proceeds.
    1. ``kind`` on ``reject_kinds`` (question, speech by default) ->
       ``drop_kind``, even with both quotes: a parliamentary question that
       names a data centre and its waste heat is still a question.
    2. ``kind`` on ``soft_reject_kinds`` (report, article by default) ->
       ``drop_kind`` when the classifier found neither quote, ``escalate``
       (the strong model decides) when it found either. Measured 2026-09-03
       on the reviewer's rows: her kept agency pages and press release were
       labelled report/article with quotes, so a hard drop loses keeps.
    3. any other kind -> ``proceed``.

    The quotes never gate on their own. The deterministic scope gate on
    source text (Stage 4b, ADR-0001) is the data-centre rule; the replay
    showed the model failing to quote a data-centre sentence on 14 of 23
    kept pages the regex had matched. Lesson PL-008.
    """
    if result.kind is None:
        return "proceed"
    if result.kind in reject_kinds:
        return "drop_kind"
    if result.kind in soft_reject_kinds:
        return "escalate" if (result.dc_quote or result.heat_quote) else "drop_kind"
    return "proceed"


class DomainScanner:
    """Scans a single domain through the full pipeline."""

    def __init__(
        self,
        domain: dict,
        crawler: AsyncCrawler,
        extractor: HtmlExtractor,
        keyword_matcher: KeywordMatcher,
        llm_client: Optional[ClaudeClient],
        cache: URLCache,
        verifier: Verifier,
        scan_id: str = "",
        skip_llm: bool = False,
        on_event: Optional[Callable[[ScanEvent], Awaitable[None]]] = None,
        screening_min_confidence: int = 5,
        scope_setting: str = DEFAULT_SCOPE,
        instrument_index: Optional[InstrumentIndex] = None,
        screener_reject_kinds: Optional[list[str]] = None,
        screener_soft_reject_kinds: Optional[list[str]] = None,
    ):
        self.domain = domain
        self.crawler = crawler
        self.extractor = extractor
        self.keyword_matcher = keyword_matcher
        self.llm_client = llm_client
        self.cache = cache
        self.verifier = verifier
        self.scan_id = scan_id
        self.skip_llm = skip_llm
        self.on_event = on_event
        self.screening_min_confidence = screening_min_confidence
        self.scope_setting = scope_setting
        # Document kinds the screener drops before analysis (WP-5). None
        # (every construction site that predates this - see
        # src/orchestration/scan_manager.py, which does not yet forward
        # config/settings.yaml's analysis.screener_reject_kinds here) falls
        # back to the same default that setting carries, so the gate is on
        # with sane behavior even where it is not explicitly wired.
        self.screener_reject_kinds = (
            list(DEFAULT_SCREENER_REJECT_KINDS) if screener_reject_kinds is None
            else screener_reject_kinds
        )
        self.screener_soft_reject_kinds = (
            list(DEFAULT_SCREENER_SOFT_REJECT_KINDS) if screener_soft_reject_kinds is None
            else screener_soft_reject_kinds
        )
        # Same-instrument duplicate check (WP-4). None (the default) means
        # the check is off, so every construction site that predates it
        # keeps working. Built once per scan and shared across every
        # domain's DomainScanner - see src/orchestration/scan_manager.py.
        self.instrument_index = instrument_index
        # (existing_url, new_url) pairs folded during this domain's scan,
        # always initialised regardless of instrument_index - drained by
        # the scan manager into PolicyStore.add_related_url after this
        # domain completes.
        self.duplicates: list[tuple[str, str]] = []

        self.domain_id = domain.get("id", "")
        self.progress = DomainProgress(
            domain_id=self.domain_id,
            domain_name=domain.get("name", ""),
        )

    async def _emit(self, event_type: str, data: dict = None) -> None:
        """Emit a scan event."""
        if self.on_event:
            event = ScanEvent(
                scan_id=self.scan_id,
                type=event_type,
                domain_id=self.domain_id,
                data=data or {},
            )
            await self.on_event(event)

    async def scan(self) -> list[Policy]:
        """Run the full pipeline for this domain. Returns discovered policies."""
        self.progress.status = DomainScanStatus.RUNNING
        await self._emit("domain_started", {"domain_name": self.domain.get("name", "")})

        policies: list[Policy] = []

        try:
            # Stage 1: Acquire documents — structured source or crawl
            source_type = self.domain.get("source_type", "crawl")
            if source_type != "crawl":
                from ..sources import get_source
                source = get_source(source_type)
                logger.info(
                    "Domain %s uses structured source '%s'",
                    self.domain_id, source_type,
                )
                crawl_results = await source.fetch(self.domain)
                # Count records the source itself excluded by document type,
                # before any page was fetched or any model was called.
                self.progress.filtered_doc_type += getattr(source, "dropped_doc_type", 0)
                for r in crawl_results:
                    r.domain_id = self.domain_id
            else:
                crawl_results = await self.crawler.crawl_domain(
                    base_url=self.domain["base_url"],
                    start_paths=self.domain.get("start_paths", ["/"]),
                    domain_id=self.domain_id,
                    allowed_path_patterns=self.domain.get("allowed_path_patterns"),
                    blocked_path_patterns=self.domain.get("blocked_path_patterns"),
                    max_depth_override=self.domain.get("max_depth"),
                    max_pages_override=self.domain.get("max_pages"),
                    requires_playwright=self.domain.get("requires_playwright", False),
                )

            self.progress.pages_crawled = len(crawl_results)

            # Process each successful page through the pipeline
            processed_urls = {r.url for r in crawl_results}
            for result in crawl_results:
                if not result.is_success or not result.content:
                    if result.is_blocked:
                        self.progress.errors += 1
                    continue

                await self._emit("page_fetched", {
                    "url": result.url,
                    "status": result.status.value,
                    "response_ms": result.response_time_ms,
                })

                page_policies = await self._process_page_isolated(result)
                for policy in page_policies:
                    policies.append(policy)
                    self.progress.policies_found += 1
                    await self._emit("policy_found", {
                        "url": policy.url,
                        "policy_name": policy.policy_name,
                        "relevance": policy.relevance_score,
                    })

            # Citation follow-up: analysis extracts referenced_urls from
            # every policy; laws cite laws, so same-site references we did
            # not crawl are fetched and processed too.
            followup_policies = await self._follow_referenced_urls(
                policies, processed_urls,
            )
            for policy in followup_policies:
                policies.append(policy)
                self.progress.policies_found += 1
                await self._emit("policy_found", {
                    "url": policy.url,
                    "policy_name": policy.policy_name,
                    "relevance": policy.relevance_score,
                })

            # Verify all policies for this domain
            domain_regions = self.domain.get("region", [])
            self.verifier.verify_batch(policies, domain_regions)

            self.progress.status = DomainScanStatus.COMPLETED

        except Exception as e:
            logger.error(f"Domain scan failed for {self.domain_id}: {e}")
            self.progress.status = DomainScanStatus.FAILED
            self.progress.error_message = str(e)
            self.progress.errors += 1
            await self._emit("error", {
                "domain_id": self.domain_id,
                "error": str(e),
            })

        if self.progress.filtered_out_of_scope:
            logger.info(
                "%s: %d pages dropped by the data-centre scope rule (setting=%s)",
                self.domain_id, self.progress.filtered_out_of_scope,
                self.scope_setting,
            )

        await self._emit("domain_complete", {
            "pages": self.progress.pages_crawled,
            "policies": self.progress.policies_found,
            "errors": self.progress.errors,
            "out_of_scope": self.progress.filtered_out_of_scope,
        })

        return policies

    MAX_REFERENCED_URLS = 20  # follow-up fetch budget per domain

    async def _process_page_isolated(self, result: CrawlResult) -> list[Policy]:
        """Run _process_page with per-page error isolation.

        One failed page (rate-limit exhaustion, parse error) must not lose
        the rest of the domain; an auth failure affects every page and
        still aborts.
        """
        try:
            return await self._process_page(result)
        except LLMAuthError:
            raise
        except Exception as e:
            logger.error(
                "Page processing failed for %s: %s — continuing with "
                "remaining pages", result.url, e,
            )
            self.progress.errors += 1
            return []

    async def _follow_referenced_urls(
        self, policies: list[Policy], processed_urls: set[str],
    ) -> list[Policy]:
        """Fetch and process same-site URLs cited by discovered policies."""
        base_netloc = urlparse(self.domain["base_url"]).netloc
        queue: list[str] = []
        for policy in policies:
            for ref in policy.referenced_urls:
                if ref in processed_urls or ref in queue:
                    continue
                parsed = urlparse(ref)
                if parsed.scheme not in ("http", "https"):
                    continue
                if not AsyncCrawler._same_site(parsed.netloc, base_netloc):
                    logger.info(
                        "Referenced URL is cross-site, not auto-followed: %s",
                        ref,
                    )
                    continue
                queue.append(ref)

        if not queue:
            return []
        if len(queue) > self.MAX_REFERENCED_URLS:
            logger.info(
                "Capping referenced-URL follow-up at %d of %d candidates",
                self.MAX_REFERENCED_URLS, len(queue),
            )
            queue = queue[:self.MAX_REFERENCED_URLS]

        found: list[Policy] = []
        for url in queue:
            processed_urls.add(url)
            result = await self.crawler.fetch_url(url)
            result.domain_id = self.domain_id
            if not result.is_success or not result.content:
                continue
            logger.info("Following referenced policy URL: %s", url)
            found.extend(await self._process_page_isolated(result))
        return found

    async def _process_page(self, result: CrawlResult) -> list[Policy]:
        """Process a single page through extract → keywords → LLM → verify."""

        # Stage 2: Extract content
        extracted = self.extractor.extract(result.content, result.url)

        # Structured sources (LegiScan, GovInfo, DIP, ...) return one-line
        # bills already matched by the source's own targeted query. The web-
        # page gates below — the <50-word short filter and the keyword score
        # gate — are tuned for full HTML pages and would wrongly drop these
        # thin-but-relevant hits, so skip them and let the LLM screen/analyze.
        is_structured = self.domain.get("source_type", "crawl") != "crawl"

        if not is_structured:
            # Stage 2b: the link check. A soft 404 - a missing-page
            # placeholder answered with a 200 status - looks like a page
            # but is not a document, and should never cost a screening or
            # analysis call. Structured records are API records, never
            # pages, so this never runs for them.
            if looks_like_soft_404(extracted.title, extracted.text or "", result.url):
                self.progress.pages_filtered += 1
                self.progress.filtered_link += 1
                logger.info(
                    "Dropped at link check (looks like a missing page): %s",
                    result.url,
                )
                self.cache.set(
                    result.url, is_relevant=False,
                    relevance_score=0,
                    content_hash=compute_content_hash(extracted.text or ""),
                )
                return []

            if not extracted.text or extracted.word_count < 50:
                self.progress.pages_filtered += 1
                self.progress.filtered_short_content += 1
                return []

            # Stage 3: Keyword matching
            kw_result = self.keyword_matcher.match(extracted.text)
            if kw_result.is_excluded:
                self.progress.pages_filtered += 1
                self.progress.filtered_excluded += 1
                return []

            min_score = self.domain.get("min_keyword_score")
            is_relevant = self.keyword_matcher.is_relevant(
                kw_result, url=result.url, min_score_override=min_score,
            )
        else:
            kw_result = self.keyword_matcher.match(extracted.text or "")
            is_relevant = True

        if not is_relevant:
            self.progress.pages_filtered += 1
            self.progress.filtered_keywords += 1
            # Near misses at INFO: these are the pages to inspect when
            # tuning thresholds or keyword lists.
            if self.keyword_matcher.check_near_miss(kw_result, url=result.url, min_score_override=min_score):
                kw_result.is_near_miss = True
                self.progress.near_misses += 1
                logger.info(
                    "Near miss at keyword gate: %s (score=%.1f+%.1f url bonus, "
                    "matched=%s)",
                    result.url, kw_result.score, kw_result.url_bonus,
                    [m.term for m in kw_result.matches],
                )
            else:
                logger.info(
                    "Dropped at keyword gate: %s (score=%.1f, matches=%d)",
                    result.url, kw_result.score, len(kw_result.matches),
                )
            return []

        self.progress.keywords_matched += 1
        await self._emit("keyword_match", {
            "url": result.url,
            "score": kw_result.score + kw_result.url_bonus,
            "categories": kw_result.categories_matched,
        })

        # Stage 4: Cache check
        content_hash = compute_content_hash(extracted.text)
        cached = self.cache.get(result.url, content_hash)
        if cached:
            if not cached.is_relevant:
                return []
            # Still return a policy stub from cache? For now skip re-analysis.
            logger.debug(f"Cache hit: {result.url}")
            return []  # Cache hit means we already have this policy

        # Stage 4a: same-instrument duplicate check, on the page's own
        # title. Both lanes have rejoined by here too - a structured
        # record's title (a bill's short title, say) is checked exactly
        # like a crawled page's. A hit means this page is the same
        # instrument as a row already kept, so it is folded in instead of
        # costing a screening/analysis call on a second copy. Off when no
        # instrument_index was wired in (see __init__).
        if self.instrument_index is not None:
            title_keys = instrument_keys(result.title)
            existing_url = self.instrument_index.match(title_keys, exclude_url=result.url)
            if existing_url:
                self.progress.pages_filtered += 1
                self.progress.filtered_duplicate += 1
                self.duplicates.append((existing_url, result.url))
                logger.info(
                    "Folded into %s (same instrument): %s",
                    existing_url, result.url,
                )
                self.cache.set(
                    result.url, is_relevant=False,
                    relevance_score=0, content_hash=content_hash,
                )
                return []

        # Stage 4b: scope gate. Both lanes have rejoined by here, so
        # this is the earliest point that sees every document: the
        # keyword gate above is skipped entirely by structured sources.
        # Runs before any model call, so an out-of-scope document costs
        # nothing.
        verdict = scope_verdict(extracted.text or "", self.scope_setting)
        if verdict == OUT_OF_SCOPE:
            self.progress.pages_filtered += 1
            self.progress.filtered_out_of_scope += 1
            logger.info(
                "Dropped at scope gate (no data centre reference): %s",
                result.url,
            )
            self.cache.set(
                result.url, is_relevant=False,
                relevance_score=0, content_hash=content_hash,
            )
            return []

        # Stage 5: LLM analysis (skip if disabled)
        if self.skip_llm or not self.llm_client:
            # Cache as "needs LLM" but don't analyze
            self.cache.set(
                result.url, is_relevant=True,
                relevance_score=0, content_hash=content_hash,
            )
            self.progress.llm_skipped += 1
            logger.info(
                "Keyword match at %s but LLM analysis %s — "
                "page cached for future re-scan with LLM enabled",
                result.url,
                "disabled" if self.skip_llm else "unavailable (no API key)",
            )
            return []

        # Stage 5a: Haiku screening - three narrow questions (WP-5): what
        # kind of document, and the source-text sentences (if any) naming a
        # data centre and describing heat reuse. screening_decision is a
        # pure function (defined above) so the exact same gate can be
        # replayed against recorded fixtures in
        # tests/unit/test_screening_replay.py.
        screening = await self.llm_client.screen_relevance(
            extracted.text, result.url,
            anchor_terms=[m.term for m in kw_result.matches],
        )
        if not screening.relevant:
            if screening.confidence >= self.screening_min_confidence:
                self.progress.pages_filtered += 1
                self.progress.filtered_screening += 1
                logger.info(
                    "Dropped at screening gate: %s (confidence=%d)",
                    result.url, screening.confidence,
                )
                self.cache.set(
                    result.url, is_relevant=False,
                    relevance_score=0, content_hash=content_hash,
                )
                return []
            # Borderline rejection: the screener is not confident enough to
            # make the final call - the strong model decides.
            logger.info(
                "Borderline screening rejection for %s (confidence=%d < %d) "
                "- escalating to analysis",
                result.url, screening.confidence, self.screening_min_confidence,
            )

        # Stage 5a2: the classifier (WP-5). A second cheap call, only for
        # pages the gate passed: the document kind drives the hard and soft
        # kind lists; the quotes are evidence on the row.
        classification = await self.llm_client.classify_document(
            extracted.text, result.url,
            anchor_terms=[m.term for m in kw_result.matches],
        )
        decision = screening_decision(
            classification, self.screener_reject_kinds, self.screener_soft_reject_kinds,
        )
        if decision == "drop_kind":
            self.progress.pages_filtered += 1
            self.progress.screened_kind += 1
            logger.info(
                "Dropped at screening (document kind: %s): %s",
                classification.kind, result.url,
            )
            self.cache.set(
                result.url, is_relevant=False,
                relevance_score=0, content_hash=content_hash,
                policy_type=classification.kind,
            )
            return []
        if decision == "escalate":
            logger.info(
                "Classified as %s with evidence, the strong model decides: %s",
                classification.kind, result.url,
            )
        # decision == "proceed" falls through silently, same as today.

        # Stage 5b: Sonnet analysis
        analysis = await self.llm_client.analyze_policy(
            extracted.text, result.url, extracted.language,
        )

        # Cache the result
        self.cache.set(
            result.url,
            is_relevant=analysis.is_relevant,
            relevance_score=analysis.relevance_score,
            content_hash=content_hash,
            policy_type=analysis.policy_type,
        )

        # Stage 6: Convert to Policy records (index pages can hold several)
        policies = self.llm_client.to_policies(
            analysis, result.url,
            language=extracted.language or "en",
            domain_id=self.domain_id,
            scan_id=self.scan_id,
        )
        # A source-declared stage (bill status, open consultation) is
        # authoritative over the analysis model's inference.
        if result.lifecycle_stage:
            for policy in policies:
                policy.lifecycle_stage = result.lifecycle_stage

        # Evidence from the screener rides on every policy this page
        # produced (WP-5): the document kind, the two quotes, and whether
        # they were actually found in the excerpt - so a reviewer can see
        # why the row exists without re-reading the source page.
        if policies:
            evidence = {
                "kind": classification.kind,
                "dc_quote": classification.dc_quote,
                "heat_quote": classification.heat_quote,
                "quote_verified": classification.quote_verified,
            }
            for policy in policies:
                policy.evidence = evidence

        # Stage 6b: same-instrument fold on the extracted policy name(s).
        # The pre-screen check above only sees the page's own title; the
        # model may extract a cleaner name (or several, from an index
        # page) that reveals a match the title alone missed. Checked
        # in order and added to the index as each survives, so a second
        # policy from this same page sharing the first one's keys folds
        # into it too - not just matches against rows from earlier pages.
        if self.instrument_index is not None and policies:
            survivors: list[Policy] = []
            page_keys: set[str] = set()
            for policy in policies:
                keys = instrument_keys(policy.policy_name, policy.policy_name_en)
                # A key shared with an earlier policy from this very page
                # is a sibling, not a stale self-record - fold it without
                # consulting the index (which would otherwise treat the
                # shared page URL as "its own" and refuse the match).
                existing_url = (
                    policy.url if keys & page_keys
                    else self.instrument_index.match(keys, exclude_url=policy.url)
                )
                if existing_url:
                    self.progress.pages_filtered += 1
                    self.progress.filtered_duplicate += 1
                    self.duplicates.append((existing_url, policy.url))
                    logger.info(
                        "Folded into %s (same instrument): %s",
                        existing_url, policy.url,
                    )
                    continue
                page_keys |= keys
                self.instrument_index.add(policy)
                survivors.append(policy)
            policies = survivors

        return policies
