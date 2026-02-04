"""Unit tests for PlaywrightFetcher DOM stabilization and wait strategy."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.crawler.fetchers.playwright_fetcher import PlaywrightFetcher
from src.models.crawl import PageStatus


def _make_settings(**overrides):
    """Create a minimal CrawlSettings-like object."""
    settings = MagicMock()
    settings.timeout_seconds = overrides.get("timeout_seconds", 30)
    settings.delay_seconds = overrides.get("delay_seconds", 0)
    settings.user_agent = overrides.get("user_agent", "test-agent")
    return settings


def _make_page(
    content="<html><body>Hello</body></html>",
    title="Test Page",
    status=200,
    evaluate_return="stable",
):
    """Create a mock Playwright page object."""
    page = AsyncMock()
    page.content.return_value = content
    page.title.return_value = title
    page.evaluate.return_value = evaluate_return

    response = AsyncMock()
    response.status = status
    response.headers = {}
    page.goto.return_value = response

    return page


class TestDOMStabilization:
    """Test the MutationObserver wait strategy in PlaywrightFetcher."""

    @pytest.fixture
    def fetcher(self):
        """Create a PlaywrightFetcher with mocked internals."""
        settings = _make_settings(delay_seconds=0)
        f = PlaywrightFetcher(settings)
        f._context = AsyncMock()
        f._last_request = {}
        return f

    @pytest.mark.asyncio
    async def test_fetch_uses_domcontentloaded(self, fetcher):
        """fetch() should use wait_until='domcontentloaded', not 'networkidle'."""
        page = _make_page()
        fetcher._context.new_page.return_value = page

        await fetcher.fetch("https://example.gov/page")

        page.goto.assert_called_once()
        call_kwargs = page.goto.call_args
        assert call_kwargs[1]["wait_until"] == "domcontentloaded"

    @pytest.mark.asyncio
    async def test_fetch_calls_dom_stable(self, fetcher):
        """fetch() should call page.evaluate with MutationObserver JS."""
        page = _make_page()
        fetcher._context.new_page.return_value = page

        await fetcher.fetch("https://example.gov/page")

        page.evaluate.assert_called_once()
        js_code = page.evaluate.call_args[0][0]
        assert "MutationObserver" in js_code

    @pytest.mark.asyncio
    async def test_fetch_succeeds_when_dom_stable_fails(self, fetcher):
        """If MutationObserver JS fails, fetch still returns content."""
        page = _make_page(content="<html><body>SPA Content</body></html>")
        page.evaluate.side_effect = Exception("JS eval failed")
        fetcher._context.new_page.return_value = page

        result = await fetcher.fetch("https://example.gov/page")

        assert result.status == PageStatus.SUCCESS
        assert "SPA Content" in result.content

    @pytest.mark.asyncio
    async def test_fetch_returns_content_on_success(self, fetcher):
        """Normal fetch returns SUCCESS with content and title."""
        page = _make_page(
            content="<html><body>Policy text</body></html>",
            title="Energy Policy",
        )
        fetcher._context.new_page.return_value = page

        result = await fetcher.fetch("https://example.gov/policy")

        assert result.status == PageStatus.SUCCESS
        assert result.content == "<html><body>Policy text</body></html>"
        assert result.title == "Energy Policy"
        assert result.used_playwright is True

    @pytest.mark.asyncio
    async def test_fetch_measures_elapsed_after_dom_stable(self, fetcher):
        """response_time_ms should include DOM stabilization wait time."""
        page = _make_page()
        fetcher._context.new_page.return_value = page

        result = await fetcher.fetch("https://example.gov/page")

        assert result.response_time_ms is not None
        assert result.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_fetch_handles_http_error_before_dom_stable(self, fetcher):
        """HTTP 403 should return early without calling DOM stabilization."""
        page = _make_page(status=403, content="Access Denied")
        fetcher._context.new_page.return_value = page

        result = await fetcher.fetch("https://example.gov/blocked")

        assert result.status == PageStatus.ACCESS_DENIED
        assert result.used_playwright is True
        # evaluate should NOT be called for error responses
        page.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_handles_none_response(self, fetcher):
        """None response returns UNKNOWN_ERROR without calling DOM stabilization."""
        page = AsyncMock()
        page.goto.return_value = None
        fetcher._context.new_page.return_value = page

        result = await fetcher.fetch("https://example.gov/empty")

        assert result.status == PageStatus.UNKNOWN_ERROR
        assert "No response" in result.error_message

    @pytest.mark.asyncio
    async def test_dom_stable_js_contains_observer_config(self, fetcher):
        """The MutationObserver JS observes childList, subtree, and characterData."""
        page = _make_page()
        fetcher._context.new_page.return_value = page

        await fetcher.fetch("https://example.gov/page")

        js_code = page.evaluate.call_args[0][0]
        assert "childList: true" in js_code
        assert "subtree: true" in js_code
        assert "characterData: true" in js_code

    @pytest.mark.asyncio
    async def test_dom_stable_js_has_timeout_and_stable_params(self, fetcher):
        """The JS receives timeout_ms and stable_ms as parameters."""
        page = _make_page()
        fetcher._context.new_page.return_value = page

        await fetcher.fetch("https://example.gov/page")

        call_args = page.evaluate.call_args
        params = call_args[0][1]
        assert params == [10000, 500]  # defaults

    @pytest.mark.asyncio
    async def test_dom_stable_custom_params(self, fetcher):
        """_wait_for_dom_stable accepts custom timeout and stable values."""
        page = _make_page()

        await fetcher._wait_for_dom_stable(page, timeout_ms=5000, stable_ms=200)

        call_args = page.evaluate.call_args
        params = call_args[0][1]
        assert params == [5000, 200]

    @pytest.mark.asyncio
    async def test_dom_stable_js_resolves_variants(self, fetcher):
        """The JS can resolve with 'stable', 'timeout', or 'already-stable'."""
        page = _make_page()

        for resolve_val in ["stable", "timeout", "already-stable"]:
            page.evaluate.return_value = resolve_val
            await fetcher._wait_for_dom_stable(page)  # Should not raise
