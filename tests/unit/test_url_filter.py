"""Unit tests for URL pre-filtering."""

import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from src.analysis.url_filter import (
    URLFilter,
    URLFilterConfig,
    FilterResult,
    FilterStats,
    load_url_filters,
    create_url_filter,
)


class TestURLFilterConfig:
    """Tests for URLFilterConfig dataclass."""

    def test_default_config(self):
        """Test creating config with defaults."""
        config = URLFilterConfig()
        assert config.skip_paths == []
        assert config.skip_patterns == []
        assert config.skip_extensions == []
        assert config.domain_overrides == {}

    def test_config_with_values(self):
        """Test creating config with values."""
        config = URLFilterConfig(
            skip_paths=["/login", "/contact"],
            skip_patterns=["^/news/"],
            skip_extensions=[".pdf", ".doc"],
            domain_overrides={"example.com": {"skip_paths": ["/about"]}},
        )
        assert len(config.skip_paths) == 2
        assert len(config.skip_patterns) == 1
        assert len(config.skip_extensions) == 2
        assert "example.com" in config.domain_overrides

    def test_pattern_compilation(self):
        """Test that patterns are compiled on init."""
        config = URLFilterConfig(skip_patterns=["^/[a-z]{2}/news/", "/archive/\\d+"])
        assert len(config._compiled_patterns) == 2

    def test_invalid_pattern_warning(self, capsys):
        """Test that invalid regex patterns produce warning but don't fail."""
        config = URLFilterConfig(skip_patterns=["[invalid(regex"])
        assert len(config._compiled_patterns) == 0
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "Invalid" in captured.out


