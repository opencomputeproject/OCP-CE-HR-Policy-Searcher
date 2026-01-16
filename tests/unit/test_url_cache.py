"""Unit tests for URL result caching (Phase 5)."""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.cache.url_cache import (
    URLCache,
    CacheEntry,
    CacheStats,
    compute_content_hash,
    load_cache,
    save_cache,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_not_expired(self):
        """Entry with future expiry is not expired."""
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        entry = CacheEntry(url="https://example.com", is_relevant=True, expires_date=future)
        assert not entry.is_expired()

    def test_expired(self):
        """Entry with past expiry is expired."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        entry = CacheEntry(url="https://example.com", is_relevant=True, expires_date=past)
        assert entry.is_expired()

    def test_empty_expiry_is_expired(self):
        """Entry with empty expiry is considered expired."""
        entry = CacheEntry(url="https://example.com", is_relevant=True, expires_date="")
        assert entry.is_expired()

    def test_invalid_expiry_is_expired(self):
        """Entry with invalid expiry is considered expired."""
        entry = CacheEntry(url="https://example.com", is_relevant=True, expires_date="invalid")
        assert entry.is_expired()

    def test_matches_content(self):
        """Content hash matching works."""
        entry = CacheEntry(
            url="https://example.com",
            is_relevant=True,
            content_hash="abc123",
        )
        assert entry.matches_content("abc123")
        assert not entry.matches_content("different")

    def test_empty_hash_no_match(self):
        """Empty hash doesn't match."""
        entry = CacheEntry(url="https://example.com", is_relevant=True, content_hash="")
        assert not entry.matches_content("abc123")
        assert not entry.matches_content("")

    def test_from_dict(self):
        """Create entry from dictionary."""
        data = {
            "url": "https://example.com",
            "is_relevant": True,
            "relevance_score": 8,
            "content_hash": "abc123",
            "policy_type": "regulation",
        }
        entry = CacheEntry.from_dict(data)
        assert entry.url == "https://example.com"
        assert entry.is_relevant is True
        assert entry.relevance_score == 8
        assert entry.content_hash == "abc123"
        assert entry.policy_type == "regulation"

    def test_from_dict_defaults(self):
        """Missing fields get defaults."""
        entry = CacheEntry.from_dict({})
        assert entry.url == ""
        assert entry.is_relevant is False
        assert entry.relevance_score == 0


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_initial_values(self):
        """Stats start at zero."""
        stats = CacheStats()
        assert stats.total_entries == 0
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0

    def test_hit_rate(self):
        """Hit rate is calculated correctly."""
        stats = CacheStats(hits=75, misses=25)
        assert stats.hit_rate == 0.75

    def test_hit_rate_no_lookups(self):
        """Zero lookups gives 0% hit rate (not division error)."""
        stats = CacheStats(hits=0, misses=0)
        assert stats.hit_rate == 0.0

    def test_reset_session(self):
        """Session counters reset but total_entries preserved."""
        stats = CacheStats(total_entries=100, hits=50, misses=20, expired=5)
        stats.reset_session()
        assert stats.total_entries == 100
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.expired == 0

    def test_format(self):
        """Stats format correctly."""
        stats = CacheStats(total_entries=100, hits=80, misses=20)
        formatted = stats.format()
        assert "100 entries" in formatted
        assert "80 hits" in formatted
        assert "20 misses" in formatted
        assert "80.0%" in formatted


class TestURLCache:
    """Tests for URLCache class."""

    @pytest.fixture
    def cache(self):
        """Create empty cache."""
        return URLCache(expiry_days=30)

    def test_set_and_get(self, cache):
        """Set and get entry."""
        cache.set("https://example.com", is_relevant=True, relevance_score=8)
        entry = cache.get("https://example.com")
        assert entry is not None
        assert entry.is_relevant is True
        assert entry.relevance_score == 8

    def test_get_miss(self, cache):
        """Get returns None for unknown URL."""
        entry = cache.get("https://unknown.com")
        assert entry is None
        assert cache.stats.misses == 1

    def test_get_hit(self, cache):
        """Get counts as hit."""
        cache.set("https://example.com", is_relevant=True)
        cache.get("https://example.com")
        assert cache.stats.hits == 1

    def test_get_expired(self, cache):
        """Expired entries return None."""
        cache.set("https://example.com", is_relevant=True)
        # Manually expire the entry
        entry = cache._entries["https://example.com"]
        entry.expires_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        result = cache.get("https://example.com")
        assert result is None
        assert cache.stats.expired == 1

    def test_get_content_changed(self, cache):
        """Changed content returns None."""
        cache.set("https://example.com", is_relevant=True, content_hash="old_hash")
        result = cache.get("https://example.com", content_hash="new_hash")
        assert result is None
        assert cache.stats.content_changed == 1

    def test_get_content_matches(self, cache):
        """Same content hash returns entry."""
        cache.set("https://example.com", is_relevant=True, content_hash="same_hash")
        result = cache.get("https://example.com", content_hash="same_hash")
        assert result is not None
        assert cache.stats.hits == 1

    def test_remove_existing(self, cache):
        """Remove existing entry."""
        cache.set("https://example.com", is_relevant=True)
        result = cache.remove("https://example.com")
        assert result is True
        assert cache.get("https://example.com") is None

    def test_remove_nonexistent(self, cache):
        """Remove nonexistent entry returns False."""
        result = cache.remove("https://unknown.com")
        assert result is False

    def test_clear(self, cache):
        """Clear removes all entries."""
        cache.set("https://example1.com", is_relevant=True)
        cache.set("https://example2.com", is_relevant=False)
        cache.clear()
        assert len(cache._entries) == 0
        assert cache.stats.total_entries == 0

    def test_clean_expired(self, cache):
        """Clean removes expired entries."""
        cache.set("https://valid.com", is_relevant=True)
        cache.set("https://expired.com", is_relevant=False)
        # Manually expire one entry
        cache._entries["https://expired.com"].expires_date = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).isoformat()

        removed = cache.clean_expired()
        assert removed == 1
        assert cache.contains("https://valid.com")
        assert not cache.contains("https://expired.com")

    def test_contains(self, cache):
        """Contains checks existence without counting."""
        cache.set("https://example.com", is_relevant=True)
        assert cache.contains("https://example.com")
        assert not cache.contains("https://unknown.com")
        # Should not affect stats
        assert cache.stats.hits == 0
        assert cache.stats.misses == 0

    def test_expiry_days_applied(self, cache):
        """Expiry days are applied to new entries."""
        cache.set("https://example.com", is_relevant=True)
        entry = cache._entries["https://example.com"]
        expires = datetime.fromisoformat(entry.expires_date)
        analyzed = datetime.fromisoformat(entry.analyzed_date)
        diff = expires - analyzed
        assert diff.days == 30

    def test_to_dict(self, cache):
        """Convert cache to dictionary."""
        cache.set("https://example.com", is_relevant=True, relevance_score=8)
        data = cache.to_dict()
        assert data["expiry_days"] == 30
        assert "https://example.com" in data["entries"]
        assert data["metadata"]["version"] == 1
        assert data["metadata"]["total_entries"] == 1

    def test_from_dict(self):
        """Create cache from dictionary."""
        data = {
            "expiry_days": 60,
            "entries": {
                "https://example.com": {
                    "url": "https://example.com",
                    "is_relevant": True,
                    "relevance_score": 8,
                    "content_hash": "abc",
                    "analyzed_date": "2026-01-01T00:00:00+00:00",
                    "expires_date": "2026-03-01T00:00:00+00:00",
                    "policy_type": "regulation",
                }
            },
        }
        cache = URLCache.from_dict(data)
        assert cache.expiry_days == 60
        assert cache.contains("https://example.com")
        entry = cache._entries["https://example.com"]
        assert entry.relevance_score == 8


