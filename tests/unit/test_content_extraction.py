"""Unit tests for content extraction (Phase 3)."""

import pytest
from pathlib import Path
import tempfile

from src.crawler.extractors.html_extractor import (
    HtmlExtractor,
    ExtractionConfig,
    ExtractionStats,
    load_extraction_config,
)


class TestExtractionConfig:
    """Tests for ExtractionConfig dataclass."""

    def test_default_config(self):
        """Default config has expected values."""
        config = ExtractionConfig()
        assert "nav" in config.remove_tags
        assert "script" in config.remove_tags
        assert len(config.remove_patterns) > 0
        assert len(config.content_indicators) > 0
        assert config.min_content_length == 100
        assert config.max_content_length == 0

    def test_custom_config(self):
        """Custom config overrides defaults."""
        config = ExtractionConfig(
            remove_tags=["div"],
            remove_patterns=["test-pattern"],
            min_content_length=50,
            max_content_length=1000,
        )
        assert config.remove_tags == ["div"]
        assert config.remove_patterns == ["test-pattern"]
        assert config.min_content_length == 50
        assert config.max_content_length == 1000


class TestExtractionStats:
    """Tests for ExtractionStats dataclass."""

    def test_initial_values(self):
        """Stats start at zero."""
        stats = ExtractionStats()
        assert stats.original_length == 0
        assert stats.extracted_length == 0
        assert stats.compression_ratio == 0.0

    def test_compute_ratio(self):
        """Compression ratio is computed correctly."""
        stats = ExtractionStats(original_length=1000, extracted_length=300)
        stats.compute_ratio()
        assert stats.compression_ratio == 0.7

    def test_compute_ratio_zero_original(self):
        """Zero original length doesn't cause division error."""
        stats = ExtractionStats(original_length=0, extracted_length=100)
        stats.compute_ratio()
        assert stats.compression_ratio == 0.0


