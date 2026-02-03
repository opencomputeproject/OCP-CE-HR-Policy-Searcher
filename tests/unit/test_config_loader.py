"""Unit tests for configuration loader."""

import pytest
from pathlib import Path
import tempfile
import shutil

import yaml

from src.config.loader import (
    load_settings,
    get_enabled_domains,
    get_available_domain_files,
    list_groups,
    list_domains,
    ConfigurationError,
    _load_yaml,
    _load_domains_directory,
)


class TestLoadYaml:
    """Tests for _load_yaml helper function."""

    def test_load_existing_file(self, tmp_path):
        """Should load YAML content from existing file."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("key: value\nlist:\n  - item1\n  - item2")

        result = _load_yaml(yaml_file)

        assert result == {"key": "value", "list": ["item1", "item2"]}

    def test_load_nonexistent_file(self, tmp_path):
        """Should return empty dict for nonexistent file."""
        yaml_file = tmp_path / "nonexistent.yaml"

        result = _load_yaml(yaml_file)

        assert result == {}

    def test_load_empty_file(self, tmp_path):
        """Should return empty dict for empty file."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        result = _load_yaml(yaml_file)

        assert result == {}


class TestLoadDomainsDirectory:
    """Tests for _load_domains_directory function."""

    def test_load_multiple_files(self, tmp_path):
        """Should merge domains from multiple YAML files."""
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()

        # Create two domain files
        (domains_dir / "region1.yaml").write_text("""
domains:
  - id: domain1
    name: Domain 1
    base_url: https://example1.com
""")
        (domains_dir / "region2.yaml").write_text("""
domains:
  - id: domain2
    name: Domain 2
    base_url: https://example2.com
""")

        result = _load_domains_directory(domains_dir)

        assert len(result) == 2
        assert result[0]["id"] == "domain1"
        assert result[1]["id"] == "domain2"

    def test_skip_template_files(self, tmp_path):
        """Should skip files starting with underscore."""
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()

        (domains_dir / "_template.yaml").write_text("""
domains:
  - id: template
    name: Template
""")
        (domains_dir / "real.yaml").write_text("""
domains:
  - id: real_domain
    name: Real Domain
""")

        result = _load_domains_directory(domains_dir)

        assert len(result) == 1
        assert result[0]["id"] == "real_domain"

    def test_empty_directory(self, tmp_path):
        """Should return empty list for empty directory."""
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()

        result = _load_domains_directory(domains_dir)

        assert result == []

    def test_nonexistent_directory(self, tmp_path):
        """Should return empty list for nonexistent directory."""
        domains_dir = tmp_path / "nonexistent"

        result = _load_domains_directory(domains_dir)

        assert result == []

    def test_domains_tagged_with_source_file(self, tmp_path):
        """Should tag each domain with _source_file matching the file stem."""
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()

        (domains_dir / "germany.yaml").write_text("""
domains:
  - id: domain_de1
    name: German Domain 1
    base_url: https://de1.com
  - id: domain_de2
    name: German Domain 2
    base_url: https://de2.com
""")
        (domains_dir / "france.yaml").write_text("""
domains:
  - id: domain_fr1
    name: French Domain 1
    base_url: https://fr1.com
""")

        result = _load_domains_directory(domains_dir)

        assert len(result) == 3
        # Files loaded in sorted order: france.yaml then germany.yaml
        assert result[0]["_source_file"] == "france"
        assert result[1]["_source_file"] == "germany"
        assert result[2]["_source_file"] == "germany"