class TestComputeContentHash:
    """Tests for content hash function."""

    def test_same_content_same_hash(self):
        """Same content produces same hash."""
        content = "Some policy content about data centers"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        """Different content produces different hash."""
        hash1 = compute_content_hash("Content A")
        hash2 = compute_content_hash("Content B")
        assert hash1 != hash2

    def test_empty_content(self):
        """Empty content doesn't crash."""
        hash_val = compute_content_hash("")
        assert hash_val is not None
        assert len(hash_val) == 16

    def test_long_content_truncated(self):
        """Long content is truncated for hashing."""
        short = "x" * 10000
        long_content = "x" * 20000
        # Both should hash the same (first 10000 chars)
        hash_short = compute_content_hash(short)
        hash_long = compute_content_hash(long_content)
        assert hash_short == hash_long

    def test_hash_length(self):
        """Hash is fixed length."""
        hash_val = compute_content_hash("test")
        assert len(hash_val) == 16


class TestLoadSaveCache:
    """Tests for cache persistence."""

    def test_load_missing_file(self):
        """Load from missing file returns empty cache."""
        cache = load_cache(Path("/nonexistent/cache.json"))
        assert len(cache._entries) == 0

    def test_save_and_load(self):
        """Save and load roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_cache.json"

            # Create and save cache
            cache = URLCache(expiry_days=45, cache_path=path)
            cache.set("https://example.com", is_relevant=True, relevance_score=8)
            save_cache(cache)

            # Load and verify
            loaded = load_cache(path)
            assert loaded.expiry_days == 45
            assert loaded.contains("https://example.com")
            entry = loaded._entries["https://example.com"]
            assert entry.relevance_score == 8

    def test_save_creates_directory(self):
        """Save creates directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "cache.json"
            cache = URLCache(cache_path=path)
            cache.set("https://example.com", is_relevant=True)
            result = save_cache(cache)
            assert result is True
            assert path.exists()

    def test_load_invalid_json(self):
        """Load handles invalid JSON gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "invalid.json"
            path.write_text("not valid json {{{")
            cache = load_cache(path)
            assert len(cache._entries) == 0

    def test_load_empty_file(self):
        """Load handles empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.json"
            path.write_text("{}")
            cache = load_cache(path)
            assert len(cache._entries) == 0


