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


class HtmlExtractor:
    """HTML content extractor with boilerplate removal."""

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

        # Remove elements matching boilerplate patterns
        to_remove = []
        for el in soup.find_all(True):
            if not isinstance(el, Tag):
                continue
            classes = el.get("class", [])
            if isinstance(classes, str):
                classes = [classes]
            el_id = el.get("id", "")

            for pattern in self._remove_patterns:
                if any(pattern.search(cls) for cls in classes):
                    to_remove.append(el)
                    break
                if el_id and pattern.search(el_id):
                    to_remove.append(el)
                    break

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

    def _find_main_content(self, soup: BeautifulSoup) -> Tag:
        """Find main content area using semantic HTML and heuristics."""
        for selector in [
            lambda: soup.find("main"),
            lambda: soup.find("article"),
            lambda: soup.find(role="main"),
        ]:
            result = selector()
            if result:
                return result

        # Try content indicators in class/id
        for pattern in self._content_patterns:
            for el in soup.find_all(True):
                if not isinstance(el, Tag):
                    continue
                classes = el.get("class", [])
                if isinstance(classes, str):
                    classes = [classes]
                el_id = el.get("id", "")
                if any(pattern.search(cls) for cls in classes):
                    return el
                if el_id and pattern.search(el_id):
                    return el

        return soup.body or soup
