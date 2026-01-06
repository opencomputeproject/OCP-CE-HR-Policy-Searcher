"""HTTP fetcher using httpx."""

import asyncio
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ...config.settings import CrawlSettings
from ...models.crawl import CrawlResult, PageStatus


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
    async def fetch(self, url: str) -> CrawlResult:
        if not self.client:
            await self.initialize()

        domain = urlparse(url).netloc
        await self._rate_limit(domain)
        start = datetime.utcnow()

        try:
            response = await self.client.get(url)
            elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)

            status_map = {
                403: PageStatus.ACCESS_DENIED,
                404: PageStatus.NOT_FOUND,
                429: PageStatus.RATE_LIMITED,
            }

            if response.status_code in status_map:
                return CrawlResult(
                    url=url,
                    status=status_map[response.status_code],
                    response_time_ms=elapsed,
                    error_message=f"HTTP {response.status_code}",
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
