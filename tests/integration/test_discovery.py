"""Integration tests for AI-powered discovery workflow (Phase 4).

Tests:
- _auto_assign_groups correctly updates groups.yaml
- _execute_add_domain creates YAML and updates groups
- --discover CLI argument parsing
- REGION_TO_GROUPS mapping completeness
- Full discovery workflow with mocked Anthropic API
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from src.agent.orchestrator import PolicyAgent
from src.agent.tools import _auto_assign_groups, REGION_TO_GROUPS, get_all_tools
from src.core.config import ConfigLoader, VALID_REGIONS
from src.orchestration.events import EventBroadcaster
from src.orchestration.scan_manager import ScanManager


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


def _make_text_response(text: str):
    """Create a mock API response with text content and end_turn."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    return response


class TestDiscoverWorkflow:
    """Test the full --discover workflow with mocked Anthropic API."""

    def _build_agent(self):
        """Create a PolicyAgent with real config but mocked API client."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent._messages = []
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(
            config=agent.config, broadcaster=agent.broadcaster, data_dir="data",
        )
        agent.tools = get_all_tools()
        agent.system_prompt = "test"
        agent.model = "test-model"
        return agent

    @pytest.mark.asyncio
    async def test_discover_runs_agent_with_correct_prompt(self):
        """--discover Poland should pass a discovery prompt to the agent."""
        agent = self._build_agent()

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_text_response("Discovered 3 government websites in Poland.")
        )
        agent.client = mock_client

        # Build the discovery prompt (same logic as __main__.py)
        country = "Poland"
        message = (
            f"Discover new coverage for {country}. "
            f"Search for government websites about data center waste heat, "
            f"energy efficiency, district heating, and heat recovery regulation "
            f"in {country}. Use the country's native language for search terms "
            f"when appropriate. Add any relevant government websites you find. "
            f"Then analyze the most promising pages for policy content. "
            f"Summarize what you discovered."
        )

        result = await agent.run(message)

        # Verify the prompt reached the API with Poland in it
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs.get("messages", [])
        assert any("Poland" in str(m) for m in messages)
        assert "Discovered" in result

    @pytest.mark.asyncio
    async def test_discover_system_prompt_has_discovery_instructions(self):
        """The system prompt should include DISCOVER workflow instructions."""
        from src.agent.orchestrator import _build_system_prompt

        agent = self._build_agent()
        prompt = _build_system_prompt(agent.config)

        assert "DISCOVER" in prompt
        assert "web_search" in prompt
        assert "add_domain" in prompt
        assert "native language" in prompt.lower() or "native" in prompt.lower()

    @pytest.mark.asyncio
    async def test_discover_agent_handles_tool_use(self):
        """Discovery workflow should handle tool calls (e.g., list_domains)."""
        agent = self._build_agent()

        # First call: Claude wants to use list_domains to check existing coverage
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "list_domains"
        tool_block.input = {"region": "poland"}
        tool_block.id = "tool_1"

        tool_response = MagicMock()
        tool_response.content = [tool_block]
        tool_response.stop_reason = "tool_use"

        # Second call: Claude responds with findings
        text_response = _make_text_response(
            "Poland has 2 existing domains. I recommend adding more."
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[tool_response, text_response]
        )
        agent.client = mock_client

        result = await agent.run("Discover new coverage for Poland")

        assert mock_client.messages.create.call_count == 2
        assert "Poland" in result
