"""Playwright fetcher for JS pages."""

import asyncio
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext

from ...config.settings import CrawlSettings
from ...models.crawl import CrawlResult, PageStatus
from .http_fetcher import diagnose_denial_from_text


class PlaywrightFetcher:
    def __init__(self, settings: CrawlSettings):
        self.settings = settings
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._last_request: dict[str, float] = {}

    async def initialize(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=self.settings.user_agent
        )

    async def _rate_limit(self, domain: str) -> None:
        now = asyncio.get_event_loop().time()
        if domain in self._last_request:
            elapsed = now - self._last_request[domain]
            if elapsed < self.settings.delay_seconds:
                await asyncio.sleep(self.settings.delay_seconds - elapsed)
        self._last_request[domain] = asyncio.get_event_loop().time()

    async def fetch(self, url: str) -> CrawlResult:
        if not self._context:
            await self.initialize()

        domain = urlparse(url).netloc
        await self._rate_limit(domain)

        start = datetime.utcnow()
        page = await self._context.new_page()

        try:
            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=self.settings.timeout_seconds * 1000,
            )
            elapsed = int((datetime.utcnow() - start).total_seconds() * 1000)

            if response is None:
                return CrawlResult(
                    url=url,
                    status=PageStatus.UNKNOWN_ERROR,
                    error_message="No response",
                    used_playwright=True,
                )

            if response.status >= 400:
                pw_status_map = {
                    403: PageStatus.ACCESS_DENIED,
                    404: PageStatus.NOT_FOUND,
                    429: PageStatus.RATE_LIMITED,
                }
                status = pw_status_map.get(response.status, PageStatus.UNKNOWN_ERROR)
                body = await page.content()
                headers = {k: v for k, v in response.headers.items()}
                reason = diagnose_denial_from_text(response.status, body, headers)
                return CrawlResult(
                    url=url,
                    status=status,
                    response_time_ms=elapsed,
                    error_message=reason,
                    used_playwright=True,
                )

            content = await page.content()
            title = await page.title()

            return CrawlResult(
                url=url,
                status=PageStatus.SUCCESS,
                content=content,
                content_type="text/html",
                title=title,
                response_time_ms=elapsed,
                content_length=len(content),
                used_playwright=True,
            )

        except Exception as e:
            if "Timeout" in type(e).__name__:
                return CrawlResult(
                    url=url,
                    status=PageStatus.TIMEOUT,
                    error_message=f"Timeout after {self.settings.timeout_seconds}s",
                    used_playwright=True,
                )
            return CrawlResult(
                url=url,
                status=PageStatus.UNKNOWN_ERROR,
                error_message=str(e),
                used_playwright=True,
            )
        finally:
            await page.close()

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
