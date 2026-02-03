"""Unit tests for AsyncCrawler._extract_links with extension filtering."""

import pytest

from src.crawler.async_crawler import AsyncCrawler, _DEFAULT_SKIP_EXTENSIONS


def _make_html(links: list[str]) -> str:
    """Build a minimal HTML page with the given hrefs."""
    anchors = "\n".join(f'<a href="{href}">link</a>' for href in links)
    return f"<html><body>{anchors}</body></html>"


def _make_crawler(**kwargs):
    """Create a minimal AsyncCrawler for testing _extract_links."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.max_depth = 2
    settings.max_pages_per_domain = 50
    settings.timeout_seconds = 30
    settings.delay_seconds = 1
    settings.user_agent = "test"
    settings.force_playwright = False

    return AsyncCrawler(
        settings=settings,
        domains=[],
        keyword_matcher=MagicMock(),
        logger=MagicMock(),
        **kwargs,
    )


class TestLinkExtractorPathOnly:
    """Tests that extension check uses path, not full URL."""

    def test_query_string_not_checked_for_extension(self):
        """URL ending with .exe in query should not be filtered."""
        crawler = _make_crawler(skip_extensions=[".exe"])
        domain = {"base_url": "https://lis.virginia.gov"}
        html = _make_html([
            "/cgi-bin/legp604.exe?ses=251&typ=bil&val=hb116",
        ])

        links = crawler._extract_links(
            html, "https://lis.virginia.gov/", domain
        )
        assert len(links) == 1
        assert "legp604.exe" in links[0]

    def test_pdf_in_query_not_filtered(self):
        """URL with .pdf only in query string should pass."""
        crawler = _make_crawler(skip_extensions=[".pdf"])
        domain = {"base_url": "https://example.gov"}
        html = _make_html([
            "/search?file=report.pdf",
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 1

    def test_pdf_in_path_still_filtered(self):
        """URL with .pdf in path should still be filtered."""
        crawler = _make_crawler(skip_extensions=[".pdf"])
        domain = {"base_url": "https://example.gov"}
        html = _make_html([
            "/documents/report.pdf",
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 0


class TestLinkExtractorCgiBin:
    """Tests for CGI-bin .exe exception in link extractor."""

    def test_cgi_bin_exe_not_filtered(self):
        """CGI-bin .exe links should not be filtered."""
        crawler = _make_crawler(skip_extensions=[".exe", ".pdf"])
        domain = {"base_url": "https://lis.virginia.gov"}
        html = _make_html([
            "/cgi-bin/legp604.exe?ses=251&typ=bil&val=hb116",
            "/cgi-bin/legp604.exe?ses=251&typ=bil&val=hb323",
        ])

        links = crawler._extract_links(
            html, "https://lis.virginia.gov/", domain
        )
        assert len(links) == 2

    def test_non_cgi_exe_still_filtered(self):
        """Non-CGI .exe links should still be filtered."""
        crawler = _make_crawler(skip_extensions=[".exe"])
        domain = {"base_url": "https://example.gov"}
        html = _make_html([
            "/downloads/installer.exe",
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 0


class TestLinkExtractorConfigExtensions:
    """Tests that link extractor uses configured extensions."""

    def test_default_extensions(self):
        """Crawler without skip_extensions uses defaults."""
        crawler = _make_crawler()
        assert crawler.skip_extensions == [
            ext.lower() for ext in _DEFAULT_SKIP_EXTENSIONS
        ]

    def test_custom_extensions(self):
        """Crawler with custom skip_extensions uses them."""
        crawler = _make_crawler(skip_extensions=[".pdf", ".xml", ".csv"])
        assert crawler.skip_extensions == [".pdf", ".xml", ".csv"]

    def test_custom_extensions_filter_correctly(self):
        """Custom extensions are used for link filtering."""
        crawler = _make_crawler(skip_extensions=[".xml"])
        domain = {"base_url": "https://example.gov"}
        html = _make_html([
            "/data/feed.xml",
            "/policy/energy",
            "/documents/report.pdf",  # not in skip list
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        # .xml filtered, .pdf passes (not in custom list), /policy passes
        assert len(links) == 2
        paths = [l.split("example.gov")[1] for l in links]
        assert "/documents/report.pdf" in paths
        assert "/policy/energy" in paths

    def test_extensions_case_insensitive(self):
        """Extensions are lowered for case-insensitive matching."""
        crawler = _make_crawler(skip_extensions=[".PDF", ".DOC"])
        assert crawler.skip_extensions == [".pdf", ".doc"]
