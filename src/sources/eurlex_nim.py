"""EUR-Lex national implementing measures (NIM) structured policy source.

For each EU directive listed in config/directives.yaml, scrapes EUR-Lex's
national-transposition-measures page and emits CrawlResults only for
measures not seen in a prior run. A small seen-set file (data/nim_seen.json
by default) tracks which country+measure pairs, per directive (CELEX
number), have already been emitted — this source is a change-detector,
not a full re-list on every run.
"""

import hashlib
import json
import logging
from pathlib import Path
from urllib.parse import urljoin

import httpx
import yaml
from bs4 import BeautifulSoup

from ..core.models import CrawlResult, PageStatus
from . import register_source
from ._common import build_client, fetch_document_text
from .base import PolicySource, SourceError

logger = logging.getLogger(__name__)

DEFAULT_MAX_DOCUMENTS = 25
NIM_URL = "https://eur-lex.europa.eu/legal-content/EN/NIM/?uri=CELEX:{celex}"


def _load_directives(config_dir: str) -> list[dict]:
    path = Path(config_dir) / "directives.yaml"
    if not path.exists():
        raise SourceError(f"Missing directives config: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise SourceError(f"Invalid YAML in {path}: {e}") from e
    directives = data.get("directives")
    if not isinstance(directives, list):
        raise SourceError(f"{path} must define a 'directives' list")
    return directives


def _measure_key(country: str, title: str) -> str:
    return hashlib.sha256(f"{country}|{title}".encode("utf-8")).hexdigest()


class _SeenStore:
    """Per-directive seen-measure keys, persisted with an atomic write."""

    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "nim_seen.json"
        self._seen: dict[str, list[str]] = self._load()

    def _load(self) -> dict[str, list[str]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s", self.path, e)
            return {}

    def is_seen(self, celex: str, key: str) -> bool:
        return key in self._seen.get(celex, [])

    def mark_seen(self, celex: str, key: str) -> None:
        self._seen.setdefault(celex, []).append(key)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._seen, indent=2), encoding="utf-8")
        tmp.replace(self.path)


@register_source
class EURLexNIMSource(PolicySource):
    """Detects new national transposition measures for tracked EU directives."""

    id = "eurlex_nim"

    async def fetch(self, domain: dict) -> list[CrawlResult]:
        params = domain.get("source_params", {})
        max_documents = params.get("max_documents", DEFAULT_MAX_DOCUMENTS)
        data_dir = params.get("data_dir", "data")
        config_dir = params.get("config_dir", "config")

        directives = _load_directives(config_dir)
        seen_store = _SeenStore(data_dir)

        results: list[CrawlResult] = []
        seen_urls: set[str] = set()
        newly_seen: list[tuple[str, str]] = []

        async with build_client() as client:
            for directive in directives:
                if len(results) >= max_documents:
                    break
                celex = directive.get("celex") if isinstance(directive, dict) else None
                if not celex:
                    continue
                measures = await self._fetch_measures(client, celex)
                for country, title, link in measures:
                    if len(results) >= max_documents:
                        break
                    key = _measure_key(country, title)
                    if seen_store.is_seen(celex, key) or link in seen_urls:
                        continue
                    seen_urls.add(link)

                    content, content_type = await fetch_document_text(client, link)
                    if not content:
                        content, content_type = f"{country}: {title}", "text/plain"

                    results.append(CrawlResult(
                        url=link,
                        status=PageStatus.SUCCESS,
                        content=content,
                        content_type=content_type,
                        title=f"{country}: {title}",
                        lifecycle_stage="transposition_notified",
                    ))
                    newly_seen.append((celex, key))

        for celex, key in newly_seen:
            seen_store.mark_seen(celex, key)
        if newly_seen:
            seen_store.save()

        return results

    async def _fetch_measures(
        self, client: httpx.AsyncClient, celex: str
    ) -> list[tuple[str, str, str]]:
        url = NIM_URL.format(celex=celex)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("EUR-Lex NIM fetch failed for %s: %s", celex, e)
            return []

        try:
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.warning("Failed to parse EUR-Lex NIM page for %s: %s", celex, e)
            return []

        measures: list[tuple[str, str, str]] = []
        current_country = ""
        for el in soup.find_all(["h2", "h3", "tr", "li"]):
            if el.name in ("h2", "h3"):
                heading_text = el.get_text(strip=True)
                if heading_text:
                    current_country = heading_text
                continue
            link_tag = el.find("a", href=True)
            if not link_tag or not current_country:
                continue
            title = link_tag.get_text(strip=True)
            if not title:
                continue
            href = urljoin(url, link_tag["href"])
            measures.append((current_country, title, href))
        return measures