class TestGetEnabledDomains:
    """Tests for get_enabled_domains function."""

    def test_all_group_returns_enabled_only(self):
        """'all' group should return only enabled domains."""
        config = {
            "domains": [
                {"id": "enabled1", "enabled": True},
                {"id": "enabled2"},  # Default enabled
                {"id": "disabled", "enabled": False},
            ],
            "groups": {},
        }

        result = get_enabled_domains(config, "all")

        assert len(result) == 2
        ids = [d["id"] for d in result]
        assert "enabled1" in ids
        assert "enabled2" in ids
        assert "disabled" not in ids

    def test_specific_group(self):
        """Should return domains in specified group."""
        config = {
            "domains": [
                {"id": "domain1", "enabled": True},
                {"id": "domain2", "enabled": True},
                {"id": "domain3", "enabled": True},
            ],
            "groups": {
                "my_group": {
                    "description": "Test group",
                    "domains": ["domain1", "domain3"],
                }
            },
        }

        result = get_enabled_domains(config, "my_group")

        assert len(result) == 2
        ids = [d["id"] for d in result]
        assert "domain1" in ids
        assert "domain3" in ids
        assert "domain2" not in ids

    def test_unknown_group_raises_error(self):
        """Should raise ConfigurationError for unknown group."""
        config = {
            "domains": [{"id": "domain1"}],
            "groups": {"existing": {"domains": ["domain1"]}},
        }

        with pytest.raises(ConfigurationError) as exc_info:
            get_enabled_domains(config, "nonexistent")

        assert "Unknown group" in str(exc_info.value)
        assert "nonexistent" in str(exc_info.value)

    def test_group_with_missing_domain_raises_error(self):
        """Should raise ConfigurationError if group references missing domain."""
        config = {
            "domains": [{"id": "domain1"}],
            "groups": {
                "bad_group": {
                    "domains": ["domain1", "nonexistent_domain"],
                }
            },
        }

        with pytest.raises(ConfigurationError) as exc_info:
            get_enabled_domains(config, "bad_group")

        assert "unknown domains" in str(exc_info.value)
        assert "nonexistent_domain" in str(exc_info.value)

    def test_group_filters_disabled_domains(self):
        """Group should not include disabled domains even if listed."""
        config = {
            "domains": [
                {"id": "enabled", "enabled": True},
                {"id": "disabled", "enabled": False},
            ],
            "groups": {
                "test_group": {
                    "domains": ["enabled", "disabled"],
                }
            },
        }

        result = get_enabled_domains(config, "test_group")

        assert len(result) == 1
        assert result[0]["id"] == "enabled"

    def test_file_name_fallback(self):
        """Should return domains from matching file when group doesn't exist."""
        config = {
            "domains": [
                {"id": "d1", "enabled": True, "_source_file": "germany"},
                {"id": "d2", "enabled": True, "_source_file": "germany"},
                {"id": "d3", "enabled": True, "_source_file": "france"},
            ],
            "groups": {
                "eu": {"domains": ["d1", "d3"]},
            },
        }

        result = get_enabled_domains(config, "germany")

        assert len(result) == 2
        ids = [d["id"] for d in result]
        assert "d1" in ids
        assert "d2" in ids
        assert "d3" not in ids

    def test_group_takes_priority_over_file(self):
        """Group should take priority when name matches both group and file."""
        config = {
            "domains": [
                {"id": "d1", "enabled": True, "_source_file": "eu"},
                {"id": "d2", "enabled": True, "_source_file": "eu"},
                {"id": "d3", "enabled": True, "_source_file": "eu"},
            ],
            "groups": {
                "eu": {
                    "description": "EU group",
                    "domains": ["d1"],  # Group only includes d1
                },
            },
        }

        result = get_enabled_domains(config, "eu")

        # Should use group (1 domain), not file (3 domains)
        assert len(result) == 1
        assert result[0]["id"] == "d1"

    def test_file_fallback_skips_disabled(self):
        """File-name matching should skip disabled domains."""
        config = {
            "domains": [
                {"id": "d1", "enabled": True, "_source_file": "germany"},
                {"id": "d2", "enabled": False, "_source_file": "germany"},
            ],
            "groups": {},
        }

        result = get_enabled_domains(config, "germany")

        assert len(result) == 1
        assert result[0]["id"] == "d1"

    def test_error_shows_available_files(self):
        """Error should show both groups and available file names."""
        config = {
            "domains": [
                {"id": "d1", "enabled": True, "_source_file": "germany"},
                {"id": "d2", "enabled": True, "_source_file": "france"},
            ],
            "groups": {
                "eu": {"domains": ["d1"]},
            },
        }

        with pytest.raises(ConfigurationError) as exc_info:
            get_enabled_domains(config, "nonexistent")

        error_msg = str(exc_info.value)
        assert "nonexistent" in error_msg
        assert "eu" in error_msg  # group listed
        assert "germany" in error_msg  # file listed (not a group name)
        assert "france" in error_msg  # file listed (not a group name)


class TestListGroups:
    """Tests for list_groups function."""

    def test_returns_group_descriptions(self):
        """Should return dict mapping group names to descriptions."""
        config = {
            "groups": {
                "group1": {"description": "First group", "domains": []},
                "group2": {"description": "Second group", "domains": []},
            }
        }

        result = list_groups(config)

        assert result == {
            "group1": "First group",
            "group2": "Second group",
        }

    def test_missing_description(self):
        """Should return 'No description' for groups without description."""
        config = {
            "groups": {
                "no_desc": {"domains": []},
            }
        }

        result = list_groups(config)

        assert result["no_desc"] == "No description"

    def test_empty_groups(self):
        """Should return empty dict when no groups defined."""
        config = {"groups": {}}

        result = list_groups(config)

        assert result == {}


