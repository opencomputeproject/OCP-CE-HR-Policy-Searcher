"""Unit tests for configuration loader."""

import pytest
from pathlib import Path
import tempfile
import shutil

import yaml

from src.config.loader import (
    load_settings,
    get_enabled_domains,
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