class TestCacheIntegration:
    """Integration tests for cache usage patterns."""

    def test_typical_workflow(self):
        """Test typical cache usage workflow."""
        cache = URLCache(expiry_days=30)

        # First visit - miss
        url = "https://gov.example/policy"
        entry = cache.get(url)
        assert entry is None
        assert cache.stats.misses == 1

        # Analyze and cache
        content_hash = compute_content_hash("Policy content here")
        cache.set(url, is_relevant=True, relevance_score=8, content_hash=content_hash)

        # Second visit - hit
        entry = cache.get(url, content_hash=content_hash)
        assert entry is not None
        assert entry.is_relevant is True
        assert cache.stats.hits == 1

        # Third visit with changed content - miss
        new_hash = compute_content_hash("Updated policy content")
        entry = cache.get(url, content_hash=new_hash)
        assert entry is None
        assert cache.stats.content_changed == 1

    def test_batch_caching(self):
        """Test caching multiple URLs."""
        cache = URLCache()

        urls = [
            ("https://example1.com", True, 8),
            ("https://example2.com", False, 2),
            ("https://example3.com", True, 9),
        ]

        # Cache all
        for url, relevant, score in urls:
            cache.set(url, is_relevant=relevant, relevance_score=score)

        # Verify all cached
        assert cache.stats.total_entries == 3
        for url, relevant, score in urls:
            entry = cache.get(url)
            assert entry.is_relevant == relevant
            assert entry.relevance_score == score

    def test_not_relevant_caching(self):
        """Test caching non-relevant results."""
        cache = URLCache()

        # Cache a non-relevant result
        cache.set(
            "https://example.com/login",
            is_relevant=False,
            relevance_score=1,
        )

        entry = cache.get("https://example.com/login")
        assert entry is not None
        assert entry.is_relevant is False
        assert entry.relevance_score == 1

    def test_policy_type_stored(self):
        """Test that policy type is stored."""
        cache = URLCache()
        cache.set(
            "https://gov.example/regulation",
            is_relevant=True,
            relevance_score=9,
            policy_type="regulation",
        )

        entry = cache.get("https://gov.example/regulation")
        assert entry.policy_type == "regulation"
