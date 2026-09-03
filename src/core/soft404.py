"""Soft-404 detection: a page that is a missing-document placeholder wearing
a 200 status code.

Six of the reviewer's 88 removals needed no model at all: "not a real
website", "link is an error page", and similar. A soft 404 is exactly that -
the server answers with content instead of an HTTP error, so nothing
upstream of the pipeline catches it, and it would otherwise cost a screening
and possibly an analysis call before a model notices there is no document
here. See docs/HOW_IT_WORKS.md, "The link check".

Deliberately conservative: both signals below require the page to be short.
A long page that happens to contain the word "404" - an article about HTTP
status codes, a statute section numbered 404 - must never be dropped, so
every signal is gated on word count first.
"""

# Title or the first 300 characters of text match one of these,
# case-insensitively, when the extracted text is under 400 words. Grouped by
# language for readability; matching is a plain substring check, since a
# soft-404 page is short enough that false positives from mid-word matches
# are not a practical concern.
_PATTERNS = [
    # English
    "page not found", "404", "not found", "does not exist",
    "no longer available", "the page you requested",
    # German
    "seite nicht gefunden", "nicht gefunden", "existiert nicht",
    # Danish
    "siden blev ikke fundet", "findes ikke",
    # Dutch
    "pagina niet gevonden",
    # French
    "page introuvable", "n'existe pas",
    # Swedish
    "sidan hittades inte",
    # Spanish
    "página no encontrada",
    # Japanese
    "ページが見つかりません",
]

# A bare, short title with almost no body is its own signal, for a title
# like "Error" that is too generic to put in the pattern table above (it
# would false-positive on any long page whose title happens to be "Error").
_SHORT_TITLES = {"404", "not found", "error"}

_SHORT_PAGE_WORDS = 400
_VERY_SHORT_PAGE_WORDS = 30
_HEAD_CHARS = 300


def looks_like_soft_404(title: str | None, text: str, url: str = "") -> bool:
    """Whether this page is a missing-document placeholder, not a document.

    ``url`` is accepted for callers that have one to hand (logging, future
    URL-shaped signals) but is not currently part of the decision.
    """
    text = text or ""
    title = title or ""
    word_count = len(text.split())

    # Never fire on a long page, even one that contains "404" somewhere -
    # the reviewer's rule is about pages with nothing on them, not about a
    # word appearing in a real document.
    if word_count >= _SHORT_PAGE_WORDS:
        return False

    haystack = f"{title} {text[:_HEAD_CHARS]}".lower()
    if any(pattern in haystack for pattern in _PATTERNS):
        return True

    if word_count < _VERY_SHORT_PAGE_WORDS and title.strip().lower() in _SHORT_TITLES:
        return True

    return False
