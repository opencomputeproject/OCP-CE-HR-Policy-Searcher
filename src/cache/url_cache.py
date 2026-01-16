"""URL result caching for avoiding redundant LLM analysis.

This module provides caching of URL analysis results to:
- Skip re-analyzing URLs that have already been analyzed
- Reduce LLM API costs on repeated runs
- Track cache statistics for monitoring

Cache entries expire after a configurable number of days (default: 30).
The cache stores whether a URL was relevant and its relevance score,
along with a content hash to detect if the page has changed.

Usage:
    cache = URLCache()  # Loads from default location

    # Check if URL is cached and still valid
    entry = cache.get(url)
    if entry and not entry.is_expired():
        # Use cached result
        is_relevant = entry.is_relevant
    else:
        # Analyze and cache
        result = analyze(url)
        cache.set(url, result.is_relevant, result.relevance_score, content_hash)

    # Save cache to disk
    save_cache(cache)
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class CacheEntry:
    """A cached analysis result for a URL."""

    url: str
    is_relevant: bool
    relevance_score: int = 0
    content_hash: str = ""
    analyzed_date: str = ""
    expires_date: str = ""
    policy_type: str = ""  # Store policy type if relevant

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        if not self.expires_date:
            return True
        try:
            expires = datetime.fromisoformat(self.expires_date)
            now = datetime.now(timezone.utc)
            return now >= expires
        except (ValueError, TypeError):
            return True

    def matches_content(self, content_hash: str) -> bool:
        """Check if content hash matches (page hasn't changed)."""
        if not self.content_hash or not content_hash:
            return False
        return self.content_hash == content_hash

    @classmethod
    def from_dict(cls, data: dict) -> "CacheEntry":
        """Create from dictionary."""
        return cls(
            url=data.get("url", ""),
            is_relevant=data.get("is_relevant", False),
            relevance_score=data.get("relevance_score", 0),
            content_hash=data.get("content_hash", ""),
            analyzed_date=data.get("analyzed_date", ""),
            expires_date=data.get("expires_date", ""),
            policy_type=data.get("policy_type", ""),
        )


@dataclass
class CacheStats:
    """Statistics about cache usage."""

    total_entries: int = 0
    hits: int = 0
    misses: int = 0
    expired: int = 0
    content_changed: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def reset_session(self):
        """Reset session counters (not total_entries)."""
        self.hits = 0
        self.misses = 0
        self.expired = 0
        self.content_changed = 0

    def format(self) -> str:
        """Format stats as string."""
        return (
            f"Cache: {self.total_entries} entries, "
            f"{self.hits} hits, {self.misses} misses "
            f"({self.hit_rate:.1%} hit rate)"
        )


class URLCache:
    """Cache for URL analysis results."""

    DEFAULT_EXPIRY_DAYS = 30
    DEFAULT_CACHE_PATH = Path("data/url_cache.json")

    def __init__(
        self,
        expiry_days: int = DEFAULT_EXPIRY_DAYS,
        cache_path: Optional[Path] = None,
    ):
        """Initialize cache.

        Args:
            expiry_days: Days until cache entries expire
            cache_path: Path to cache file (default: data/url_cache.json)
        """
        self.expiry_days = expiry_days
        self.cache_path = cache_path or self.DEFAULT_CACHE_PATH
        self._entries: dict[str, CacheEntry] = {}
        self.stats = CacheStats()

    def get(self, url: str, content_hash: str = "") -> Optional[CacheEntry]:
        """Get cached entry for URL.

        Args:
            url: URL to look up
            content_hash: Optional hash of current content (for change detection)

        Returns:
            CacheEntry if found and valid, None otherwise
        """
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
        """Set cached entry for URL.

        Args:
            url: URL to cache
            is_relevant: Whether URL was relevant
            relevance_score: Relevance score (0-10)
            content_hash: Hash of content for change detection
            policy_type: Policy type if relevant

        Returns:
            Created CacheEntry
        """
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
        return entry

    def remove(self, url: str) -> bool:
        """Remove entry from cache.

        Args:
            url: URL to remove

        Returns:
            True if entry was removed, False if not found
        """
        if url in self._entries:
            del self._entries[url]
            self.stats.total_entries = len(self._entries)
            return True
        return False

    def clear(self):
        """Clear all cache entries."""
        self._entries.clear()
        self.stats = CacheStats()

    def clean_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed
        """
        expired_urls = [
            url for url, entry in self._entries.items() if entry.is_expired()
        ]
        for url in expired_urls:
            del self._entries[url]

        self.stats.total_entries = len(self._entries)
        return len(expired_urls)

    def contains(self, url: str) -> bool:
        """Check if URL is in cache (doesn't count as hit/miss)."""
        return url in self._entries

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        self.stats.total_entries = len(self._entries)
        return self.stats

    def to_dict(self) -> dict:
        """Convert cache to dictionary for serialization."""
        return {
            "expiry_days": self.expiry_days,
            "entries": {url: asdict(entry) for url, entry in self._entries.items()},
            "metadata": {
                "version": 1,
                "last_saved": datetime.now(timezone.utc).isoformat(),
                "total_entries": len(self._entries),
            },
        }

    @classmethod
    def from_dict(cls, data: dict, cache_path: Optional[Path] = None) -> "URLCache":
        """Create cache from dictionary."""
        expiry_days = data.get("expiry_days", cls.DEFAULT_EXPIRY_DAYS)
        cache = cls(expiry_days=expiry_days, cache_path=cache_path)

        entries = data.get("entries", {})
        for url, entry_data in entries.items():
            cache._entries[url] = CacheEntry.from_dict(entry_data)

        cache.stats.total_entries = len(cache._entries)
        return cache


def compute_content_hash(content: str) -> str:
    """Compute hash of content for change detection.

    Uses first 10000 chars to avoid hashing huge pages.
    """
    # Use first 10000 chars (enough to detect significant changes)
    content_sample = content[:10000] if content else ""
    return hashlib.sha256(content_sample.encode("utf-8")).hexdigest()[:16]


def load_cache(cache_path: Optional[Path] = None) -> URLCache:
    """Load cache from disk.

    Args:
        cache_path: Path to cache file

    Returns:
        URLCache (empty cache if file doesn't exist)
    """
    path = cache_path or URLCache.DEFAULT_CACHE_PATH

    if not path.exists():
        return URLCache(cache_path=path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return URLCache.from_dict(data, cache_path=path)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Warning: Failed to load cache: {e}")
        return URLCache(cache_path=path)


def save_cache(cache: URLCache, cache_path: Optional[Path] = None) -> bool:
    """Save cache to disk.

    Args:
        cache: URLCache to save
        cache_path: Path to save to (uses cache's path if not specified)

    Returns:
        True if saved successfully, False otherwise
    """
    path = cache_path or cache.cache_path

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache.to_dict(), f, indent=2)
        return True
    except (IOError, TypeError) as e:
        print(f"Warning: Failed to save cache: {e}")
        return False
