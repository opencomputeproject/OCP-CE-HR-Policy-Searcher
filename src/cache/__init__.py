"""URL result caching for avoiding redundant LLM analysis."""

from .url_cache import URLCache, CacheEntry, CacheStats, load_cache, save_cache

__all__ = ["URLCache", "CacheEntry", "CacheStats", "load_cache", "save_cache"]
