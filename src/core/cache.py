"""URL result cache with TTL expiry, content-hash change detection, and periodic saves."""

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CacheEntry(BaseModel):
    """A cached analysis result for a URL."""
    url: str
    is_relevant: bool
    relevance_score: int = 0
    content_hash: str = ""
    analyzed_date: str = ""
    expires_date: str = ""
    policy_type: str = ""

    def is_expired(self) -> bool:
        if not self.expires_date:
            return True
        try:
            expires = datetime.fromisoformat(self.expires_date)
            return datetime.now(timezone.utc) >= expires
        except (ValueError, TypeError):
            return True

    def matches_content(self, content_hash: str) -> bool:
        if not self.content_hash or not content_hash:
            return False
        return self.content_hash == content_hash


class CacheStats(BaseModel):
    """Cache usage statistics."""
    total_entries: int = 0
    hits: int = 0
    misses: int = 0
    expired: int = 0
    content_changed: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def reset_session(self):
        self.hits = 0
        self.misses = 0
        self.expired = 0
        self.content_changed = 0


class URLCache:
    """Cache for URL analysis results with TTL and content-hash support."""

    DEFAULT_EXPIRY_DAYS = 30
    DEFAULT_CACHE_PATH = Path("data/url_cache.json")
    SAVE_INTERVAL = 50  # Auto-save every N sets

    def __init__(
        self,
        expiry_days: int = DEFAULT_EXPIRY_DAYS,
        cache_path: Optional[Path] = None,
    ):
        self.expiry_days = expiry_days
        self.cache_path = cache_path or self.DEFAULT_CACHE_PATH
        self._entries: dict[str, CacheEntry] = {}
        self.stats = CacheStats()
        self._sets_since_save = 0

    def get(self, url: str, content_hash: str = "") -> Optional[CacheEntry]:
        """Get cached entry. Returns None if missing, expired, or content changed."""
        entry = self._entries.get(url)

        if entry is None:
            self.stats.misses += 1
            return None

        if entry.is_expired():
            self.stats.expired += 1
            self.stats.misses += 1
            return None

        if content_hash and not entry.matches_content(content_hash):
            self.stats.content_changed += 1
            self.stats.misses += 1
            return None

        self.stats.hits += 1
        return entry

    def set(
        self,
        url: str,
        is_relevant: bool,
        relevance_score: int = 0,
        content_hash: str = "",
        policy_type: str = "",
    ) -> CacheEntry:
        """Cache an analysis result."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self.expiry_days)

        entry = CacheEntry(
            url=url,
            is_relevant=is_relevant,
            relevance_score=relevance_score,
            content_hash=content_hash,
            analyzed_date=now.isoformat(),
            expires_date=expires.isoformat(),
            policy_type=policy_type,
        )

        self._entries[url] = entry
        self.stats.total_entries = len(self._entries)

        # Periodic auto-save
        self._sets_since_save += 1
        if self._sets_since_save >= self.SAVE_INTERVAL:
            self.save()
            self._sets_since_save = 0

        return entry

    def contains(self, url: str) -> bool:
        return url in self._entries

    def clean_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        expired = [url for url, e in self._entries.items() if e.is_expired()]
        for url in expired:
            del self._entries[url]
        self.stats.total_entries = len(self._entries)
        return len(expired)

    def save(self, path: Optional[Path] = None) -> bool:
        """Save cache to disk with atomic write."""
        target = path or self.cache_path
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = {
                "expiry_days": self.expiry_days,
                "entries": {url: e.model_dump() for url, e in self._entries.items()},
                "metadata": {
                    "version": 1,
                    "last_saved": datetime.now(timezone.utc).isoformat(),
                    "total_entries": len(self._entries),
                },
            }
            tmp = target.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp.replace(target)
            return True
        except (IOError, TypeError) as e:
            logger.warning(f"Failed to save cache: {e}")
            return False

    @classmethod
    def load(cls, cache_path: Optional[Path] = None) -> "URLCache":
        """Load cache from disk. Returns empty cache on error."""
        path = cache_path or cls.DEFAULT_CACHE_PATH
        if not path.exists():
            return cls(cache_path=path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            expiry = data.get("expiry_days", cls.DEFAULT_EXPIRY_DAYS)
            cache = cls(expiry_days=expiry, cache_path=path)
            for url, entry_data in data.get("entries", {}).items():
                cache._entries[url] = CacheEntry(**entry_data)
            cache.stats.total_entries = len(cache._entries)
            return cache
        except json.JSONDecodeError as e:
            logger.error(
                "Cache file %s is corrupted (JSON error: %s) — starting fresh. "
                "Previous cache data is lost. This is a performance impact only, "
                "no policy data is affected.",
                path, e,
            )
            return cls(cache_path=path)
        except Exception as e:
            logger.error(
                "Failed to load cache from %s: %s — starting fresh", path, e,
            )
            return cls(cache_path=path)


def compute_content_hash(content: str) -> str:
    """Hash first 10K chars for change detection."""
    sample = content[:10000] if content else ""
    return hashlib.sha256(sample.encode("utf-8")).hexdigest()[:16]
