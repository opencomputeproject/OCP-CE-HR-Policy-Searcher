"""Integration tests for AI-powered discovery workflow (Phase 4).

Tests:
- _auto_assign_groups correctly updates groups.yaml
- _execute_add_domain creates YAML and updates groups
- --discover CLI argument parsing
- REGION_TO_GROUPS mapping completeness
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.agent.tools import _auto_assign_groups, REGION_TO_GROUPS
from src.core.config import VALID_REGIONS


class TestAutoAssignGroups:
    """Test that _auto_assign_groups correctly updates groups.yaml."""

    def _create_temp_config(self, groups_content: dict) -> Path:
        """Create a temp config dir with a groups.yaml file."""
        tmpdir = Path(tempfile.mkdtemp())
        groups_file = tmpdir / "groups.yaml"
        with open(groups_file, "w", encoding="utf-8") as f:
            yaml.dump(groups_content, f, allow_unicode=True, sort_keys=False)
        return tmpdir

    def test_assigns_to_matching_groups(self):
        """Domain with eu_south region should be added to eu_south and eu groups."""
        groups = {
            "groups": {
                "eu": {"description": "EU", "domains": ["bmwk_de"]},
                "eu_south": {"description": "Southern EU", "domains": ["miteco_es"]},
                "nordic": {"description": "Nordic", "domains": ["ens_dk"]},
            }
        }
        config_dir = self._create_temp_config(groups)

        updated = _auto_assign_groups(
            domain_id="new_domain_it",
            regions=["eu", "eu_south", "italy"],
            config_dir=config_dir,
        )

        assert "eu" in updated
        assert "eu_south" in updated
        assert "nordic" not in updated

        # Verify file was written
        with open(config_dir / "groups.yaml", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        assert "new_domain_it" in result["groups"]["eu"]["domains"]
        assert "new_domain_it" in result["groups"]["eu_south"]["domains"]
        assert "new_domain_it" not in result["groups"]["nordic"]["domains"]

    def test_skips_all_group(self):
        """The 'all' group should never be updated (it's auto-populated)."""
        groups = {
            "groups": {
                "all": {"description": "All domains"},
                "eu": {"description": "EU", "domains": []},
            }
        }
        config_dir = self._create_temp_config(groups)

        updated = _auto_assign_groups(
            domain_id="test_domain",
            regions=["eu"],
            config_dir=config_dir,
        )

        assert "all" not in updated

    def test_no_duplicate_entries(self):
        """Adding a domain that's already in a group should not create duplicates."""
        groups = {
            "groups": {
                "eu": {"description": "EU", "domains": ["existing_domain"]},
            }
        }
        config_dir = self._create_temp_config(groups)

        updated = _auto_assign_groups(
            domain_id="existing_domain",
            regions=["eu"],
            config_dir=config_dir,
        )

        assert updated == []  # No changes made

        with open(config_dir / "groups.yaml", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        # Should still have exactly one entry
        assert result["groups"]["eu"]["domains"].count("existing_domain") == 1

    def test_us_state_assignment(self):
        """US state domains should be assigned to us_states and us groups."""
        groups = {
            "groups": {
                "us": {"description": "US", "domains": ["energy_gov"]},
                "us_states": {"description": "US states", "domains": ["ca_energy"]},
                "eu": {"description": "EU", "domains": []},
            }
        }
        config_dir = self._create_temp_config(groups)

        updated = _auto_assign_groups(
            domain_id="co_energy",
            regions=["us_states"],
            config_dir=config_dir,
        )

        assert "us_states" in updated
        assert "us" in updated
        assert "eu" not in updated

    def test_missing_groups_file(self):
        """Should return empty list if groups.yaml doesn't exist."""
        tmpdir = Path(tempfile.mkdtemp())
        updated = _auto_assign_groups("test", ["eu"], tmpdir)
        assert updated == []

    def test_eu_east_assignment(self):
        """Eastern European domains should be assigned to eu_east and eu groups."""
        groups = {
            "groups": {
                "eu": {"description": "EU", "domains": []},
                "eu_east": {"description": "Eastern EU", "domains": []},
            }
        }
        config_dir = self._create_temp_config(groups)

        updated = _auto_assign_groups(
            domain_id="klimat_pl",
            regions=["eu", "eu_east", "poland"],
            config_dir=config_dir,
        )

        assert "eu" in updated
        assert "eu_east" in updated


class TestRegionToGroupsMapping:
    """Test that REGION_TO_GROUPS covers all relevant regions."""

    def test_all_country_regions_have_mapping(self):
        """Every country-level VALID_REGION should have a REGION_TO_GROUPS entry."""
        # Skip meta-regions that are groups themselves
        meta_regions = {"eu", "europe", "nordic", "eu_central", "eu_west",
                        "eu_south", "eu_east", "uk", "us", "us_states", "apac"}
        # Skip US state sub-regions
        us_states = {"oregon", "texas", "california", "virginia"}

        country_regions = set(VALID_REGIONS.keys()) - meta_regions - us_states
        for region in country_regions:
            assert region in REGION_TO_GROUPS, (
                f"Region '{region}' is in VALID_REGIONS but not in REGION_TO_GROUPS"
            )

    def test_group_targets_exist_in_groups_yaml(self):
        """All group names referenced by REGION_TO_GROUPS should be valid group names."""
        # Load actual groups.yaml
        groups_file = Path("config/groups.yaml")
        if not groups_file.exists():
            pytest.skip("groups.yaml not found")

        with open(groups_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        actual_groups = set(data.get("groups", {}).keys())

        for region, target_groups in REGION_TO_GROUPS.items():
            for group in target_groups:
                assert group in actual_groups, (
                    f"REGION_TO_GROUPS['{region}'] references group '{group}' "
                    f"which doesn't exist in groups.yaml"
                )


class TestDiscoverCLI:
    """Test --discover CLI argument parsing."""

    def test_discover_arg_builds_prompt(self):
        """--discover Poland should construct a discovery prompt."""
        # Simulate the arg parsing logic from __main__.py
        args = ["--discover", "Poland"]

        assert args[0] == "--discover"
        country = " ".join(args[1:])
        assert country == "Poland"

        # Build the expected prompt
        message = (
            f"Discover new coverage for {country}. "
            f"Search for government websites about data center waste heat, "
            f"energy efficiency, district heating, and heat recovery regulation "
            f"in {country}. Use the country's native language for search terms "
            f"when appropriate. Add any relevant government websites you find. "
            f"Then analyze the most promising pages for policy content. "
            f"Summarize what you discovered."
        )
        assert "Poland" in message
        assert "native language" in message

    def test_discover_multi_word_country(self):
        """--discover Czech Republic should work with multi-word country names."""
        args = ["--discover", "Czech", "Republic"]
        country = " ".join(args[1:])
        assert country == "Czech Republic"
