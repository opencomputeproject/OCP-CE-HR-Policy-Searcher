"""Tests for PolicyStore — JSON file persistence."""

import json

import pytest

from src.core.models import Policy, PolicyType
from src.storage.store import PolicyStore


def _make_policy(url: str = "https://a.gov/p1", **overrides) -> Policy:
    defaults = dict(
        url=url,
        policy_name="Test Policy",
        jurisdiction="US",
        policy_type=PolicyType.LAW,
        summary="A test policy",
        relevance_score=7,
    )
    defaults.update(overrides)
    return Policy(**defaults)


class TestPolicyStoreInit:
    def test_init_creates_empty_list(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        assert store.get_all() == []

    def test_init_loads_existing_file(self, tmp_path):
        policies_file = tmp_path / "policies.json"
        data = [{"url": "https://a.gov", "policy_name": "P1"}]
        policies_file.write_text(json.dumps(data), encoding="utf-8")
        store = PolicyStore(data_dir=str(tmp_path))
        assert len(store.get_all()) == 1

    def test_init_handles_corrupt_json(self, tmp_path):
        policies_file = tmp_path / "policies.json"
        policies_file.write_text("NOT JSON", encoding="utf-8")
        store = PolicyStore(data_dir=str(tmp_path))
        assert store.get_all() == []


class TestAddPolicies:
    def test_add_policies(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        policies = [_make_policy("https://a.gov"), _make_policy("https://b.gov")]
        added = store.add_policies(policies)
        assert added == 2
        assert len(store.get_all()) == 2

    def test_deduplicates_by_url(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        store.add_policies([_make_policy("https://a.gov")])
        added = store.add_policies([_make_policy("https://a.gov")])
        assert added == 0
        assert len(store.get_all()) == 1

    def test_empty_list_returns_zero(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        assert store.add_policies([]) == 0

    def test_persists_to_disk(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        store.add_policies([_make_policy("https://a.gov")])
        # Load fresh from disk
        store2 = PolicyStore(data_dir=str(tmp_path))
        assert len(store2.get_all()) == 1


class TestSearch:
    @pytest.fixture
    def store_with_data(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        store.add_policies([
            _make_policy("https://a.gov", jurisdiction="Germany", policy_type=PolicyType.LAW, relevance_score=9, scan_id="s1"),
            _make_policy("https://b.gov", jurisdiction="France", policy_type=PolicyType.REGULATION, relevance_score=5, scan_id="s1"),
            _make_policy("https://c.gov", jurisdiction="Germany", policy_type=PolicyType.DIRECTIVE, relevance_score=3, scan_id="s2"),
        ])
        return store

    def test_search_by_jurisdiction(self, store_with_data):
        results = store_with_data.search(jurisdiction="Germany")
        assert len(results) == 2

    def test_search_by_policy_type(self, store_with_data):
        results = store_with_data.search(policy_type="regulation")
        assert len(results) == 1

    def test_search_by_min_score(self, store_with_data):
        results = store_with_data.search(min_score=5)
        assert len(results) == 2

    def test_search_by_scan_id(self, store_with_data):
        results = store_with_data.search(scan_id="s2")
        assert len(results) == 1

    def test_search_no_filters(self, store_with_data):
        results = store_with_data.search()
        assert len(results) == 3

    def test_search_combined_filters(self, store_with_data):
        results = store_with_data.search(jurisdiction="Germany", min_score=5)
        assert len(results) == 1


class TestGetStats:
    def test_stats_empty_store(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        stats = store.get_stats()
        assert stats["total"] == 0
        assert stats["flagged_count"] == 0

    def test_stats_with_data(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        store.add_policies([
            _make_policy("https://a.gov", jurisdiction="Germany", relevance_score=9),
            _make_policy("https://b.gov", jurisdiction="France", relevance_score=5),
            _make_policy("https://c.gov", jurisdiction="Germany", relevance_score=2),
        ])
        stats = store.get_stats()
        assert stats["total"] == 3
        assert stats["by_jurisdiction"]["Germany"] == 2
        assert stats["by_jurisdiction"]["France"] == 1
        assert stats["by_score_range"]["9-10"] == 1
        assert stats["by_score_range"]["4-6"] == 1
        assert stats["by_score_range"]["1-3"] == 1


class TestCorruptFileRecovery:
    """Tests for corrupt file backup instead of silent data loss."""

    def test_corrupt_json_creates_backup(self, tmp_path):
        """Corrupt JSON should be renamed to .corrupt, not silently deleted."""
        policies_file = tmp_path / "policies.json"
        policies_file.write_text("{{CORRUPT DATA}}", encoding="utf-8")
        store = PolicyStore(data_dir=str(tmp_path))
        assert store.get_all() == []
        backup = tmp_path / "policies.json.corrupt"
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == "{{CORRUPT DATA}}"

    def test_wrong_type_creates_backup(self, tmp_path):
        """A dict instead of list should be backed up and replaced."""
        policies_file = tmp_path / "policies.json"
        policies_file.write_text('{"not": "a list"}', encoding="utf-8")
        store = PolicyStore(data_dir=str(tmp_path))
        assert store.get_all() == []
        backup = tmp_path / "policies.json.corrupt"
        assert backup.exists()
        assert '"not"' in backup.read_text(encoding="utf-8")

    def test_backup_preserves_original_content(self, tmp_path):
        """Backup file should contain the exact original corrupt content."""
        policies_file = tmp_path / "policies.json"
        original = '[{"url": "partial...  TRUNCATED'
        policies_file.write_text(original, encoding="utf-8")
        PolicyStore(data_dir=str(tmp_path))
        backup = tmp_path / "policies.json.corrupt"
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == original

    def test_store_functional_after_corrupt_recovery(self, tmp_path):
        """After recovering from corruption, store should accept new policies."""
        policies_file = tmp_path / "policies.json"
        policies_file.write_text("NOT JSON", encoding="utf-8")
        store = PolicyStore(data_dir=str(tmp_path))
        added = store.add_policies([_make_policy("https://a.gov")])
        assert added == 1
        # Verify persisted to disk
        store2 = PolicyStore(data_dir=str(tmp_path))
        assert len(store2.get_all()) == 1

    def test_corrupt_logs_error(self, tmp_path, caplog):
        """Corrupt file should produce an error-level log message."""
        policies_file = tmp_path / "policies.json"
        policies_file.write_text("NOT JSON", encoding="utf-8")
        import logging
        with caplog.at_level(logging.ERROR, logger="src.storage.store"):
            PolicyStore(data_dir=str(tmp_path))
        assert any("corrupted" in r.message.lower() for r in caplog.records)


class TestSave:
    def test_save_creates_directory(self, tmp_path):
        data_dir = tmp_path / "sub" / "dir"
        store = PolicyStore(data_dir=str(data_dir))
        store.add_policies([_make_policy()])
        assert (data_dir / "policies.json").exists()
