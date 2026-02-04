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


class TestPathPatternFiltering:
    """Test allowed_path_patterns and blocked_path_patterns in _extract_links."""

    def test_blocked_pattern_filters_links(self):
        """Links matching blocked_path_patterns are excluded."""
        crawler = _make_crawler()
        domain = {
            "base_url": "https://lis.virginia.gov",
            "blocked_path_patterns": ["/developers/*", "/login"],
        }
        html = _make_html([
            "/developers/api-reference",
            "/developers/getting-started",
            "/login",
            "/bill-details/20261/HB323",
        ])

        links = crawler._extract_links(
            html, "https://lis.virginia.gov/", domain
        )
        assert len(links) == 1
        assert "/bill-details/20261/HB323" in links[0]

    def test_allowed_pattern_only_allows_matching(self):
        """Only links matching allowed_path_patterns are included."""
        crawler = _make_crawler()
        domain = {
            "base_url": "https://lis.virginia.gov",
            "allowed_path_patterns": ["/bill-details/*", "/bill-text/*"],
        }
        html = _make_html([
            "/bill-details/20261/HB323",
            "/bill-text/20261/HB323",
            "/session-details/20261",
            "/developers/api",
            "/about",
        ])

        links = crawler._extract_links(
            html, "https://lis.virginia.gov/", domain
        )
        assert len(links) == 2
        paths = [l.split("lis.virginia.gov")[1] for l in links]
        assert "/bill-details/20261/HB323" in paths
        assert "/bill-text/20261/HB323" in paths

    def test_empty_patterns_allows_all(self):
        """No patterns set = all same-domain links allowed (current behavior)."""
        crawler = _make_crawler()
        domain = {"base_url": "https://example.gov"}
        html = _make_html([
            "/page-a",
            "/page-b",
            "/page-c",
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 3

    def test_empty_allowed_list_allows_all(self):
        """Explicit empty allowed_path_patterns = allow all (same as omitted)."""
        crawler = _make_crawler()
        domain = {
            "base_url": "https://example.gov",
            "allowed_path_patterns": [],
        }
        html = _make_html(["/page-a", "/page-b"])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 2

    def test_blocked_checked_before_allowed(self):
        """A link matching both blocked and allowed is blocked."""
        crawler = _make_crawler()
        domain = {
            "base_url": "https://example.gov",
            "allowed_path_patterns": ["/data/*"],
            "blocked_path_patterns": ["/data/private/*"],
        }
        html = _make_html([
            "/data/public/report",
            "/data/private/secret",
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 1
        assert "/data/public/report" in links[0]

    def test_patterns_case_insensitive(self):
        """Pattern matching is case-insensitive."""
        crawler = _make_crawler()
        domain = {
            "base_url": "https://example.gov",
            "blocked_path_patterns": ["/Developers/*"],
        }
        html = _make_html([
            "/developers/api",
            "/DEVELOPERS/docs",
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 0

    def test_wildcard_patterns_work(self):
        """Glob-style wildcards match correctly."""
        crawler = _make_crawler()
        domain = {
            "base_url": "https://example.gov",
            "allowed_path_patterns": ["/bills/*/text"],
        }
        html = _make_html([
            "/bills/HB323/text",
            "/bills/SB192/text",
            "/bills/HB323/sponsors",
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 2
        paths = [l.split("example.gov")[1] for l in links]
        assert "/bills/HB323/text" in paths
        assert "/bills/SB192/text" in paths

    def test_start_paths_bypass_patterns(self):
        """Start paths go to queue directly, never through _extract_links.

        This is an architectural property -- crawl_domain() adds start_paths
        to the queue at line 82 without calling _extract_links(). We verify
        that _extract_links would block such a path if it were a discovered
        link, confirming that the bypass matters.
        """
        crawler = _make_crawler()
        domain = {
            "base_url": "https://lis.virginia.gov",
            "allowed_path_patterns": ["/bill-details/*"],
        }
        # If /session-details/20261 were discovered as a link, it would be blocked
        html = _make_html(["/session-details/20261"])
        links = crawler._extract_links(
            html, "https://lis.virginia.gov/", domain
        )
        assert len(links) == 0
        # But as a start_path, it would be added directly to queue by crawl_domain()

    def test_blocked_only_no_allowed(self):
        """Blocked patterns work without allowed patterns set."""
        crawler = _make_crawler()
        domain = {
            "base_url": "https://example.gov",
            "blocked_path_patterns": ["/admin/*"],
        }
        html = _make_html([
            "/admin/settings",
            "/policies/energy",
            "/reports/2026",
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 2
        paths = [l.split("example.gov")[1] for l in links]
        assert "/policies/energy" in paths
        assert "/reports/2026" in paths

    def test_path_patterns_combined_with_extension_filter(self):
        """Path patterns and extension filtering work together."""
        crawler = _make_crawler(skip_extensions=[".pdf"])
        domain = {
            "base_url": "https://example.gov",
            "blocked_path_patterns": ["/admin/*"],
        }
        html = _make_html([
            "/admin/settings",       # blocked by pattern
            "/docs/report.pdf",      # blocked by extension
            "/policies/energy",      # passes both
        ])

        links = crawler._extract_links(
            html, "https://example.gov/", domain
        )
        assert len(links) == 1
        assert "/policies/energy" in links[0]
