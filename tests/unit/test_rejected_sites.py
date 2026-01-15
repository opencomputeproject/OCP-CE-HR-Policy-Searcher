"""Tests for rejected sites loading functionality."""

import pytest
from pathlib import Path
import tempfile
import shutil

from src.config.loader import (
    _load_rejected_sites_directory,
    load_rejected_sites,
    list_rejected_sites,
    is_url_rejected,
    ConfigurationError,
)


class TestLoadRejectedSitesDirectory:
    """Tests for _load_rejected_sites_directory function."""

    def test_empty_directory(self, tmp_path):
        """Empty directory returns empty list."""
        result = _load_rejected_sites_directory(tmp_path)
        assert result == []

    def test_nonexistent_directory(self, tmp_path):
        """Nonexistent directory returns empty list."""
        nonexistent = tmp_path / "does_not_exist"
        result = _load_rejected_sites_directory(nonexistent)
        assert result == []

    def test_load_single_file(self, tmp_path):
        """Load a single YAML file with rejected sites."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""
rejected_sites:
  - url: https://example.com
    reason: Test reason
    evaluated_date: "2026-01-15"
""")
        result = _load_rejected_sites_directory(tmp_path)
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com"
        assert result[0]["reason"] == "Test reason"
        assert result[0]["_source_file"] == "test.yaml"

    def test_load_multiple_files(self, tmp_path):
        """Load multiple YAML files and merge."""
        file1 = tmp_path / "a.yaml"
        file1.write_text("""
rejected_sites:
  - url: https://site1.com
    reason: Reason 1
""")
        file2 = tmp_path / "b.yaml"
        file2.write_text("""
rejected_sites:
  - url: https://site2.com
    reason: Reason 2
  - url: https://site3.com
    reason: Reason 3
""")
        result = _load_rejected_sites_directory(tmp_path)
        assert len(result) == 3
        urls = [r["url"] for r in result]
        assert "https://site1.com" in urls
        assert "https://site2.com" in urls
        assert "https://site3.com" in urls

    def test_skip_template_files(self, tmp_path):
        """Files starting with _ are skipped."""
        template = tmp_path / "_template.yaml"
        template.write_text("""
rejected_sites:
  - url: https://should-be-skipped.com
    reason: Should not appear
""")
        regular = tmp_path / "regular.yaml"
        regular.write_text("""
rejected_sites:
  - url: https://included.com
    reason: Should appear
""")
        result = _load_rejected_sites_directory(tmp_path)
        assert len(result) == 1
        assert result[0]["url"] == "https://included.com"

    def test_load_subdirectories(self, tmp_path):
        """Load files from subdirectories recursively."""
        # Root level file
        root_file = tmp_path / "root.yaml"
        root_file.write_text("""
rejected_sites:
  - url: https://root.com
    reason: Root level
""")
        # Subdirectory file
        subdir = tmp_path / "uk"
        subdir.mkdir()
        sub_file = subdir / "government.yaml"
        sub_file.write_text("""
rejected_sites:
  - url: https://uk-gov.com
    reason: UK government
""")
        # Nested subdirectory
        nested = subdir / "nested"
        nested.mkdir()
        nested_file = nested / "deep.yaml"
        nested_file.write_text("""
rejected_sites:
  - url: https://deep.com
    reason: Deeply nested
""")
        result = _load_rejected_sites_directory(tmp_path)
        assert len(result) == 3
        urls = [r["url"] for r in result]
        assert "https://root.com" in urls
        assert "https://uk-gov.com" in urls
        assert "https://deep.com" in urls

        # Check source file paths include subdirectory
        sources = {r["url"]: r["_source_file"] for r in result}
        assert "uk" in sources["https://uk-gov.com"]
        assert "nested" in sources["https://deep.com"]

    def test_empty_file_returns_empty_list(self, tmp_path):
        """Empty YAML file doesn't cause errors."""
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        result = _load_rejected_sites_directory(tmp_path)
        assert result == []

    def test_file_without_rejected_sites_key(self, tmp_path):
        """File without rejected_sites key is handled."""
        other = tmp_path / "other.yaml"
        other.write_text("""
some_other_key:
  - item: value
""")
        result = _load_rejected_sites_directory(tmp_path)
        assert result == []

    def test_handles_none_entries(self, tmp_path):
        """None entries in the list are skipped."""
        with_none = tmp_path / "with_none.yaml"
        with_none.write_text("""
rejected_sites:
  - url: https://valid.com
    reason: Valid
  -
  - url: https://also-valid.com
    reason: Also valid
""")
        result = _load_rejected_sites_directory(tmp_path)
        assert len(result) == 2


