"""HTML content extraction with boilerplate removal.

This module provides enhanced HTML content extraction for cleaner LLM input.
It removes navigation, boilerplate, cookie notices, and other irrelevant content.

Features:
- Removes structural tags (nav, footer, header, aside, script, style)
- Removes boilerplate by class/id patterns (cookie banners, social widgets, ads)
- Finds main content using semantic HTML (main, article, role="main")
- Tracks extraction statistics for diagnostics
- Configurable via config/content_extraction.yaml
"""

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
from langdetect import detect, LangDetectException

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from ...models.crawl import ExtractedContent


@dataclass
class ExtractionConfig:
    """Configuration for content extraction."""

    # Tags to completely remove
    remove_tags: list[str] = field(default_factory=lambda: [
        "nav", "footer", "header", "aside", "script", "style", "noscript",
        "iframe", "svg", "canvas", "video", "audio", "map", "object", "embed",
    ])

    # Class/ID patterns to remove (case-insensitive regex)
    remove_patterns: list[str] = field(default_factory=lambda: [
        # Cookie/consent banners
        r"cookie", r"consent", r"gdpr", r"privacy-banner", r"cc-banner",
        # Navigation and menus
        r"nav", r"menu", r"breadcrumb", r"pagination", r"sidebar",
        # Social media
        r"social", r"share", r"twitter", r"facebook", r"linkedin",
        # Ads and promotions
        r"ad-", r"ads-", r"advert", r"banner", r"promo", r"sponsor",
        # Comments
        r"comment", r"disqus", r"discuss",
        # Footer elements
        r"footer", r"copyright", r"legal",
        # Other boilerplate
        r"newsletter", r"subscribe", r"signup", r"login", r"search-form",
        r"related-posts", r"recommended", r"popular", r"trending",
    ])

    # Content indicators - prioritize elements with these
    content_indicators: list[str] = field(default_factory=lambda: [
        r"content", r"article", r"main", r"post", r"entry", r"text",
        r"body-content", r"page-content", r"story",
    ])

    # Minimum content length (chars) to consider valid
    min_content_length: int = 100

    # Maximum content length to return (chars) - 0 for unlimited
    max_content_length: int = 0


@dataclass
class ExtractionStats:
    """Statistics from content extraction."""

    original_length: int = 0
    extracted_length: int = 0
    tags_removed: int = 0
    elements_by_pattern_removed: int = 0
    compression_ratio: float = 0.0

    def compute_ratio(self):
        if self.original_length > 0:
            self.compression_ratio = 1 - (self.extracted_length / self.original_length)


