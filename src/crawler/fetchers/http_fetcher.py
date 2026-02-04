"""HTTP fetcher using httpx."""

import asyncio
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ...config.settings import CrawlSettings
from ...models.crawl import CrawlResult, PageStatus


_DENIAL_PATTERNS = [
    ("cloudflare", "Cloudflare bot protection"),
    ("akamaighost", "Akamai WAF"),
    ("access denied", "Access Denied"),
    ("403 forbidden", "Forbidden"),
    ("bot detection", "bot detection"),
    ("automated access", "automated access blocked"),
    ("please verify", "verification required"),
    ("rate limit", "rate limited"),
    ("ip address", "IP-based block"),
    ("sign in to continue", "sign-in required"),
    ("login required", "login required"),
]


def _diagnose_response(response) -> str:
    """Build a diagnostic reason string from an error HTTP response."""
    code = response.status_code
    server = (response.headers.get("server", "") or "").lower()
    body = response.text[:2000].lower() if response.text else ""

    # Check Server header
    if "cloudflare" in server:
        return f"HTTP {code} -- Cloudflare bot protection"
    if "akamaighost" in server:
        return f"HTTP {code} -- Akamai WAF"

    # Check body for known patterns
    for pattern, label in _DENIAL_PATTERNS:
        if pattern in body:
            return f"HTTP {code} -- {label}"

    return f"HTTP {code}"


def diagnose_denial_from_text(status_code: int, body: str, headers: dict) -> str:
    """Build a diagnostic reason from raw text and headers (for Playwright)."""
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


class HttpFetcher:
    def __init__(self, settings: CrawlSettings):
        self.settings = settings
        self.client: Optional[httpx.AsyncClient] = None
        self._last_request: dict[str, float] = {}

    async def initialize(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            follow_redirects=True,
            max_redirects=5,
            headers={"User-Agent": self.settings.user_agent},
        )

    async def _rate_limit(self, domain: str) -> None:
        now = asyncio.get_event_loop().time()
        if domain in self._last_request:
            elapsed = now - self._last_request[domain]
            if elapsed < self.settings.delay_seconds:
                await asyncio.sleep(self.settings.delay_seconds - elapsed)
        self._last_request[domain] = asyncio.get_event_loop().time()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    async def fetch(
        self,
        url: str,
        extra_headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> CrawlResult:
        if not self.client:
            await self.initialize()

        domain = urlparse(url).netloc
        await self._rate_limit(domain)
        start = datetime.utcnow()

        try:
            kwargs: dict = {}
            if extra_headers:
                kwargs["headers"] = extra_headers
            if cookies:
                kwargs["cookies"] = cookies
            response = await self.client.get(url, **kwargs)
            elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)

            status_map = {
                403: PageStatus.ACCESS_DENIED,
                404: PageStatus.NOT_FOUND,
                429: PageStatus.RATE_LIMITED,
            }

            if response.status_code in status_map:
                reason = _diagnose_response(response)
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
            return CrawlResult(
                url=url,
                status=PageStatus.TIMEOUT,
                error_message=f"Timeout after {self.settings.timeout_seconds}s",
            )
        except Exception as e:
            return CrawlResult(
                url=url,
                status=PageStatus.UNKNOWN_ERROR,
                error_message=str(e),
            )

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