class TestHtmlExtractor:
    """Tests for HtmlExtractor class."""

    @pytest.fixture
    def extractor(self):
        """Create extractor with default config."""
        return HtmlExtractor()

    @pytest.fixture
    def simple_html(self):
        """Simple HTML with main content."""
        return """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <main>
                <h1>Main Content</h1>
                <p>This is the main policy content about data center heat reuse.</p>
            </main>
        </body>
        </html>
        """

    def test_extract_main_content(self, extractor, simple_html):
        """Extracts content from main tag."""
        result = extractor.extract(simple_html, "https://example.com")
        assert "Main Content" in result.text
        assert "data center heat reuse" in result.text
        assert result.title == "Test Page"

    def test_removes_script_tags(self, extractor):
        """Script tags are removed."""
        html = """
        <html>
        <body>
            <main>
                <p>Content</p>
                <script>alert('should be removed');</script>
            </main>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "alert" not in result.text
        assert "Content" in result.text

    def test_removes_nav_tags(self, extractor):
        """Nav tags are removed."""
        html = """
        <html>
        <body>
            <nav><a href="/">Home</a><a href="/about">About</a></nav>
            <main><p>Main content here</p></main>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Home" not in result.text
        assert "About" not in result.text
        assert "Main content here" in result.text

    def test_removes_footer_tags(self, extractor):
        """Footer tags are removed."""
        html = """
        <html>
        <body>
            <main><p>Main content</p></main>
            <footer><p>Copyright 2024</p></footer>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Copyright" not in result.text
        assert "Main content" in result.text

    def test_removes_cookie_banner_by_class(self, extractor):
        """Cookie banners are removed by class pattern."""
        html = """
        <html>
        <body>
            <div class="cookie-notice">Accept cookies</div>
            <main><p>Policy content</p></main>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Accept cookies" not in result.text
        assert "Policy content" in result.text

    def test_removes_social_widgets_by_id(self, extractor):
        """Social widgets are removed by id pattern."""
        html = """
        <html>
        <body>
            <div id="social-share">Share on Twitter</div>
            <main><p>Policy content</p></main>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Share on Twitter" not in result.text
        assert "Policy content" in result.text

    def test_removes_newsletter_signup(self, extractor):
        """Newsletter signup sections are removed."""
        html = """
        <html>
        <body>
            <main><p>Policy content</p></main>
            <div class="newsletter-signup">Subscribe to updates</div>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Subscribe" not in result.text

    def test_removes_sidebar(self, extractor):
        """Sidebar elements are removed."""
        html = """
        <html>
        <body>
            <div class="sidebar"><p>Related links</p></div>
            <main><p>Main policy content</p></main>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Related links" not in result.text
        assert "Main policy content" in result.text

    def test_finds_article_when_no_main(self, extractor):
        """Uses article tag when main is not present."""
        html = """
        <html>
        <body>
            <article>
                <h1>Article Title</h1>
                <p>Article content about policy.</p>
            </article>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Article Title" in result.text
        assert "Article content" in result.text

    def test_finds_role_main(self, extractor):
        """Uses role="main" attribute."""
        html = """
        <html>
        <body>
            <div role="main">
                <p>Content with role main</p>
            </div>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Content with role main" in result.text

    def test_finds_content_by_class_indicator(self, extractor):
        """Finds content by class indicator when no semantic HTML."""
        html = """
        <html>
        <body>
            <div class="page-content">
                <p>Page content here</p>
            </div>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Page content here" in result.text

    def test_extracts_title_from_h1(self, extractor):
        """Extracts title from h1 when no title tag."""
        html = """
        <html>
        <body>
            <main>
                <h1>Policy Document Title</h1>
                <p>Content</p>
            </main>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert result.title == "Policy Document Title"

    def test_detects_language_from_html_lang(self, extractor):
        """Detects language from html lang attribute."""
        html = """
        <html lang="de-DE">
        <body><main><p>German content</p></main></body>
        </html>
        """
        result = extractor.extract(html, "https://example.com")
        assert result.language == "de"

    def test_word_count(self, extractor, simple_html):
        """Word count is calculated."""
        result = extractor.extract(simple_html, "https://example.com")
        assert result.word_count > 0

    def test_stats_are_tracked(self, extractor, simple_html):
        """Extraction stats are tracked."""
        extractor.extract(simple_html, "https://example.com")
        stats = extractor.get_stats()
        assert stats.original_length > 0
        assert stats.extracted_length > 0
        assert stats.tags_removed >= 0

    def test_format_stats(self, extractor, simple_html):
        """Stats can be formatted as string."""
        extractor.extract(simple_html, "https://example.com")
        formatted = extractor.format_stats()
        assert "Extraction:" in formatted
        assert "chars" in formatted


class TestMaxContentLength:
    """Tests for max_content_length configuration."""

    def test_max_length_truncates_content(self):
        """Content is truncated to max length."""
        config = ExtractionConfig(max_content_length=50)
        extractor = HtmlExtractor(config)
        html = """
        <html><body><main>
        <p>This is a very long piece of content that should be truncated at fifty characters.</p>
        </main></body></html>
        """
        result = extractor.extract(html, "https://example.com")
        assert len(result.text) <= 50

    def test_zero_max_length_unlimited(self):
        """Zero max length means unlimited."""
        config = ExtractionConfig(max_content_length=0)
        extractor = HtmlExtractor(config)
        html = """
        <html><body><main>
        <p>This content should not be truncated at all.</p>
        </main></body></html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "should not be truncated" in result.text


class TestCustomPatterns:
    """Tests for custom removal patterns."""

    def test_custom_remove_pattern(self):
        """Custom patterns can be added."""
        config = ExtractionConfig(remove_patterns=["custom-boilerplate"])
        extractor = HtmlExtractor(config)
        html = """
        <html><body>
            <div class="custom-boilerplate">Remove me</div>
            <main><p>Keep this</p></main>
        </body></html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Remove me" not in result.text
        assert "Keep this" in result.text

    def test_custom_content_indicator(self):
        """Custom content indicators work."""
        config = ExtractionConfig(content_indicators=["my-special-content"])
        extractor = HtmlExtractor(config)
        html = """
        <html><body>
            <div class="my-special-content">
                <p>This is the special content</p>
            </div>
        </body></html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "special content" in result.text


