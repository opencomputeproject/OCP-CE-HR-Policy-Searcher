"""Tests for HtmlExtractor."""

from pathlib import Path

import pytest

from src.core.extractor import HtmlExtractor


@pytest.fixture
def extractor():
    # Use a non-existent config dir so defaults are used
    return HtmlExtractor(config_dir="__nonexistent__")


@pytest.mark.small
class TestExtractBasicContent:
    def test_extracts_text_from_body(self, extractor):
        html = "<html><body><p>Hello World</p></body></html>"
        result = extractor.extract(html)
        assert "Hello World" in result.text

    def test_word_count(self, extractor):
        html = "<html><body><p>one two three four five</p></body></html>"
        result = extractor.extract(html)
        assert result.word_count == 5

    def test_extracts_title_from_title_tag(self, extractor):
        html = "<html><head><title>Test Page</title></head><body><p>Content</p></body></html>"
        result = extractor.extract(html)
        assert result.title == "Test Page"

    def test_extracts_title_from_h1_fallback(self, extractor):
        html = "<html><body><h1>Main Heading</h1><p>Content</p></body></html>"
        result = extractor.extract(html)
        assert result.title == "Main Heading"

    def test_detects_language_from_html_attr(self, extractor):
        html = '<html lang="de"><body><p>Inhalt</p></body></html>'
        result = extractor.extract(html)
        assert result.language == "de"

    def test_returns_empty_text_for_empty_html(self, extractor):
        result = extractor.extract("")
        assert result.text == ""
        assert result.word_count == 0


@pytest.mark.small
class TestBoilerplateRemoval:
    def test_removes_nav(self, extractor):
        html = """
        <html><body>
            <nav><a href="/home">Home</a><a href="/about">About</a></nav>
            <main><p>Important policy content here</p></main>
        </body></html>
        """
        result = extractor.extract(html)
        assert "Important policy content" in result.text
        assert "Home" not in result.text

    def test_removes_footer(self, extractor):
        html = """
        <html><body>
            <main><p>Policy text</p></main>
            <footer><p>Copyright 2024</p></footer>
        </body></html>
        """
        result = extractor.extract(html)
        assert "Policy text" in result.text
        assert "Copyright" not in result.text

    def test_removes_script_and_style(self, extractor):
        html = """
        <html><body>
            <script>var x = 1;</script>
            <style>.red { color: red; }</style>
            <p>Real content</p>
        </body></html>
        """
        result = extractor.extract(html)
        assert "Real content" in result.text
        assert "var x" not in result.text
        assert ".red" not in result.text

    def test_removes_cookie_banner_by_class(self, extractor):
        html = """
        <html><body>
            <div class="cookie-consent">Accept cookies</div>
            <article><p>Policy details</p></article>
        </body></html>
        """
        result = extractor.extract(html)
        assert "Policy details" in result.text
        assert "Accept cookies" not in result.text

    def test_removes_sidebar_by_id(self, extractor):
        html = """
        <html><body>
            <div id="sidebar-nav">Links here</div>
            <article><p>Main content</p></article>
        </body></html>
        """
        result = extractor.extract(html)
        assert "Main content" in result.text
        assert "Links here" not in result.text


@pytest.mark.small
class TestMainContentDetection:
    def test_finds_main_tag(self, extractor):
        html = """
        <html><body>
            <div><p>Outer noise</p></div>
            <main><p>Main content here</p></main>
        </body></html>
        """
        result = extractor.extract(html)
        assert "Main content here" in result.text

    def test_finds_article_tag(self, extractor):
        html = """
        <html><body>
            <article><p>Article content</p></article>
            <aside><p>Sidebar stuff</p></aside>
        </body></html>
        """
        result = extractor.extract(html)
        assert "Article content" in result.text

    def test_finds_content_class(self, extractor):
        html = """
        <html><body>
            <div class="page-content"><p>Real stuff</p></div>
            <div class="ad-block"><p>Buy now</p></div>
        </body></html>
        """
        result = extractor.extract(html)
        assert "Real stuff" in result.text

    def test_falls_back_to_body(self, extractor):
        html = "<html><body><p>Just body</p></body></html>"
        result = extractor.extract(html)
        assert "Just body" in result.text