class HtmlExtractor:
    """Enhanced HTML content extractor with boilerplate removal."""

    # Default tags to always remove
    REMOVE_TAGS = ["nav", "footer", "header", "aside", "script", "style", "noscript"]

    def __init__(self, config: Optional[ExtractionConfig] = None):
        """Initialize extractor with optional configuration.

        Args:
            config: Extraction configuration. If None, uses defaults.
        """
        self.config = config or ExtractionConfig()
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config.remove_patterns
        ]
        self._content_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config.content_indicators
        ]
        self.stats = ExtractionStats()

    def extract(self, html: str, url: str) -> ExtractedContent:
        """Extract main content from HTML.

        Args:
            html: Raw HTML string
            url: Source URL (for context)

        Returns:
            ExtractedContent with cleaned text, title, language
        """
        # Reset stats
        self.stats = ExtractionStats()
        self.stats.original_length = len(html)

        soup = BeautifulSoup(html, "lxml")

        # Phase 1: Remove structural tags
        tags_removed = self._remove_tags(soup)
        self.stats.tags_removed = tags_removed

        # Phase 2: Remove elements by class/id patterns
        patterns_removed = self._remove_by_patterns(soup)
        self.stats.elements_by_pattern_removed = patterns_removed

        # Phase 3: Find main content area
        main = self._find_main_content(soup)

        # Phase 4: Extract text
        text = main.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        # Apply max length if configured
        if self.config.max_content_length > 0:
            text = text[:self.config.max_content_length]

        self.stats.extracted_length = len(text)
        self.stats.compute_ratio()

        # Extract title
        title = self._extract_title(soup)

        # Detect language
        language = self._detect_language(soup, text)

        return ExtractedContent(
            text=text,
            title=title,
            language=language,
            word_count=len(text.split()),
        )

    def _remove_tags(self, soup: BeautifulSoup) -> int:
        """Remove configured structural tags."""
        count = 0
        for tag in self.config.remove_tags:
            for el in soup.find_all(tag):
                el.decompose()
                count += 1
        return count

    def _remove_by_patterns(self, soup: BeautifulSoup) -> int:
        """Remove elements matching class/id patterns."""
        # Collect elements to remove first (can't modify while iterating)
        to_remove = []

        # Find all elements with class or id attributes
        for el in soup.find_all(True):
            if not isinstance(el, Tag):
                continue

            # Check class attribute
            classes = el.get("class", [])
            if isinstance(classes, str):
                classes = [classes]

            # Check id attribute
            el_id = el.get("id", "")

            # Check if any class or id matches removal patterns
            should_remove = False
            for pattern in self._compiled_patterns:
                for cls in classes:
                    if pattern.search(cls):
                        should_remove = True
                        break
                if el_id and pattern.search(el_id):
                    should_remove = True
                if should_remove:
                    break

            if should_remove:
                to_remove.append(el)

        # Now decompose collected elements
        for el in to_remove:
            el.decompose()

        return len(to_remove)

    def _find_main_content(self, soup: BeautifulSoup) -> Tag:
        """Find the main content area using semantic HTML and heuristics."""
        # Try semantic HTML first
        main = soup.find("main")
        if main:
            return main

        main = soup.find("article")
        if main:
            return main

        main = soup.find(role="main")
        if main:
            return main

        # Try content indicators in class/id
        for pattern in self._content_patterns:
            for el in soup.find_all(True):
                if not isinstance(el, Tag):
                    continue
                classes = el.get("class", [])
                if isinstance(classes, str):
                    classes = [classes]
                el_id = el.get("id", "")

                for cls in classes:
                    if pattern.search(cls):
                        return el
                if el_id and pattern.search(el_id):
                    return el

        # Fall back to body
        return soup.body or soup

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract page title."""
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return None

    def _detect_language(self, soup: BeautifulSoup, text: str) -> Optional[str]:
        """Detect page language."""
        if soup.html and soup.html.get("lang"):
            return soup.html.get("lang")[:2]
        if len(text) > 50:
            try:
                return detect(text)
            except LangDetectException:
                pass
        return None

    def get_stats(self) -> ExtractionStats:
        """Get extraction statistics from last extraction."""
        return self.stats

    def format_stats(self) -> str:
        """Format extraction statistics as string."""
        s = self.stats
        return (
            f"Extraction: {s.original_length} -> {s.extracted_length} chars "
            f"({s.compression_ratio:.1%} reduction), "
            f"{s.tags_removed} tags, {s.elements_by_pattern_removed} patterns removed"
        )


def load_extraction_config(config_path: Optional[Path] = None) -> ExtractionConfig:
    """Load extraction configuration from YAML file.

    Args:
        config_path: Path to config file. Defaults to config/content_extraction.yaml

    Returns:
        ExtractionConfig (default config if file doesn't exist)
    """
    if config_path is None:
        config_path = Path("config/content_extraction.yaml")

    if not config_path.exists():
        return ExtractionConfig()

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        extraction = data.get("content_extraction", {})

        # Get defaults from a fresh instance
        defaults = ExtractionConfig()

        return ExtractionConfig(
            remove_tags=extraction.get("remove_tags", defaults.remove_tags),
            remove_patterns=extraction.get("remove_patterns", defaults.remove_patterns),
            content_indicators=extraction.get("content_indicators", defaults.content_indicators),
            min_content_length=extraction.get("min_content_length", defaults.min_content_length),
            max_content_length=extraction.get("max_content_length", defaults.max_content_length),
        )
    except Exception as e:
        print(f"Warning: Failed to load content extraction config: {e}")
        return ExtractionConfig()
