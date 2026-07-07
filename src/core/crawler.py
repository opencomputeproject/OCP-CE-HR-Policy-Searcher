"""Async web crawler with BFS traversal, rate limiting, and link extraction.

Supports two fetching backends:
- **httpx** (default) — fast, lightweight HTTP client for static pages.
- **Playwright** — headless Chromium for JavaScript-rendered SPAs.

Set ``requires_playwright=True`` in :meth:`crawl_domain` (or in the domain
YAML config) to enable Playwright rendering.  The browser is launched once
per crawl and reused for every page in that domain.
"""

import asyncio
import fnmatch
import heapq
import logging
import re
import warnings
from datetime import datetime
from typing import Optional, Callable, Awaitable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .models import CrawlResult, PageStatus
from .pdf import PDFExtractionError, extract_pdf_text, looks_like_pdf

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
logger = logging.getLogger(__name__)

# .pdf is deliberately NOT skipped: statutes and regulations are
# overwhelmingly published as PDFs and go through text extraction.
_DEFAULT_SKIP_EXTENSIONS = [
    ".doc", ".docx", ".zip", ".jpg", ".jpeg", ".png", ".gif",
    ".svg", ".css", ".js", ".json", ".xml", ".mp3", ".mp4", ".ico",
]

# URL substrings that suggest a page holds or indexes legislation.
# Used to prioritize the crawl frontier so the page budget is spent on
# likely law pages instead of whatever FIFO order surfaced first.
_PRIORITY_URL_TERMS = [
    "law", "legislation", "statute", "regulation", "directive", "act",
    "bill", "decree", "ordinance", "code",
    "energy", "energi", "heat", "warme", "wärme", "varme", "abwarme",
    "abwärme", "chaleur", "calor", "climate", "klima", "efficien",
    "gesetz", "recht", "loi", "ley", "lag", "lov", "laki", "wet",
]

# Patterns indicating access denial or bot protection
_DENIAL_PATTERNS = [
    ("cloudflare", "Cloudflare bot protection"),
    ("akamaighost", "Akamai WAF"),
    ("access denied", "Access Denied"),
    ("403 forbidden", "Forbidden"),
    ("bot detection", "bot detection"),
    ("rate limit", "rate limited"),
    ("sign in to continue", "sign-in required"),
    ("login required", "login required"),
]


def _diagnose_response(status_code: int, headers: dict, body: str) -> str:
    """Build diagnostic reason from HTTP response."""
    server = (headers.get("server", "") or "").lower()
    body_lower = body[:2000].lower() if body else ""

    if "cloudflare" in server:
        return f"HTTP {status_code} -- Cloudflare bot protection"
    if "akamaighost" in server:
        return f"HTTP {status_code} -- Akamai WAF"

    for pattern, label in _DENIAL_PATTERNS:
        if pattern in body_lower:
            return f"HTTP {status_code} -- {label}"

    return f"HTTP {status_code}"


