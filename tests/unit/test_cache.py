"""Tests for URLCache, CacheEntry, CacheStats, and compute_content_hash."""

from datetime import datetime, timezone, timedelta

import pytest

from src.core.cache import CacheEntry, CacheStats, URLCache, compute_content_hash


# --- CacheEntry ---

class TestCacheEntry:
    def test_not_expired_with_future_date(self):
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        entry = CacheEntry(url="https://a.gov", is_relevant=True, expires_date=future)
        assert not entry.is_expired()

    def test_expired_with_past_date(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        entry = CacheEntry(url="https://a.gov", is_relevant=True, expires_date=past)
        assert entry.is_expired()

    def test_expired_when_no_expiry(self):
        entry = CacheEntry(url="https://a.gov", is_relevant=True)
        assert entry.is_expired()

    def test_expired_with_bad_date(self):
        entry = CacheEntry(url="https://a.gov", is_relevant=True, expires_date="not-a-date")
        assert entry.is_expired()

    def test_matches_content_same_hash(self):
        entry = CacheEntry(url="https://a.gov", is_relevant=True, content_hash="abc123")
        assert entry.matches_content("abc123")

    def test_no_match_different_hash(self):
        entry = CacheEntry(url="https://a.gov", is_relevant=True, content_hash="abc123")
        assert not entry.matches_content("def456")

    def test_no_match_empty_hash(self):
        entry = CacheEntry(url="https://a.gov", is_relevant=True, content_hash="")
        assert not entry.matches_content("abc123")

    def test_no_match_when_both_empty(self):
        entry = CacheEntry(url="https://a.gov", is_relevant=True)
        assert not entry.matches_content("")


# --- CacheStats ---

class TestCacheStats:
    def test_hit_rate_with_hits(self):
        stats = CacheStats(hits=3, misses=7)
        assert stats.hit_rate == pytest.approx(0.3)

    def test_hit_rate_zero_total(self):
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_reset_session(self):
        stats = CacheStats(total_entries=10, hits=5, misses=3, expired=1, content_changed=1)
        stats.reset_session()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.expired == 0
        assert stats.content_changed == 0
        assert stats.total_entries == 10  # not reset


# --- URLCache ---

class TestURLCache:
    def test_set_and_get(self):
        cache = URLCache(expiry_days=30)
        cache.set("https://a.gov/p1", is_relevant=True, relevance_score=8)
        entry = cache.get("https://a.gov/p1")
        assert entry is not None
        assert entry.is_relevant is True
        assert entry.relevance_score == 8

    def test_get_missing_url(self):
        cache = URLCache()
        assert cache.get("https://missing.gov") is None
        assert cache.stats.misses == 1

    def test_get_expired_entry(self):
        cache = URLCache(expiry_days=0)
        # Manually insert an already-expired entry
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        cache._entries["https://a.gov"] = CacheEntry(
            url="https://a.gov", is_relevant=True, expires_date=past,
        )
        assert cache.get("https://a.gov") is None
        assert cache.stats.expired == 1

    def test_get_content_changed(self):
        cache = URLCache()
        cache.set("https://a.gov", is_relevant=True, content_hash="old")
        entry = cache.get("https://a.gov", content_hash="new")
        assert entry is None
        assert cache.stats.content_changed == 1

    def test_get_content_matches(self):
        cache = URLCache()
        cache.set("https://a.gov", is_relevant=True, content_hash="same")
        entry = cache.get("https://a.gov", content_hash="same")
        assert entry is not None
        assert cache.stats.hits == 1

    def test_contains(self):
        cache = URLCache()
        cache.set("https://a.gov", is_relevant=True)
        assert cache.contains("https://a.gov")
        assert not cache.contains("https://b.gov")

    def test_clean_expired(self):
        cache = URLCache()
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        cache._entries["expired"] = CacheEntry(
            url="expired", is_relevant=True, expires_date=past,
        )
        cache.set("valid", is_relevant=True)
        removed = cache.clean_expired()
        assert removed == 1
        assert not cache.contains("expired")
        assert cache.contains("valid")

    def test_stats_total_entries(self):
        cache = URLCache()
        cache.set("https://a.gov", is_relevant=True)
        cache.set("https://b.gov", is_relevant=False)
        assert cache.stats.total_entries == 2

    def test_save_and_load(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        cache = URLCache(expiry_days=30, cache_path=cache_path)
        cache.set("https://a.gov", is_relevant=True, relevance_score=9, content_hash="h1")
        cache.set("https://b.gov", is_relevant=False, relevance_score=2, content_hash="h2")
        assert cache.save()

        loaded = URLCache.load(cache_path)
        assert loaded.contains("https://a.gov")
        assert loaded.contains("https://b.gov")
        entry = loaded.get("https://a.gov", content_hash="h1")
        assert entry is not None
        assert entry.relevance_score == 9

    def test_load_nonexistent_file(self, tmp_path):
        cache = URLCache.load(tmp_path / "nope.json")
        assert cache.stats.total_entries == 0

    def test_load_corrupt_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("NOT JSON", encoding="utf-8")
        cache = URLCache.load(bad_file)
        assert cache.stats.total_entries == 0

    def test_load_corrupt_json_logs_error(self, tmp_path, caplog):
        """Corrupt cache should log at ERROR level with context."""
        import logging
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{INVALID", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="src.core.cache"):
            URLCache.load(bad_file)
        assert any("corrupted" in r.message.lower() for r in caplog.records)
        assert any("performance impact" in r.message.lower() for r in caplog.records)

    def test_load_generic_error_logs_at_error_level(self, tmp_path, caplog, monkeypatch):
        """Non-JSON errors during cache load should log at ERROR level."""
        import logging
        cache_file = tmp_path / "cache.json"
        cache_file.write_text('{"entries": {}}', encoding="utf-8")
        # Make json.load raise a non-JSON error
        import json as json_mod
        original_load = json_mod.load
        def broken_load(f):
            raise PermissionError("Access denied")
        monkeypatch.setattr(json_mod, "load", broken_load)
        with caplog.at_level(logging.ERROR, logger="src.core.cache"):
            cache = URLCache.load(cache_file)
        assert cache.stats.total_entries == 0
        assert any("failed to load cache" in r.message.lower() for r in caplog.records)

    def test_save_creates_parent_dir(self, tmp_path):
        cache_path = tmp_path / "sub" / "dir" / "cache.json"
        cache = URLCache(cache_path=cache_path)
        cache.set("https://a.gov", is_relevant=True)
        assert cache.save()
        assert cache_path.exists()


# --- compute_content_hash ---

class TestComputeContentHash:
    def test_same_content_same_hash(self):
        h1 = compute_content_hash("hello world")
        h2 = compute_content_hash("hello world")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("world")
        assert h1 != h2

    def test_truncated_to_16_chars(self):
        h = compute_content_hash("some content")
        assert len(h) == 16

    def test_empty_content(self):
        h = compute_content_hash("")
        assert isinstance(h, str)
        assert len(h) == 16

    def test_long_content_uses_first_10k(self):
        long_content = "x" * 20000
        h1 = compute_content_hash(long_content)
        # Same first 10k chars → same hash
        h2 = compute_content_hash("x" * 10000)
        assert h1 == h2
