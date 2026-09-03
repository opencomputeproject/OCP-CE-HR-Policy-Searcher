"""Tests for soft-404 detection (WP-4): a page that is a missing-page
placeholder in disguise should never reach a model.

See docs/HOW_IT_WORKS.md, "The link check", and the reviewer's row "Link is
a general site, an error page, not the document" in "The reviewer's
vocabulary".
"""

import pytest

from src.core.soft404 import looks_like_soft_404

# One representative phrase per language row from the work package spec.
LANGUAGE_SIGNALS = [
    ("English", "page not found"),
    ("English", "404"),
    ("English", "not found"),
    ("English", "does not exist"),
    ("English", "no longer available"),
    ("English", "the page you requested"),
    ("German", "Seite nicht gefunden"),
    ("German", "nicht gefunden"),
    ("German", "existiert nicht"),
    ("Danish", "siden blev ikke fundet"),
    ("Danish", "findes ikke"),
    ("Dutch", "pagina niet gevonden"),
    ("French", "page introuvable"),
    ("French", "n'existe pas"),
    ("Swedish", "sidan hittades inte"),
    ("Spanish", "página no encontrada"),
    ("Japanese", "ページが見つかりません"),
]

_IDS = [f"{lang}:{phrase}" for lang, phrase in LANGUAGE_SIGNALS]


@pytest.mark.small
class TestLanguagePatterns:
    """Every language row fires when the phrase is on a short page."""

    @pytest.mark.parametrize("language, phrase", LANGUAGE_SIGNALS, ids=_IDS)
    def test_pattern_in_body_fires_on_a_short_page(self, language, phrase):
        text = f"{phrase}. Please check the URL and try again."
        assert looks_like_soft_404(
            title="Oops", text=text, url="https://example.gov/gone",
        ) is True

    @pytest.mark.parametrize("language, phrase", LANGUAGE_SIGNALS, ids=_IDS)
    def test_pattern_in_title_fires_too(self, language, phrase):
        assert looks_like_soft_404(title=phrase, text="Short body text.") is True


@pytest.mark.small
class TestNeverFiresOnALongPage:
    """A long page must never be dropped, even if it says "404" somewhere."""

    def test_long_page_mentioning_404_is_not_flagged(self):
        body = " ".join(["word"] * 450)
        text = f"Error code 404 appears in this long article. {body}"
        assert looks_like_soft_404(
            title="Article about HTTP status codes", text=text,
        ) is False

    def test_word_count_boundary_at_400_does_not_fire(self):
        text = " ".join(["word"] * 400)
        assert looks_like_soft_404(title="Nothing special", text=text) is False


@pytest.mark.small
class TestShortTitleRule:
    """Under 30 words with a bare "404"/"Not Found"/"Error" title fires,
    even when the title text alone wouldn't otherwise be a pattern match."""

    @pytest.mark.parametrize("title", ["404", "Not Found", "Error"])
    def test_short_title_with_short_body_fires(self, title):
        assert looks_like_soft_404(title=title, text="Sorry, nothing here.") is True

    def test_bare_error_title_does_not_fire_when_over_thirty_words(self):
        # "error" alone matches no language pattern, so once the body is at
        # or past the 30-word threshold this signal must not fire either.
        text = " ".join(["word"] * 35)
        assert looks_like_soft_404(title="Error", text=text) is False

    def test_unrelated_short_title_does_not_fire(self):
        assert looks_like_soft_404(title="Welcome", text="Hello there.") is False


@pytest.mark.small
class TestGracefulInputs:
    def test_none_title_and_empty_text(self):
        assert looks_like_soft_404(title=None, text="", url="") is False

    def test_missing_url_argument_is_optional(self):
        assert looks_like_soft_404(title="404", text="gone") is True