@pytest.mark.small
class TestMaxLength:
    def test_respects_max_length(self):
        extractor = HtmlExtractor.__new__(HtmlExtractor)
        extractor._remove_tags = []
        extractor._remove_patterns = []
        extractor._content_patterns = []
        extractor._max_length = 20

        html = "<html><body><p>" + "a" * 100 + "</p></body></html>"
        result = extractor.extract(html)
        assert len(result.text) <= 20


# ---------------------------------------------------------------------------
# PL-011: the reviewer's keeps that extracted to nothing (2026-09-08)
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "extraction"

POLICY = " ".join(["Data centres shall recover waste heat for district heating."] * 20)


class TestABoilerplateMatchCannotDeleteThePage:
    """`sidebar` matches `no-sidebar`, `cookie` matches `alert__has-cookie`:
    layout-state classes on wrappers. A banner is never half the page."""

    @pytest.mark.small
    def test_a_no_sidebar_wrapper_keeps_its_content(self, extractor):
        # emb3rs.eu: <div class="no-sidebar"> wraps the whole site -> 49 chars
        html = f'<html><body><div class="no-sidebar"><div class="content"><p>{POLICY}</p></div></div></body></html>'
        assert "waste heat" in extractor.extract(html).text

    @pytest.mark.small
    def test_a_cookie_state_class_on_body_keeps_its_content(self, extractor):
        # bidenwhitehouse.archives.gov: <body class="alert__has-cookie"> -> 0 chars
        html = f'<html><body class="alert__has-cookie"><main><p>{POLICY}</p></main></body></html>'
        assert "waste heat" in extractor.extract(html).text

    @pytest.mark.small
    def test_a_has_sidebar_layout_wrapper_keeps_its_content(self, extractor):
        html = f'<html><body><div class="has-sidebar"><article><p>{POLICY}</p></article></div></body></html>'
        assert "waste heat" in extractor.extract(html).text

    @pytest.mark.small
    def test_a_real_cookie_banner_is_still_removed(self, extractor):
        html = (
            f'<html><body><div class="cookie-banner">We use cookies. Accept?</div>'
            f'<main><p>{POLICY}</p></main></body></html>'
        )
        text = extractor.extract(html).text
        assert "waste heat" in text
        assert "cookies" not in text


class TestTheMainContentPickIsTheBiggestCandidate:
    @pytest.mark.small
    def test_an_empty_article_before_the_content_does_not_win(self, extractor):
        # ec.europa.eu Have Your Say: the first <article> is an empty shell
        html = (
            f'<html><body><article></article>'
            f'<div class="page-content"><p>{POLICY}</p></div></body></html>'
        )
        assert "waste heat" in extractor.extract(html).text

    @pytest.mark.small
    def test_a_one_character_content_class_does_not_win(self, extractor):
        # eur-lex.europa.eu: <div class="modal-content">x</div> came first
        html = (
            f'<html><body><div class="modal-content">x</div>'
            f'<div id="text-content"><p>{POLICY}</p></div></body></html>'
        )
        text = extractor.extract(html).text
        assert "waste heat" in text and text.strip() != "x"

    @pytest.mark.small
    def test_a_small_main_falls_back_to_the_body(self, extractor):
        html = f'<html><body><main>Skip to content</main><div><p>{POLICY}</p></div></body></html>'
        assert "waste heat" in extractor.extract(html).text


class TestRecordedPages:
    """The real pages, as fetched 2026-09-08, that produced 0 characters."""

    @pytest.mark.small
    def test_have_your_say_initiative_rendered_by_playwright(self, extractor):
        html = (FIXTURES / "r083-ec-europa-eu.rendered.html").read_text(encoding="utf-8")
        text = extractor.extract(html, "https://ec.europa.eu/info/law/better-regulation/have-your-say/initiatives/12889").text
        # The pick is the portal's ecl-main-content block: the initiative
        # summary, type of act, feedback windows. 656 chars; it was 0.
        assert len(text) > 500, len(text)
        assert "energy efficiency first" in text.lower()
        assert "Type of act" in text

    @pytest.mark.small
    def test_white_house_executive_order_over_httpx(self, extractor):
        html = (FIXTURES / "r131-bidenwhitehouse-archives-gov.html").read_text(encoding="utf-8")
        text = extractor.extract(html).text
        assert len(text) > 20000, len(text)
        assert "Sec. 2." in text
