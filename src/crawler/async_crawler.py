"""Main async crawler."""

import asyncio
import fnmatch
import warnings
from urllib.parse import urljoin, urlparse
from typing import Optional

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from ..config.settings import CrawlSettings
from ..models.crawl import CrawlResult, PageStatus
from ..analysis.keywords import KeywordMatcher
from ..logging.run_logger import RunLogger
from .fetchers.http_fetcher import HttpFetcher
from .fetchers.playwright_fetcher import PlaywrightFetcher
from .extractors.html_extractor import HtmlExtractor, load_extraction_config
from .detection.paywall import detect_paywall
from .detection.captcha import detect_captcha
from .detection.js_required import detect_js_required


_DEFAULT_SKIP_EXTENSIONS = [".pdf", ".doc", ".docx", ".zip", ".jpg", ".png"]

# Navigation tags to remove before link extraction.
# These contain global nav links that cause crawl explosion on SPAs.
_NAV_TAGS_FOR_LINK_EXTRACTION = ["nav", "header", "footer"]


class AsyncCrawler:
    def __init__(
        self,
        settings: CrawlSettings,
        domains: list[dict],
        keyword_matcher: KeywordMatcher,
        logger: RunLogger,
        skip_extensions: Optional[list[str]] = None,
        crawl_blocked_patterns: Optional[list[str]] = None,
    ):
        self.settings = settings
        self.domains = domains
        self.keyword_matcher = keyword_matcher
        self.logger = logger
        self.skip_extensions = [
            ext.lower() for ext in (skip_extensions or _DEFAULT_SKIP_EXTENSIONS)
        ]
        self.crawl_blocked_patterns = crawl_blocked_patterns or []

        self.http_fetcher = HttpFetcher(settings)
        self.playwright_fetcher: Optional[PlaywrightFetcher] = None

        # Load content extraction config
        extraction_config = load_extraction_config()
        self.html_extractor = HtmlExtractor(extraction_config)

        self._visited: set[str] = set()

    async def crawl_all(self) -> list[CrawlResult]:
        results = []

        try:
            await self.http_fetcher.initialize()

            for domain in self.domains:
                if not domain.get("enabled", True):
                    continue

                self.logger.info(f"Starting: {domain['id']}")
                domain_results = await self.crawl_domain(domain)
                results.extend(domain_results)

                success = sum(1 for r in domain_results if r.is_success)
                blocked = sum(1 for r in domain_results if r.is_blocked)
                self.logger.info(f"Complete: {len(domain_results)} pages, {success} ok, {blocked} blocked")
        finally:
            await self.http_fetcher.close()
            if self.playwright_fetcher:
                await self.playwright_fetcher.close()

        return results

    async def crawl_domain(self, domain: dict) -> list[CrawlResult]:
        results = []
        base_url = domain["base_url"]
        max_depth = domain.get("max_depth", self.settings.max_depth)
        max_pages = domain.get("max_pages", self.settings.max_pages_per_domain)
        domain_id = domain.get("id", "")

        queue = [(urljoin(base_url, p), 0) for p in domain.get("start_paths", ["/"])]

        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)

            if url in self._visited:
                continue
            self._visited.add(url)

            result = await self._fetch_page(url, domain)
            result.domain_id = domain_id
            results.append(result)

            if result.is_success:
                self.logger.success(f"Fetched: {urlparse(url).path} ({result.response_time_ms}ms)")

                if depth < max_depth:
                    links = self._extract_links(result.content, url, domain)
                    for link in links:
                        if link not in self._visited:
                            queue.append((link, depth + 1))
            elif result.is_blocked:
                reason = f" ({result.error_message})" if result.error_message else ""
                self.logger.warning(f"{result.status.value}: {urlparse(url).path}{reason}")
            else:
                self.logger.warning(f"Error: {urlparse(url).path} - {result.error_message}")

        return results

    async def _fetch_page(self, url: str, domain: dict) -> CrawlResult:
        use_playwright = self.settings.force_playwright or domain.get("requires_playwright", False)

        if not use_playwright:
            result = await self.http_fetcher.fetch(url)

            if result.is_success:
                extracted = self.html_extractor.extract(result.content, url)
                needs_js, _ = detect_js_required(result.content, extracted.text)
                if needs_js:
                    use_playwright = True

        if use_playwright:
            if not self.playwright_fetcher:
                self.playwright_fetcher = PlaywrightFetcher(self.settings)
                await self.playwright_fetcher.initialize()
            result = await self.playwright_fetcher.fetch(url)

        if result.is_success:
            extracted = self.html_extractor.extract(result.content, url)
            result.title = extracted.title
            result.language = extracted.language

            is_paywall, reason = detect_paywall(result.content, extracted.text)
            if is_paywall:
                result.status = PageStatus.PAYWALL_DETECTED
                result.error_message = reason
                result.requires_human_review = True

            is_captcha, reason = detect_captcha(result.content)
            if is_captcha:
                result.status = PageStatus.CAPTCHA_DETECTED
                result.error_message = reason
                result.requires_human_review = True

        return result

    def _extract_links(self, html: str, base_url: str, domain: dict) -> list[str]:
        soup = BeautifulSoup(html, "lxml")

        # Strip navigation elements before extracting links.
        # This prevents following global nav bar links that cause crawl explosion.
        for tag_name in _NAV_TAGS_FOR_LINK_EXTRACTION:
            for el in soup.find_all(tag_name):
                el.decompose()
        for el in soup.find_all(attrs={"role": "navigation"}):
            el.decompose()

        links = []
        base_domain = urlparse(domain["base_url"]).netloc

        # Path pattern filtering (crawl-time budget protection)
        # Global patterns from url_filters.yaml + domain-specific patterns merged
        allowed_patterns = domain.get("allowed_path_patterns", [])
        blocked_patterns = self.crawl_blocked_patterns + domain.get("blocked_path_patterns", [])

        for a in soup.find_all("a", href=True):
            full_url = urljoin(base_url, a["href"])
            parsed = urlparse(full_url)

            if parsed.netloc != base_domain:
                continue
            if parsed.scheme not in ("http", "https"):
                continue

            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in self.skip_extensions):
                # CGI scripts use .exe but return HTML content
                if not (path_lower.endswith(".exe") and "/cgi-bin/" in path_lower):
                    continue

            # Blocked patterns: reject known-bad paths before checking allow list
            if blocked_patterns:
                if any(fnmatch.fnmatch(path_lower, p.lower()) for p in blocked_patterns):
                    continue

            # Allowed patterns: when set, only follow links matching at least one
            if allowed_patterns:
                if not any(fnmatch.fnmatch(path_lower, p.lower()) for p in allowed_patterns):
                    continue

            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            links.append(normalized)

        return list(set(links))