class TestListRejectedSites:
    """Tests for list_rejected_sites function."""

    def test_formats_output(self):
        """Returns formatted list with all fields."""
        test_data = [
            {
                "url": "https://test.com",
                "reason": "Test reason",
                "evaluated_date": "2026-01-15",
                "evaluated_by": "Tester",
                "reconsider_if": "Condition",
                "replaced_by": "other_id",
                "_source_file": "test.yaml",
            }
        ]
        result = list_rejected_sites(test_data)
        assert len(result) == 1
        assert result[0]["url"] == "https://test.com"
        assert result[0]["reason"] == "Test reason"
        assert result[0]["evaluated_date"] == "2026-01-15"
        assert result[0]["evaluated_by"] == "Tester"
        assert result[0]["reconsider_if"] == "Condition"
        assert result[0]["replaced_by"] == "other_id"
        assert result[0]["source_file"] == "test.yaml"

    def test_handles_missing_fields(self):
        """Missing optional fields return empty strings."""
        test_data = [
            {
                "url": "https://test.com",
                "reason": "Minimal entry",
            }
        ]
        result = list_rejected_sites(test_data)
        assert len(result) == 1
        assert result[0]["evaluated_date"] == ""
        assert result[0]["evaluated_by"] == ""
        assert result[0]["reconsider_if"] == ""

    def test_filters_none_entries(self):
        """None entries are filtered out."""
        test_data = [
            {"url": "https://valid.com", "reason": "Valid"},
            None,
            {"url": "https://also-valid.com", "reason": "Also valid"},
        ]
        result = list_rejected_sites(test_data)
        assert len(result) == 2


class TestIsUrlRejected:
    """Tests for is_url_rejected function."""

    def test_url_is_rejected(self):
        """Returns True for rejected URL."""
        test_data = [
            {"url": "https://rejected.com", "reason": "Rejected"},
        ]
        assert is_url_rejected("https://rejected.com", test_data) is True

    def test_url_not_rejected(self):
        """Returns False for URL not in list."""
        test_data = [
            {"url": "https://rejected.com", "reason": "Rejected"},
        ]
        assert is_url_rejected("https://other.com", test_data) is False

    def test_empty_list(self):
        """Returns False for empty list."""
        assert is_url_rejected("https://anything.com", []) is False

    def test_handles_none_entries(self):
        """Handles None entries in list."""
        test_data = [
            {"url": "https://rejected.com", "reason": "Rejected"},
            None,
        ]
        assert is_url_rejected("https://rejected.com", test_data) is True


class TestLoadRejectedSitesIntegration:
    """Integration tests loading from actual config directory."""

    def test_load_from_config(self):
        """Load rejected sites from config/rejected_sites/ directory."""
        rejected = load_rejected_sites()
        # Should have at least the migrated entry
        assert isinstance(rejected, list)
        # Check if the migrated entry is present
        urls = [r.get("url") for r in rejected]
        assert "https://www.bmwk.de/Navigation/EN/Topic/Functions/Liste4_Formular.html" in urls


class TestDomainsDirectorySubdirectories:
    """Tests for _load_domains_directory with subdirectories."""

    def test_load_domains_from_subdirectories(self, tmp_path):
        """Load domain files from subdirectories."""
        from src.config.loader import _load_domains_directory

        # Root level
        root = tmp_path / "root.yaml"
        root.write_text("""
domains:
  - id: root_domain
    name: Root Domain
    base_url: https://root.com
    start_paths: ["/"]
""")
        # Subdirectory
        subdir = tmp_path / "region"
        subdir.mkdir()
        sub = subdir / "local.yaml"
        sub.write_text("""
domains:
  - id: sub_domain
    name: Sub Domain
    base_url: https://sub.com
    start_paths: ["/"]
""")
        result = _load_domains_directory(tmp_path)
        assert len(result) == 2
        ids = [d["id"] for d in result]
        assert "root_domain" in ids
        assert "sub_domain" in ids

    def test_skip_template_in_subdirectories(self, tmp_path):
        """Template files in subdirectories are also skipped."""
        from src.config.loader import _load_domains_directory

        subdir = tmp_path / "region"
        subdir.mkdir()
        template = subdir / "_template.yaml"
        template.write_text("""
domains:
  - id: should_skip
    name: Should Skip
    base_url: https://skip.com
    start_paths: ["/"]
""")
        regular = subdir / "regular.yaml"
        regular.write_text("""
domains:
  - id: should_include
    name: Should Include
    base_url: https://include.com
    start_paths: ["/"]
""")
        result = _load_domains_directory(tmp_path)
        assert len(result) == 1
        assert result[0]["id"] == "should_include"