class TestLoadExtractionConfig:
    """Tests for config file loading."""

    def test_missing_file_returns_default(self):
        """Missing config file returns default config."""
        config = load_extraction_config(Path("/nonexistent/path.yaml"))
        assert isinstance(config, ExtractionConfig)
        assert len(config.remove_tags) > 0

    def test_load_valid_config(self):
        """Valid config file is loaded."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
content_extraction:
  remove_tags:
    - div
    - span
  min_content_length: 200
  max_content_length: 5000
""")
            f.flush()
            config = load_extraction_config(Path(f.name))

        assert "div" in config.remove_tags
        assert "span" in config.remove_tags
        assert config.min_content_length == 200
        assert config.max_content_length == 5000

    def test_empty_file_returns_default(self):
        """Empty config file returns default config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            f.flush()
            config = load_extraction_config(Path(f.name))

        assert isinstance(config, ExtractionConfig)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_html(self):
        """Empty HTML doesn't crash."""
        extractor = HtmlExtractor()
        result = extractor.extract("", "https://example.com")
        assert result.text == ""

    def test_malformed_html(self):
        """Malformed HTML is handled gracefully."""
        extractor = HtmlExtractor()
        html = "<html><body><p>Unclosed paragraph"
        result = extractor.extract(html, "https://example.com")
        assert "Unclosed paragraph" in result.text

    def test_no_body_tag(self):
        """HTML without body tag works."""
        extractor = HtmlExtractor()
        html = "<html><p>Just a paragraph</p></html>"
        result = extractor.extract(html, "https://example.com")
        assert "Just a paragraph" in result.text

    def test_deeply_nested_content(self):
        """Deeply nested content is extracted."""
        extractor = HtmlExtractor()
        html = """
        <html><body>
            <div><div><div><div><main>
                <p>Deep content</p>
            </main></div></div></div></div>
        </body></html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Deep content" in result.text

    def test_unicode_content(self):
        """Unicode content is preserved."""
        extractor = HtmlExtractor()
        html = """
        <html><body><main>
            <p>German: Rechenzentrumsabwärme</p>
            <p>Swedish: spillvärme</p>
            <p>Chinese: 数据中心</p>
        </main></body></html>
        """
        result = extractor.extract(html, "https://example.com")
        assert "Rechenzentrumsabwärme" in result.text
        assert "spillvärme" in result.text
        assert "数据中心" in result.text


class TestRealWorldPatterns:
    """Tests with real-world-like HTML patterns."""

    def test_government_site_pattern(self):
        """Handles typical government site structure."""
        extractor = HtmlExtractor()
        html = """
        <html lang="en">
        <head><title>Data Center Energy Policy | Gov.Example</title></head>
        <body>
            <header>
                <nav class="main-navigation">
                    <a href="/">Home</a>
                    <a href="/policies">Policies</a>
                </nav>
            </header>
            <div class="cookie-banner">We use cookies. <button>Accept</button></div>
            <main id="main-content">
                <article>
                    <h1>Data Center Heat Reuse Regulation</h1>
                    <p>This regulation requires all data centers to implement heat recovery systems.</p>
                    <p>Key requirements include annual energy efficiency reporting.</p>
                </article>
            </main>
            <aside class="sidebar">
                <h3>Related Links</h3>
                <ul><li>Energy Policy</li></ul>
            </aside>
            <div class="social-share">Share: Twitter | Facebook</div>
            <footer>
                <p>Copyright 2024 Government</p>
                <nav class="footer-nav">Legal | Privacy</nav>
            </footer>
        </body>
        </html>
        """
        result = extractor.extract(html, "https://gov.example/policy")

        # Main content preserved
        assert "Data Center Heat Reuse Regulation" in result.text
        assert "heat recovery systems" in result.text
        assert "Key requirements" in result.text

        # Boilerplate removed
        assert "We use cookies" not in result.text
        assert "Related Links" not in result.text
        assert "Share: Twitter" not in result.text
        assert "Copyright 2024" not in result.text
        assert "Legal | Privacy" not in result.text

        # Title and language detected
        assert "Data Center Energy Policy" in result.title
        assert result.language == "en"