class TestGetAvailableDomainFiles:
    """Tests for get_available_domain_files function."""

    def test_returns_file_counts(self):
        """Should return file names with enabled domain counts."""
        config = {
            "domains": [
                {"id": "d1", "enabled": True, "_source_file": "germany"},
                {"id": "d2", "enabled": True, "_source_file": "germany"},
                {"id": "d3", "enabled": True, "_source_file": "france"},
            ],
        }

        result = get_available_domain_files(config)

        assert result == {"france": 1, "germany": 2}

    def test_excludes_disabled(self):
        """Should not count disabled domains."""
        config = {
            "domains": [
                {"id": "d1", "enabled": True, "_source_file": "germany"},
                {"id": "d2", "enabled": False, "_source_file": "germany"},
                {"id": "d3", "enabled": True, "_source_file": "france"},
            ],
        }

        result = get_available_domain_files(config)

        assert result == {"france": 1, "germany": 1}

    def test_empty_domains(self):
        """Should return empty dict when no domains."""
        config = {"domains": []}

        result = get_available_domain_files(config)

        assert result == {}

    def test_domains_without_source_file(self):
        """Should skip domains without _source_file tag."""
        config = {
            "domains": [
                {"id": "d1", "enabled": True},
                {"id": "d2", "enabled": True, "_source_file": "germany"},
            ],
        }

        result = get_available_domain_files(config)

        assert result == {"germany": 1}


class TestListDomains:
    """Tests for list_domains function."""

    def test_returns_domain_info(self):
        """Should return list of domain info dicts."""
        config = {
            "domains": [
                {"id": "d1", "name": "Domain 1", "base_url": "https://d1.com", "enabled": True},
                {"id": "d2", "name": "Domain 2", "base_url": "https://d2.com", "enabled": False},
            ]
        }

        result = list_domains(config)

        assert len(result) == 2
        assert result[0] == {
            "id": "d1",
            "name": "Domain 1",
            "base_url": "https://d1.com",
            "enabled": True,
            "category": None,
            "tags": [],
            "policy_types": [],
        }
        assert result[1]["enabled"] is False

    def test_default_enabled(self):
        """Should default enabled to True if not specified."""
        config = {
            "domains": [
                {"id": "d1", "name": "Domain 1", "base_url": "https://d1.com"},
            ]
        }

        result = list_domains(config)

        assert result[0]["enabled"] is True


class TestLoadSettingsIntegration:
    """Integration tests using actual config files."""

    def test_load_actual_config(self):
        """Should successfully load the actual project configuration."""
        # This test uses the real config files
        settings, domains_config, keywords_config = load_settings()

        # Verify domains loaded
        assert "domains" in domains_config
        assert len(domains_config["domains"]) > 0

        # Verify groups loaded
        assert "groups" in domains_config
        assert "all" in domains_config["groups"]
        assert "eu" in domains_config["groups"]

        # Verify keywords loaded
        assert "keywords" in keywords_config

    def test_get_enabled_domains_eu(self):
        """Should get EU domains from actual config."""
        _, domains_config, _ = load_settings()

        eu_domains = get_enabled_domains(domains_config, "eu")

        assert len(eu_domains) > 0
        # Check known EU domain exists
        ids = [d["id"] for d in eu_domains]
        assert "bmwk_de" in ids  # German ministry

    def test_get_enabled_domains_quick(self):
        """Quick group should have exactly 2 domains."""
        _, domains_config, _ = load_settings()

        quick_domains = get_enabled_domains(domains_config, "quick")

        assert len(quick_domains) == 2

    def test_file_targeting_germany(self):
        """Should get Germany-specific domains via file name."""
        _, domains_config, _ = load_settings()

        germany_domains = get_enabled_domains(domains_config, "germany")

        assert len(germany_domains) >= 1
        # All should come from germany.yaml
        for d in germany_domains:
            assert d.get("_source_file") == "germany"

    def test_domains_have_source_file_tags(self):
        """All domains should have _source_file tags after loading."""
        _, domains_config, _ = load_settings()

        for d in domains_config["domains"]:
            assert "_source_file" in d, f"Domain {d['id']} missing _source_file tag"