class AsyncCrawler:
    """Async BFS web crawler for a single domain."""

    def __init__(
        self,
        max_depth: int = 3,
        max_pages: int = 200,
        delay_seconds: float = 3.0,
        timeout_seconds: int = 30,
        user_agent: str = "OCP-PolicyHub/1.0",
        max_retries: int = 3,
        skip_extensions: Optional[list[str]] = None,
        crawl_blocked_patterns: Optional[list[str]] = None,
        url_skip_paths: Optional[list[str]] = None,
        url_skip_patterns: Optional[list[re.Pattern]] = None,
        on_page_fetched: Optional[Callable[[CrawlResult], Awaitable[None]]] = None,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.skip_extensions = [
            ext.lower() for ext in (skip_extensions or _DEFAULT_SKIP_EXTENSIONS)
        ]
        self.crawl_blocked_patterns = crawl_blocked_patterns or []
        self.url_skip_paths = [p.lower() for p in (url_skip_paths or [])]
        self.url_skip_patterns = url_skip_patterns or []
        self.on_page_fetched = on_page_fetched

        self._client: Optional[httpx.AsyncClient] = None
        self._playwright = None          # Playwright context manager
        self._pw_browser = None           # Launched Chromium instance
        self._pw_fallback_broken = False  # stop retrying if Playwright is unavailable
        self._last_request_time: float = 0
        self._visited: set[str] = set()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
                max_redirects=5,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    async def _ensure_playwright(self):  # -> playwright Browser
        """Launch headless Chromium (once) for JavaScript-rendered pages."""
        if self._pw_browser:
            return self._pw_browser
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is required for JavaScript-rendered sites. "
                "Install with: pip install '.[browser]' && playwright install chromium"
            )
        self._playwright = await async_playwright().start()
        self._pw_browser = await self._playwright.chromium.launch(headless=True)
        logger.info("Playwright Chromium launched for JS rendering")
        return self._pw_browser

    async def _fetch_playwright(self, url: str) -> CrawlResult:
        """Fetch a URL using Playwright headless Chromium (for JavaScript SPAs)."""
        await self._rate_limit()
        start = datetime.utcnow()
        browser = await self._ensure_playwright()

        page = None
        try:
            page = await browser.new_page(user_agent=self.user_agent)
            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=self.timeout_seconds * 1000,
            )

            if response is None:
                return CrawlResult(
                    url=url,
                    status=PageStatus.UNKNOWN_ERROR,
                    error_message="Playwright: no response from page",
                    response_time_ms=int((datetime.utcnow() - start).total_seconds() * 1000),
                )

            status_code = response.status
            if status_code in (403, 404, 429):
                status_map = {
                    403: PageStatus.ACCESS_DENIED,
                    404: PageStatus.NOT_FOUND,
                    429: PageStatus.RATE_LIMITED,
                }
                return CrawlResult(
                    url=url,
                    status=status_map[status_code],
                    response_time_ms=int((datetime.utcnow() - start).total_seconds() * 1000),
                    error_message=f"HTTP {status_code} (Playwright)",
                )
            elif status_code >= 400:
                return CrawlResult(
                    url=url,
                    status=PageStatus.UNKNOWN_ERROR,
                    response_time_ms=int((datetime.utcnow() - start).total_seconds() * 1000),
                    error_message=f"HTTP {status_code} (Playwright)",
                )

            content = await page.content()
            elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)

            logger.debug("Playwright fetched %s (%d chars, %dms)", url, len(content), elapsed)

            return CrawlResult(
                url=url,
                status=PageStatus.SUCCESS,
                content=content,
                content_type="text/html",
                response_time_ms=elapsed,
                content_length=len(content),
                used_playwright=True,
            )

        except Exception as e:
            error_msg = str(e)
            is_timeout = "timeout" in error_msg.lower()
            return CrawlResult(
                url=url,
                status=PageStatus.TIMEOUT if is_timeout else PageStatus.UNKNOWN_ERROR,
                error_message=f"Playwright: {error_msg}",
                response_time_ms=int((datetime.utcnow() - start).total_seconds() * 1000),
            )
        finally:
            if page:
                await page.close()

    async def _rate_limit(self) -> None:
        """Enforce per-domain delay between requests."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self.delay_seconds:
            await asyncio.sleep(self.delay_seconds - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def crawl_domain(
        self,
        base_url: str,
        start_paths: list[str],
        domain_id: str = "",
        allowed_path_patterns: Optional[list[str]] = None,
        blocked_path_patterns: Optional[list[str]] = None,
        max_depth_override: Optional[int] = None,
        max_pages_override: Optional[int] = None,
        requires_playwright: bool = False,
    ) -> list[CrawlResult]:
        """BFS crawl a domain starting from given paths."""
        max_depth = max_depth_override or self.max_depth
        max_pages = max_pages_override or self.max_pages
        all_blocked = self.crawl_blocked_patterns + (blocked_path_patterns or [])

        if requires_playwright:
            logger.info("Domain %s requires Playwright (JavaScript rendering)", domain_id)

        self._visited.clear()
        results: list[CrawlResult] = []
        # Priority frontier: law-like URLs first so the page budget is not
        # exhausted on nav noise before reaching legislation. seq keeps
        # FIFO order among equal priorities (still BFS-ish).
        seq = 0
        queue: list[tuple[int, int, str, int]] = []
        for p in start_paths:
            url = urljoin(base_url, p)
            heapq.heappush(queue, (-self._url_priority(url), seq, url, 0))
            seq += 1

        client = await self._ensure_client() if not requires_playwright else None

        # Sitemap seeding: enumerate deep document URLs the BFS budget
        # would never reach. Failure is silent — many sites have none.
        # Sitemap URLs obey the same path filters as extracted links.
        if client is None:
            client = await self._ensure_client()
        base_netloc = urlparse(base_url).netloc
        for sitemap_url in await self._sitemap_urls(client, base_url):
            parsed = urlparse(sitemap_url)
            if not self._same_site(parsed.netloc, base_netloc):
                continue
            if sitemap_url in self._visited:
                continue
            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in self.skip_extensions):
                continue
            if all_blocked and any(
                fnmatch.fnmatch(path_lower, p.lower()) for p in all_blocked
            ):
                continue
            if allowed_path_patterns and not any(
                fnmatch.fnmatch(path_lower, p.lower())
                for p in allowed_path_patterns
            ):
                continue
            heapq.heappush(
                queue, (-self._url_priority(sitemap_url), seq, sitemap_url, 1),
            )
            seq += 1

        while queue and len(results) < max_pages:
            _, _, url, depth = heapq.heappop(queue)

            if url in self._visited:
                continue
            self._visited.add(url)

            # Pre-fetch URL filtering
            if self._should_skip_url(url):
                continue

            # PDFs are static files: always fetch over httpx, even on
            # Playwright domains (a browser tab cannot extract PDF text).
            is_pdf_url = urlparse(url).path.lower().endswith(".pdf")
            if requires_playwright and not is_pdf_url:
                result = await self._fetch_playwright(url)
            else:
                if client is None:
                    client = await self._ensure_client()
                result = await self._fetch_with_retry(client, url)

                # JS-shell fallback: a "successful" HTML page with almost
                # no visible text is usually an unflagged SPA. Retry once
                # with Playwright rather than silently scoring zero words.
                if (
                    not requires_playwright
                    and not self._pw_fallback_broken
                    and result.is_success
                    and result.content
                    and "html" in (result.content_type or "")
                    and self._visible_text_len(result.content) < 200
                ):
                    try:
                        rendered = await self._fetch_playwright(url)
                        if (
                            rendered.is_success
                            and self._visible_text_len(rendered.content or "")
                            > self._visible_text_len(result.content)
                        ):
                            logger.info(
                                "Playwright fallback recovered content for %s",
                                url,
                            )
                            rendered.used_playwright = True
                            result = rendered
                    except Exception as e:
                        # Playwright unavailable (not installed / no
                        # browser) — stop trying for this crawl.
                        logger.warning(
                            "Playwright fallback unavailable (%s); "
                            "disabled for the rest of this crawl", e,
                        )
                        self._pw_fallback_broken = True
            result.domain_id = domain_id
            results.append(result)

            if self.on_page_fetched:
                await self.on_page_fetched(result)

            if (
                result.is_success
                and depth < max_depth
                and result.content_type != "application/pdf"
            ):
                links = self._extract_links(
                    result.content, url, base_url,
                    allowed_path_patterns, all_blocked,
                )
                for link in links:
                    if link not in self._visited:
                        heapq.heappush(
                            queue,
                            (-self._url_priority(link), seq, link, depth + 1),
                        )
                        seq += 1

        return results

    def _should_skip_url(self, url: str) -> bool:
        """Check if URL should be skipped based on path filters."""
        parsed = urlparse(url)
        path_lower = parsed.path.lower()

        for skip_path in self.url_skip_paths:
            if skip_path in path_lower:
                return True

        for pattern in self.url_skip_patterns:
            if pattern.search(parsed.path):
                return True

        return False

    async def _fetch_with_retry(
        self, client: httpx.AsyncClient, url: str,
    ) -> CrawlResult:
        """Fetch a URL with retries and rate limiting."""
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            await self._rate_limit()
            start = datetime.utcnow()

            try:
                response = await client.get(url)
                elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)

                status_map = {
                    403: PageStatus.ACCESS_DENIED,
                    404: PageStatus.NOT_FOUND,
                    429: PageStatus.RATE_LIMITED,
                }

                if response.status_code in status_map:
                    reason = _diagnose_response(
                        response.status_code,
                        dict(response.headers),
                        response.text[:2000] if response.text else "",
                    )
                    return CrawlResult(
                        url=url,
                        status=status_map[response.status_code],
                        response_time_ms=elapsed,
                        error_message=reason,
                    )
                elif response.status_code >= 400:
                    return CrawlResult(
                        url=url,
                        status=PageStatus.UNKNOWN_ERROR,
                        response_time_ms=elapsed,
                        error_message=f"HTTP {response.status_code}",
                    )

                content_type = response.headers.get("content-type", "")
                if looks_like_pdf(url, content_type):
                    try:
                        text = extract_pdf_text(response.content)
                    except PDFExtractionError as e:
                        return CrawlResult(
                            url=url,
                            status=PageStatus.UNKNOWN_ERROR,
                            response_time_ms=elapsed,
                            error_message=f"PDF extraction failed: {e}",
                        )
                    return CrawlResult(
                        url=url,
                        status=PageStatus.SUCCESS,
                        content=text,
                        content_type="application/pdf",
                        response_time_ms=elapsed,
                        content_length=len(text),
                    )

                return CrawlResult(
                    url=url,
                    status=PageStatus.SUCCESS,
                    content=response.text,
                    content_type=content_type,
                    response_time_ms=elapsed,
                    content_length=len(response.text),
                )

            except httpx.TimeoutException:
                last_error = f"Timeout after {self.timeout_seconds}s"
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)

        return CrawlResult(
            url=url,
            status=PageStatus.TIMEOUT if "Timeout" in (last_error or "") else PageStatus.UNKNOWN_ERROR,
            error_message=last_error or "Unknown error",
        )

    MAX_SITEMAP_URLS = 200
    MAX_NESTED_SITEMAPS = 5
    _SITEMAP_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)

    @staticmethod
    def _visible_text_len(html: str) -> int:
        """Rough visible-text length, cheap enough to run per page."""
        if not html:
            return 0
        stripped = re.sub(
            r"<(script|style)[^>]*>.*?</\1>", " ", html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        stripped = re.sub(r"<[^>]+>", " ", stripped)
        return len(" ".join(stripped.split()))

    async def _sitemap_urls(self, client, base_url: str) -> list[str]:
        """Enumerate URLs from sitemap.xml (one level of nesting).

        Sitemaps list deep document URLs directly, countering the page
        budget and depth limits of BFS crawling. Regex extraction of
        <loc> avoids parsing untrusted XML.
        """
        seen: list[str] = []
        try:
            queue = [urljoin(base_url, "/sitemap.xml")]
            nested_budget = self.MAX_NESTED_SITEMAPS
            while queue and len(seen) < self.MAX_SITEMAP_URLS:
                sitemap_url = queue.pop(0)
                result = await self._fetch_with_retry(client, sitemap_url)
                if not result.is_success or not result.content:
                    continue
                for loc in self._SITEMAP_LOC_RE.findall(result.content):
                    loc = loc.strip()
                    if loc.lower().endswith(".xml"):
                        if nested_budget > 0:
                            queue.append(loc)
                            nested_budget -= 1
                        continue
                    seen.append(loc)
                    if len(seen) >= self.MAX_SITEMAP_URLS:
                        break
        except Exception as e:
            logger.debug("Sitemap enumeration failed for %s: %s", base_url, e)
        if seen:
            logger.info("Sitemap seeded %d URLs for %s", len(seen), base_url)
        return seen

    @staticmethod
    def _same_site(link_netloc: str, base_netloc: str) -> bool:
        """Same host, www/apex variants, or a subdomain of the seed host.

        Gov sites routinely place document stores and legislation viewers
        on sibling subdomains; an exact-netloc match dropped those links.
        """
        link_host = link_netloc.lower().removeprefix("www.")
        base_host = base_netloc.lower().removeprefix("www.")
        return link_host == base_host or link_host.endswith("." + base_host)

    @staticmethod
    def _url_priority(url: str) -> int:
        """Score a URL by how likely it is to hold or index legislation."""
        lowered = url.lower()
        score = sum(1 for term in _PRIORITY_URL_TERMS if term in lowered)
        if lowered.endswith(".pdf"):
            score += 2  # statutes are usually the PDFs
        return score

    def _extract_links(
        self,
        html: str,
        current_url: str,
        base_url: str,
        allowed_patterns: Optional[list[str]] = None,
        blocked_patterns: Optional[list[str]] = None,
    ) -> list[str]:
        """Extract same-site links from HTML.

        Nav/aside elements are deliberately KEPT: on legislation sites the
        statute's table of contents (links into each section of a law) is
        usually rendered as a navigation element.
        """
        soup = BeautifulSoup(html, "lxml")

        base_domain = urlparse(base_url).netloc
        links = []

        for a in soup.find_all("a", href=True):
            full_url = urljoin(current_url, a["href"])
            parsed = urlparse(full_url)

            if not self._same_site(parsed.netloc, base_domain):
                continue
            if parsed.scheme not in ("http", "https"):
                continue

            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in self.skip_extensions):
                continue

            if blocked_patterns:
                if any(fnmatch.fnmatch(path_lower, p.lower()) for p in blocked_patterns):
                    continue

            if allowed_patterns:
                if not any(fnmatch.fnmatch(path_lower, p.lower()) for p in allowed_patterns):
                    continue

            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            links.append(normalized)

        return list(set(links))

    async def fetch_url(self, url: str) -> CrawlResult:
        """Fetch a single URL outside a crawl (e.g. a referenced policy link).

        Respects the crawler's rate limiting and retry logic; PDFs go
        through text extraction like any crawled page.
        """
        client = await self._ensure_client()
        return await self._fetch_with_retry(client, url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pw_browser:
            await self._pw_browser.close()
            self._pw_browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
