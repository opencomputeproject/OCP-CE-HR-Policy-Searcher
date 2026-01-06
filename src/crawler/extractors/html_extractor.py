"""HTML content extraction."""

from typing import Optional
from bs4 import BeautifulSoup
from langdetect import detect, LangDetectException

from ...models.crawl import ExtractedContent


class HtmlExtractor:
    REMOVE_TAGS = ["nav", "footer", "header", "aside", "script", "style", "noscript"]

    def extract(self, html: str, url: str) -> ExtractedContent:
        soup = BeautifulSoup(html, "lxml")

        # Remove unwanted tags
        for tag in self.REMOVE_TAGS:
            for el in soup.find_all(tag):
                el.decompose()

        # Find main content
        main = (
            soup.find("main") or
            soup.find("article") or
            soup.find(role="main") or
            soup.body or
            soup
        )

        # Extract text
        text = main.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        text = "\n".join(lines)

        # Extract title
        title = None
        if soup.title:
            title = soup.title.string
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)

        # Detect language
        language = self._detect_language(soup, text)

        return ExtractedContent(
            text=text,
            title=title,
            language=language,
            word_count=len(text.split()),
        )

    def _detect_language(self, soup: BeautifulSoup, text: str) -> Optional[str]:
        if soup.html and soup.html.get("lang"):
            return soup.html.get("lang")[:2]
        if len(text) > 50:
            try:
                return detect(text)
            except LangDetectException:
                pass
        return None
