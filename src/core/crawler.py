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
import logging
import re
import warnings
from datetime import datetime
from typing import Optional, Callable, Awaitable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .models import CrawlResult, PageStatus

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
logger = logging.getLogger(__name__)

_DEFAULT_SKIP_EXTENSIONS = [
    ".pdf", ".doc", ".docx", ".zip", ".jpg", ".jpeg", ".png", ".gif",
    ".svg", ".css", ".js", ".json", ".xml", ".mp3", ".mp4", ".ico",
]

_NAV_TAGS_FOR_LINK_EXTRACTION = ["nav", "header", "footer"]

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
                "Install with: pip install 'playwright>=1.40' && playwright install chromium"
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
        queue: list[tuple[str, int]] = [
            (urljoin(base_url, p), 0) for p in start_paths
        ]

        client = await self._ensure_client() if not requires_playwright else None

        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)

            if url in self._visited:
                continue
            self._visited.add(url)

            # Pre-fetch URL filtering
            if self._should_skip_url(url):
                continue

            if requires_playwright:
                result = await self._fetch_playwright(url)
            else:
                result = await self._fetch_with_retry(client, url)
            result.domain_id = domain_id
            results.append(result)

            if self.on_page_fetched:
                await self.on_page_fetched(result)

            if result.is_success and depth < max_depth:
                links = self._extract_links(
                    result.content, url, base_url,
                    allowed_path_patterns, all_blocked,
                )
                for link in links:
                    if link not in self._visited:
                        queue.append((link, depth + 1))

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

                return CrawlResult(
                    url=url,
                    status=PageStatus.SUCCESS,
                    content=response.text,
                    content_type=response.headers.get("content-type", ""),
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

    def _extract_links(
        self,
        html: str,
        current_url: str,
        base_url: str,
        allowed_patterns: Optional[list[str]] = None,
        blocked_patterns: Optional[list[str]] = None,
    ) -> list[str]:
        """Extract same-domain links from HTML, removing nav elements first."""
        soup = BeautifulSoup(html, "lxml")

        for tag_name in _NAV_TAGS_FOR_LINK_EXTRACTION:
            for el in soup.find_all(tag_name):
                el.decompose()
        for el in soup.find_all(attrs={"role": "navigation"}):
            el.decompose()

        base_domain = urlparse(base_url).netloc
        links = []

        for a in soup.find_all("a", href=True):
            full_url = urljoin(current_url, a["href"])
            parsed = urlparse(full_url)

            if parsed.netloc != base_domain:
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
