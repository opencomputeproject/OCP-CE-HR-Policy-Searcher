"""HTML content extraction with boilerplate removal."""

import re
import warnings
from pathlib import Path

import yaml
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
from langdetect import detect, LangDetectException

from .models import ExtractedContent

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


# Default tags to completely remove
_DEFAULT_REMOVE_TAGS = [
    "nav", "footer", "header", "aside", "script", "style", "noscript",
    "iframe", "svg", "canvas", "video", "audio", "map", "object", "embed",
]

# Class/ID patterns indicating boilerplate
_DEFAULT_REMOVE_PATTERNS = [
    r"cookie", r"consent", r"gdpr", r"privacy-banner", r"cc-banner",
    r"nav", r"menu", r"breadcrumb", r"pagination", r"sidebar",
    r"social", r"share", r"twitter", r"facebook", r"linkedin",
    r"ad-", r"ads-", r"advert", r"banner", r"promo", r"sponsor",
    r"comment", r"disqus", r"discuss",
    r"footer", r"copyright", r"legal",
    r"newsletter", r"subscribe", r"signup", r"login", r"search-form",
    r"related-posts", r"recommended", r"popular", r"trending",
]

# Content area indicators
_DEFAULT_CONTENT_INDICATORS = [
    r"content", r"article", r"main", r"post", r"entry", r"text",
    r"body-content", r"page-content", r"story",
]


def _text_len(el) -> int:
    return len(el.get_text(" ", strip=True)) if isinstance(el, Tag) else 0


class HtmlExtractor:
    """HTML content extractor with boilerplate removal.

    Two rules keep the boilerplate patterns from eating the page, both
    learned from the reviewer's own keeps (PL-011, 2026-09-08):

    - A boilerplate match is removed only if it holds less than
      WRAPPER_SHARE of the page's text. "sidebar" also matches the layout
      class `no-sidebar` on a site's outer wrapper and "cookie" matches
      `alert__has-cookie` on a `<body>`; a banner is never half the page,
      so a match that big is a wrapper wearing a state class, not
      boilerplate.
    - The main-content pick is the candidate with the MOST text, and only
      if it holds at least MAIN_SHARE of the page; the first `<article>`
      on the Have Your Say portal is empty and EUR-Lex's first "content"
      class is a one-character modal. Otherwise the whole body is used.
    """

    WRAPPER_SHARE = 0.5
    MAIN_SHARE = 0.2

    def __init__(self, config_dir: str = "config"):
        cfg = self._load_config(config_dir)
        self._remove_tags = cfg.get("remove_tags", _DEFAULT_REMOVE_TAGS)
        self._remove_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in cfg.get("remove_patterns", _DEFAULT_REMOVE_PATTERNS)
        ]
        self._content_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in cfg.get("content_indicators", _DEFAULT_CONTENT_INDICATORS)
        ]
        self._max_length = cfg.get("max_content_length", 0)

    def _load_config(self, config_dir: str) -> dict:
        path = Path(config_dir) / "content_extraction.yaml"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("content_extraction", {})
        except Exception:
            return {}

    def extract(self, html: str, url: str = "") -> ExtractedContent:
        """Extract main content from HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Remove structural tags
        for tag_name in self._remove_tags:
            for el in soup.find_all(tag_name):
                el.decompose()

        # Remove elements matching boilerplate patterns - unless the match
        # is the page itself (see the class docstring).
        page_len = _text_len(soup.body or soup)
        to_remove = []
        for el in soup.find_all(True):
            if not isinstance(el, Tag) or el.name in ("html", "body"):
                continue
            if self._matches_any(el, self._remove_patterns):
                if page_len and _text_len(el) >= self.WRAPPER_SHARE * page_len:
                    continue
                to_remove.append(el)

        for el in to_remove:
            el.decompose()

        # Find main content area
        main = self._find_main_content(soup)

        # Extract text
        text = main.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        if self._max_length > 0:
            text = text[:self._max_length]

        # Title
        title = None
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)

        # Language
        language = None
        if soup.html and soup.html.get("lang"):
            language = soup.html.get("lang")[:2]
        elif len(text) > 50:
            try:
                language = detect(text)
            except LangDetectException:
                pass

        return ExtractedContent(
            text=text,
            title=title,
            language=language,
            word_count=len(text.split()),
        )

    @staticmethod
    def _matches_any(el: Tag, patterns) -> bool:
        classes = el.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        el_id = el.get("id", "")
        return any(
            any(p.search(cls) for cls in classes) or (el_id and p.search(el_id))
            for p in patterns
        )

    def _find_main_content(self, soup: BeautifulSoup) -> Tag:
        """The main content area: semantic HTML first, then class/id hints,
        the body as the fallback. Among candidates the one with the most
        text wins, and a winner must hold at least MAIN_SHARE of the page's
        text - an empty `<article>` or a one-character "content" modal is
        not the page."""
        body = soup.body or soup
        page_len = _text_len(body)

        def best(candidates):
            candidates = [c for c in candidates if isinstance(c, Tag)]
            if not candidates:
                return None
            top = max(candidates, key=_text_len)
            return top if _text_len(top) >= self.MAIN_SHARE * page_len else None

        semantic = soup.find_all("main") + soup.find_all("article") + soup.find_all(role="main")
        pick = best(semantic)
        if pick is not None:
            return pick

        indicated = [
            el for el in soup.find_all(True)
            if isinstance(el, Tag) and el.name not in ("html", "body")
            and self._matches_any(el, self._content_patterns)
        ]
        pick = best(indicated)
        return pick if pick is not None else body