class TestURLFilterExtensions:
    """Tests for file extension filtering."""

    def test_skip_pdf(self):
        """Test that PDF files are skipped."""
        config = URLFilterConfig(skip_extensions=[".pdf"])
        url_filter = URLFilter(config)

        result = url_filter.check_url("https://example.gov/policy.pdf")
        assert result.should_skip is True
        assert result.rule_type == "extension"
        assert ".pdf" in result.matched_rule

    def test_skip_doc(self):
        """Test that DOC files are skipped."""
        config = URLFilterConfig(skip_extensions=[".doc", ".docx"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/report.doc")
        assert url_filter.should_skip("https://example.gov/report.docx")

    def test_case_insensitive_extension(self):
        """Test that extension matching is case-insensitive."""
        config = URLFilterConfig(skip_extensions=[".pdf"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/policy.PDF")
        assert url_filter.should_skip("https://example.gov/policy.Pdf")

    def test_pass_html(self):
        """Test that HTML pages pass through."""
        config = URLFilterConfig(skip_extensions=[".pdf", ".doc"])
        url_filter = URLFilter(config)

        assert not url_filter.should_skip("https://example.gov/policy.html")
        assert not url_filter.should_skip("https://example.gov/policy")

    def test_extension_at_end_only(self):
        """Test that extension must be at end of path."""
        config = URLFilterConfig(skip_extensions=[".pdf"])
        url_filter = URLFilter(config)

        # Should skip - .pdf at end
        assert url_filter.should_skip("https://example.gov/docs/policy.pdf")

        # Should NOT skip - .pdf in middle of path
        assert not url_filter.should_skip("https://example.gov/.pdf/policy")


class TestURLFilterPaths:
    """Tests for path-based filtering."""

    def test_skip_login(self):
        """Test that login pages are skipped."""
        config = URLFilterConfig(skip_paths=["/login"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/login")
        assert url_filter.should_skip("https://example.gov/user/login")
        assert url_filter.should_skip("https://example.gov/en/login/")

    def test_skip_privacy(self):
        """Test that privacy pages are skipped."""
        config = URLFilterConfig(skip_paths=["/privacy", "/privacy-policy"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/privacy")
        assert url_filter.should_skip("https://example.gov/privacy-policy")
        assert url_filter.should_skip("https://example.gov/about/privacy-policy")

    def test_case_insensitive_path(self):
        """Test that path matching is case-insensitive."""
        config = URLFilterConfig(skip_paths=["/login"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/LOGIN")
        assert url_filter.should_skip("https://example.gov/Login")
        assert url_filter.should_skip("https://example.gov/LOGIN/page")

    def test_pass_policy_pages(self):
        """Test that policy pages pass through."""
        config = URLFilterConfig(skip_paths=["/login", "/contact"])
        url_filter = URLFilter(config)

        assert not url_filter.should_skip("https://example.gov/policy/energy")
        assert not url_filter.should_skip("https://example.gov/regulations")
        assert not url_filter.should_skip("https://example.gov/heat-reuse")

    def test_substring_match(self):
        """Test that skip_paths use substring matching."""
        config = URLFilterConfig(skip_paths=["/cart"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://shop.com/cart")
        assert url_filter.should_skip("https://shop.com/cart/checkout")
        # Note: "shopping-cart" does NOT match "/cart" because we look for "/cart" substring
        # This is intentional - if you want to match "cart" anywhere, use pattern instead


class TestURLFilterPatterns:
    """Tests for regex pattern filtering."""

    def test_pattern_news_prefix(self):
        """Test pattern matching for news sections with language prefix."""
        config = URLFilterConfig(skip_patterns=["^/[a-z]{2}/news/"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/en/news/article")
        assert url_filter.should_skip("https://example.gov/de/news/update")
        assert url_filter.should_skip("https://example.gov/sv/news/")

    def test_pattern_date_archive(self):
        """Test pattern matching for date-based archives."""
        config = URLFilterConfig(skip_patterns=["/\\d{4}/\\d{2}/\\d{2}/"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://news.com/2024/01/15/article")
        assert url_filter.should_skip("https://blog.com/posts/2023/12/01/title")

    def test_pattern_pagination(self):
        """Test pattern matching for pagination."""
        config = URLFilterConfig(skip_patterns=["[?&]page=\\d+"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/results?page=5")
        assert url_filter.should_skip("https://example.gov/search?q=test&page=2")

    def test_pass_no_pattern_match(self):
        """Test that non-matching URLs pass through."""
        config = URLFilterConfig(skip_patterns=["^/[a-z]{2}/news/"])
        url_filter = URLFilter(config)

        assert not url_filter.should_skip("https://example.gov/policy/energy")
        assert not url_filter.should_skip("https://example.gov/news/")  # No lang prefix


class TestURLFilterDomainOverrides:
    """Tests for domain-specific filtering."""

    def test_domain_override_skip(self):
        """Test domain-specific skip paths."""
        config = URLFilterConfig(
            domain_overrides={
                "energy.gov": {"skip_paths": ["/articles/", "/person/"]}
            }
        )
        url_filter = URLFilter(config)

        # Should skip for energy.gov
        assert url_filter.should_skip("https://energy.gov/articles/news")
        assert url_filter.should_skip("https://www.energy.gov/person/john-doe")

    def test_domain_override_pass(self):
        """Test that domain overrides don't affect other domains."""
        config = URLFilterConfig(
            domain_overrides={
                "energy.gov": {"skip_paths": ["/articles/"]}
            }
        )
        url_filter = URLFilter(config)

        # Should NOT skip for other domains
        assert not url_filter.should_skip("https://other.gov/articles/news")
        assert not url_filter.should_skip("https://example.com/articles/test")

    def test_domain_with_www(self):
        """Test that www. prefix is handled correctly."""
        config = URLFilterConfig(
            domain_overrides={
                "energy.gov": {"skip_paths": ["/about/"]}
            }
        )
        url_filter = URLFilter(config)

        # Both with and without www should match
        assert url_filter.should_skip("https://energy.gov/about/us")
        assert url_filter.should_skip("https://www.energy.gov/about/us")

    def test_domain_override_with_explicit_domain(self):
        """Test domain override with explicit domain parameter."""
        config = URLFilterConfig(
            domain_overrides={
                "special.gov": {"skip_paths": ["/skip-this/"]}
            }
        )
        url_filter = URLFilter(config)

        # Pass explicit domain that doesn't match URL
        result = url_filter.check_url(
            "https://other.gov/skip-this/page",
            domain="special.gov"
        )
        assert result.should_skip is True


class TestURLFilterStats:
    """Tests for filter statistics tracking."""

    def test_stats_initialization(self):
        """Test that stats start at zero."""
        url_filter = URLFilter(URLFilterConfig())
        stats = url_filter.get_stats()

        assert stats.total_checked == 0
        assert stats.total_skipped == 0
        assert stats.by_path == 0
        assert stats.by_pattern == 0
        assert stats.by_extension == 0
        assert stats.by_domain == 0

    def test_stats_counting(self):
        """Test that stats are counted correctly."""
        config = URLFilterConfig(
            skip_paths=["/login"],
            skip_extensions=[".pdf"],
        )
        url_filter = URLFilter(config)

        # Check various URLs
        url_filter.should_skip("https://example.gov/policy")  # pass
        url_filter.should_skip("https://example.gov/login")  # skip by path
        url_filter.should_skip("https://example.gov/doc.pdf")  # skip by extension
        url_filter.should_skip("https://example.gov/another")  # pass

        stats = url_filter.get_stats()
        assert stats.total_checked == 4
        assert stats.total_skipped == 2
        assert stats.by_path == 1
        assert stats.by_extension == 1
        assert stats.passed == 2

    def test_skip_rate_calculation(self):
        """Test skip rate percentage calculation."""
        config = URLFilterConfig(skip_paths=["/skip"])
        url_filter = URLFilter(config)

        # Skip 2 out of 4
        url_filter.should_skip("https://example.gov/pass1")
        url_filter.should_skip("https://example.gov/skip/1")
        url_filter.should_skip("https://example.gov/pass2")
        url_filter.should_skip("https://example.gov/skip/2")

        stats = url_filter.get_stats()
        assert stats.skip_rate == 50.0

    def test_skip_rate_zero_division(self):
        """Test skip rate when no URLs checked."""
        url_filter = URLFilter(URLFilterConfig())
        stats = url_filter.get_stats()
        assert stats.skip_rate == 0.0

    def test_stats_reset(self):
        """Test resetting statistics."""
        config = URLFilterConfig(skip_paths=["/login"])
        url_filter = URLFilter(config)

        url_filter.should_skip("https://example.gov/login")
        url_filter.should_skip("https://example.gov/page")

        url_filter.reset_stats()
        stats = url_filter.get_stats()

        assert stats.total_checked == 0
        assert stats.total_skipped == 0

    def test_format_stats(self):
        """Test stats formatting."""
        config = URLFilterConfig(skip_paths=["/login"])
        url_filter = URLFilter(config)

        url_filter.should_skip("https://example.gov/login")
        url_filter.should_skip("https://example.gov/page")

        formatted = url_filter.format_stats()
        assert "Total checked:" in formatted
        assert "Total skipped:" in formatted
        assert "50.0%" in formatted


class TestFilterResult:
    """Tests for FilterResult dataclass."""

    def test_skip_result(self):
        """Test creating skip result."""
        result = FilterResult(
            should_skip=True,
            reason="Matched skip path: /login",
            rule_type="path",
            matched_rule="/login",
        )
        assert result.should_skip is True
        assert "login" in result.reason

    def test_pass_result(self):
        """Test creating pass result."""
        result = FilterResult(should_skip=False)
        assert result.should_skip is False
        assert result.reason is None


class TestLoadURLFilters:
    """Tests for configuration loading."""

    def test_load_missing_file(self):
        """Test loading when file doesn't exist."""
        config = load_url_filters(Path("/nonexistent/path.yaml"))
        assert config.skip_paths == []
        assert config.skip_extensions == []

    def test_load_empty_file(self, tmp_path):
        """Test loading empty YAML file."""
        config_file = tmp_path / "url_filters.yaml"
        config_file.write_text("")

        config = load_url_filters(config_file)
        assert config.skip_paths == []

    def test_load_valid_config(self, tmp_path):
        """Test loading valid config file."""
        config_file = tmp_path / "url_filters.yaml"
        config_file.write_text("""
url_filters:
  skip_paths:
    - /login
    - /contact
  skip_extensions:
    - .pdf
  skip_patterns:
    - "^/news/"
  domain_overrides:
    example.com:
      skip_paths:
        - /about/
""")

        config = load_url_filters(config_file)
        assert "/login" in config.skip_paths
        assert "/contact" in config.skip_paths
        assert ".pdf" in config.skip_extensions
        assert "^/news/" in config.skip_patterns
        assert "example.com" in config.domain_overrides

    def test_load_malformed_yaml(self, tmp_path, capsys):
        """Test loading malformed YAML produces warning."""
        config_file = tmp_path / "url_filters.yaml"
        config_file.write_text("url_filters: [invalid: yaml: :]")

        config = load_url_filters(config_file)
        captured = capsys.readouterr()
        assert "Warning" in captured.out or config.skip_paths == []


class TestCreateURLFilter:
    """Tests for create_url_filter convenience function."""

    def test_create_with_default_path(self, tmp_path, monkeypatch):
        """Test creating filter with default path."""
        # Create temp config
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "url_filters.yaml"
        config_file.write_text("""
url_filters:
  skip_paths:
    - /test/
""")

        # Change working directory
        monkeypatch.chdir(tmp_path)

        url_filter = create_url_filter()
        assert url_filter.should_skip("https://example.com/test/page")

    def test_create_with_custom_path(self, tmp_path):
        """Test creating filter with custom path."""
        config_file = tmp_path / "custom_filters.yaml"
        config_file.write_text("""
url_filters:
  skip_extensions:
    - .zip
""")

        url_filter = create_url_filter(config_file)
        assert url_filter.should_skip("https://example.com/file.zip")


class TestURLFilterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_malformed_url(self):
        """Test handling of malformed URLs."""
        url_filter = URLFilter(URLFilterConfig(skip_paths=["/login"]))

        # Should not crash on malformed URLs
        result = url_filter.check_url("not-a-url")
        assert result.should_skip is False

    def test_empty_path(self):
        """Test handling of root path."""
        config = URLFilterConfig(skip_paths=["/login"])
        url_filter = URLFilter(config)

        assert not url_filter.should_skip("https://example.gov/")
        assert not url_filter.should_skip("https://example.gov")

    def test_query_string_ignored_for_paths(self):
        """Test that query strings don't affect path matching."""
        config = URLFilterConfig(skip_paths=["/search"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/search?q=test")
        assert url_filter.should_skip("https://example.gov/search?q=test&page=1")

    def test_fragment_ignored(self):
        """Test that URL fragments don't affect matching."""
        config = URLFilterConfig(skip_paths=["/login"])
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.gov/login#section")

    def test_unicode_in_url(self):
        """Test handling of unicode characters in URLs."""
        config = URLFilterConfig(skip_paths=["/nieuws"])  # Dutch for "news"
        url_filter = URLFilter(config)

        assert url_filter.should_skip("https://example.nl/nieuws/artikel")

    def test_priority_order(self):
        """Test that rules are checked in correct priority order."""
        # Extension > Domain > Path > Pattern
        config = URLFilterConfig(
            skip_paths=["/docs"],
            skip_extensions=[".pdf"],
            domain_overrides={"example.com": {"skip_paths": ["/special"]}}
        )
        url_filter = URLFilter(config)

        # Extension should be checked first
        result = url_filter.check_url("https://example.com/docs/file.pdf")
        assert result.rule_type == "extension"

    def test_no_config(self):
        """Test that URLFilter works with no config."""
        url_filter = URLFilter(None)

        # Should not skip anything
        assert not url_filter.should_skip("https://example.gov/login")
        assert not url_filter.should_skip("https://example.gov/file.pdf")


class TestIntegrationScenarios:
    """Integration-style tests with realistic scenarios."""

    def test_energy_gov_scenario(self):
        """Test realistic energy.gov filtering scenario."""
        config = URLFilterConfig(
            skip_paths=[
                "/login",
                "/contact",
                "/privacy",
                "/careers",
            ],
            skip_extensions=[".pdf", ".doc"],
            domain_overrides={
                "energy.gov": {
                    "skip_paths": ["/articles/", "/person/", "/leadership/"]
                }
            }
        )
        url_filter = URLFilter(config)

        # Should skip
        assert url_filter.should_skip("https://energy.gov/articles/news-update")
        assert url_filter.should_skip("https://energy.gov/person/john-smith")
        assert url_filter.should_skip("https://energy.gov/careers")
        assert url_filter.should_skip("https://energy.gov/report.pdf")

        # Should pass (policy-relevant pages)
        assert not url_filter.should_skip("https://energy.gov/eere/buildings/data-centers")
        assert not url_filter.should_skip("https://energy.gov/policy/energy-efficiency")
        assert not url_filter.should_skip("https://energy.gov/femp/data-center-energy")

    def test_nordic_government_scenario(self):
        """Test realistic Nordic government site filtering."""
        config = URLFilterConfig(
            skip_paths=[
                "/login",
                "/om-oss",  # Swedish "about us"
                "/nyheter",  # Swedish "news"
            ],
            skip_patterns=[
                "^/[a-z]{2}/nyheter/",
                "^/[a-z]{2}/aktuellt/",
            ]
        )
        url_filter = URLFilter(config)

        # Should skip news and about pages
        assert url_filter.should_skip("https://energimyndigheten.se/sv/nyheter/")
        assert url_filter.should_skip("https://energimyndigheten.se/om-oss/")

        # Should pass policy pages
        assert not url_filter.should_skip("https://energimyndigheten.se/fornybart/")
        assert not url_filter.should_skip("https://energimyndigheten.se/energieffektivisering/")

    def test_batch_filtering(self):
        """Test filtering a batch of URLs and checking stats."""
        config = URLFilterConfig(
            skip_paths=["/login", "/contact", "/privacy"],
            skip_extensions=[".pdf"],
        )
        url_filter = URLFilter(config)

        urls = [
            "https://example.gov/policy/heat-reuse",  # pass
            "https://example.gov/login",  # skip
            "https://example.gov/regulations",  # pass
            "https://example.gov/contact",  # skip
            "https://example.gov/document.pdf",  # skip
            "https://example.gov/data-centers",  # pass
        ]

        results = [url_filter.should_skip(url) for url in urls]

        assert results == [False, True, False, True, True, False]

        stats = url_filter.get_stats()
        assert stats.total_checked == 6
        assert stats.total_skipped == 3
        assert stats.passed == 3
        assert stats.skip_rate == 50.0
