"""Unit tests for domain filtering by category, tags, and policy types."""

import pytest

from src.config.loader import (
    filter_domains,
    filter_domains_by_category,
    filter_domains_by_tag,
    filter_domains_by_policy_type,
    list_categories,
    list_tags,
    list_policy_types,
    get_domain_stats,
    ConfigurationError,
    VALID_CATEGORIES,
    VALID_TAGS,
    VALID_POLICY_TYPES,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def sample_domains_config():
    """Sample domains configuration for testing."""
    return {
        "domains": [
            {
                "id": "energy_ministry_1",
                "name": "Energy Ministry 1",
                "enabled": True,
                "category": "energy_ministry",
                "tags": ["efficiency", "mandates"],
                "policy_types": ["law", "regulation"],
            },
            {
                "id": "energy_ministry_2",
                "name": "Energy Ministry 2",
                "enabled": True,
                "category": "energy_ministry",
                "tags": ["incentives", "efficiency"],
                "policy_types": ["incentive", "guidance"],
            },
            {
                "id": "legislative_1",
                "name": "Legislature 1",
                "enabled": True,
                "category": "legislative",
                "tags": ["mandates"],
                "policy_types": ["law"],
            },
            {
                "id": "regulatory_1",
                "name": "Regulatory 1",
                "enabled": True,
                "category": "regulatory",
                "tags": ["planning", "efficiency"],
                "policy_types": ["regulation", "guidance"],
            },
            {
                "id": "disabled_domain",
                "name": "Disabled Domain",
                "enabled": False,
                "category": "energy_ministry",
                "tags": ["efficiency"],
                "policy_types": ["law"],
            },
            {
                "id": "uncategorized_domain",
                "name": "Uncategorized Domain",
                "enabled": True,
                # No category, tags, or policy_types
            },
        ]
    }


# =============================================================================
# VALID CONSTANTS TESTS
# =============================================================================

class TestValidConstants:
    """Tests for VALID_CATEGORIES, VALID_TAGS, VALID_POLICY_TYPES."""

    def test_valid_categories_not_empty(self):
        """Should have at least one category."""
        assert len(VALID_CATEGORIES) > 0

    def test_valid_categories_contains_expected(self):
        """Should contain expected categories."""
        expected = ["energy_ministry", "legislative", "regulatory", "grid_operator"]
        for cat in expected:
            assert cat in VALID_CATEGORIES

    def test_valid_tags_not_empty(self):
        """Should have at least one tag."""
        assert len(VALID_TAGS) > 0

    def test_valid_tags_contains_expected(self):
        """Should contain expected tags."""
        expected = ["efficiency", "mandates", "incentives", "carbon"]
        for tag in expected:
            assert tag in VALID_TAGS

    def test_valid_policy_types_not_empty(self):
        """Should have at least one policy type."""
        assert len(VALID_POLICY_TYPES) > 0

    def test_valid_policy_types_contains_expected(self):
        """Should contain expected policy types."""
        expected = ["law", "regulation", "directive", "incentive", "guidance"]
        for pt in expected:
            assert pt in VALID_POLICY_TYPES


# =============================================================================
# FILTER BY CATEGORY TESTS
# =============================================================================

class TestFilterDomainsByCategory:
    """Tests for filter_domains_by_category function."""

    def test_filter_by_energy_ministry(self, sample_domains_config):
        """Should return only energy ministry domains."""
        result = filter_domains_by_category(sample_domains_config, "energy_ministry")

        assert len(result) == 2  # Not 3, because one is disabled
        ids = [d["id"] for d in result]
        assert "energy_ministry_1" in ids
        assert "energy_ministry_2" in ids
        assert "disabled_domain" not in ids

    def test_filter_by_legislative(self, sample_domains_config):
        """Should return only legislative domains."""
        result = filter_domains_by_category(sample_domains_config, "legislative")

        assert len(result) == 1
        assert result[0]["id"] == "legislative_1"

    def test_filter_by_regulatory(self, sample_domains_config):
        """Should return only regulatory domains."""
        result = filter_domains_by_category(sample_domains_config, "regulatory")

        assert len(result) == 1
        assert result[0]["id"] == "regulatory_1"

    def test_filter_excludes_disabled(self, sample_domains_config):
        """Should exclude disabled domains."""
        result = filter_domains_by_category(sample_domains_config, "energy_ministry")
        ids = [d["id"] for d in result]
        assert "disabled_domain" not in ids

    def test_filter_invalid_category_raises_error(self, sample_domains_config):
        """Should raise error for invalid category."""
        with pytest.raises(ConfigurationError) as exc_info:
            filter_domains_by_category(sample_domains_config, "invalid_category")

        assert "Unknown category" in str(exc_info.value)
        assert "invalid_category" in str(exc_info.value)

    def test_filter_returns_empty_for_unused_category(self, sample_domains_config):
        """Should return empty list for valid but unused category."""
        result = filter_domains_by_category(sample_domains_config, "grid_operator")
        assert result == []


# =============================================================================
# FILTER BY TAG TESTS
# =============================================================================

class TestFilterDomainsByTag:
    """Tests for filter_domains_by_tag function."""

    def test_filter_by_efficiency_tag(self, sample_domains_config):
        """Should return domains with efficiency tag."""
        result = filter_domains_by_tag(sample_domains_config, "efficiency")

        assert len(result) == 3  # energy_ministry_1, energy_ministry_2, regulatory_1
        ids = [d["id"] for d in result]
        assert "energy_ministry_1" in ids
        assert "energy_ministry_2" in ids
        assert "regulatory_1" in ids

    def test_filter_by_mandates_tag(self, sample_domains_config):
        """Should return domains with mandates tag."""
        result = filter_domains_by_tag(sample_domains_config, "mandates")

        assert len(result) == 2  # energy_ministry_1, legislative_1
        ids = [d["id"] for d in result]
        assert "energy_ministry_1" in ids
        assert "legislative_1" in ids

    def test_filter_excludes_disabled(self, sample_domains_config):
        """Should exclude disabled domains even if they have the tag."""
        result = filter_domains_by_tag(sample_domains_config, "efficiency")
        ids = [d["id"] for d in result]
        assert "disabled_domain" not in ids

    def test_filter_invalid_tag_raises_error(self, sample_domains_config):
        """Should raise error for invalid tag."""
        with pytest.raises(ConfigurationError) as exc_info:
            filter_domains_by_tag(sample_domains_config, "invalid_tag")

        assert "Unknown tag" in str(exc_info.value)

    def test_filter_returns_empty_for_unused_tag(self, sample_domains_config):
        """Should return empty list for valid but unused tag."""
        result = filter_domains_by_tag(sample_domains_config, "reporting")
        assert result == []


# =============================================================================
# FILTER BY POLICY TYPE TESTS
# =============================================================================

class TestFilterDomainsByPolicyType:
    """Tests for filter_domains_by_policy_type function."""

    def test_filter_by_law_policy_type(self, sample_domains_config):
        """Should return domains with law policy type."""
        result = filter_domains_by_policy_type(sample_domains_config, "law")

        assert len(result) == 2  # energy_ministry_1, legislative_1
        ids = [d["id"] for d in result]
        assert "energy_ministry_1" in ids
        assert "legislative_1" in ids

    def test_filter_by_guidance_policy_type(self, sample_domains_config):
        """Should return domains with guidance policy type."""
        result = filter_domains_by_policy_type(sample_domains_config, "guidance")

        assert len(result) == 2  # energy_ministry_2, regulatory_1
        ids = [d["id"] for d in result]
        assert "energy_ministry_2" in ids
        assert "regulatory_1" in ids

    def test_filter_excludes_disabled(self, sample_domains_config):
        """Should exclude disabled domains."""
        result = filter_domains_by_policy_type(sample_domains_config, "law")
        ids = [d["id"] for d in result]
        assert "disabled_domain" not in ids

    def test_filter_invalid_policy_type_raises_error(self, sample_domains_config):
        """Should raise error for invalid policy type."""
        with pytest.raises(ConfigurationError) as exc_info:
            filter_domains_by_policy_type(sample_domains_config, "invalid_type")

        assert "Unknown policy type" in str(exc_info.value)


# =============================================================================
# COMBINED FILTER TESTS
# =============================================================================

class TestFilterDomains:
    """Tests for filter_domains function with multiple criteria."""

    def test_filter_by_category_only(self, sample_domains_config):
        """Should filter by category when only category specified."""
        result = filter_domains(sample_domains_config, category="energy_ministry")

        assert len(result) == 2
        ids = [d["id"] for d in result]
        assert "energy_ministry_1" in ids
        assert "energy_ministry_2" in ids

    def test_filter_by_single_tag(self, sample_domains_config):
        """Should filter by tag when only tag specified."""
        result = filter_domains(sample_domains_config, tags=["mandates"])

        assert len(result) == 2
        ids = [d["id"] for d in result]
        assert "energy_ministry_1" in ids
        assert "legislative_1" in ids

    def test_filter_by_multiple_tags_any(self, sample_domains_config):
        """Should return domains with ANY of the specified tags (default)."""
        result = filter_domains(
            sample_domains_config,
            tags=["mandates", "incentives"],
            match_all_tags=False
        )

        # energy_ministry_1 (mandates), energy_ministry_2 (incentives), legislative_1 (mandates)
        assert len(result) == 3
        ids = [d["id"] for d in result]
        assert "energy_ministry_1" in ids
        assert "energy_ministry_2" in ids
        assert "legislative_1" in ids

    def test_filter_by_multiple_tags_all(self, sample_domains_config):
        """Should return domains with ALL specified tags when match_all_tags=True."""
        result = filter_domains(
            sample_domains_config,
            tags=["efficiency", "mandates"],
            match_all_tags=True
        )

        # Only energy_ministry_1 has both efficiency AND mandates
        assert len(result) == 1
        assert result[0]["id"] == "energy_ministry_1"

    def test_filter_by_category_and_tag(self, sample_domains_config):
        """Should filter by both category AND tag."""
        result = filter_domains(
            sample_domains_config,
            category="energy_ministry",
            tags=["mandates"]
        )

        # Only energy_ministry_1 is energy_ministry AND has mandates tag
        assert len(result) == 1
        assert result[0]["id"] == "energy_ministry_1"

    def test_filter_by_category_tag_and_policy_type(self, sample_domains_config):
        """Should filter by category, tag, and policy type."""
        result = filter_domains(
            sample_domains_config,
            category="energy_ministry",
            tags=["efficiency"],
            policy_types=["regulation"]
        )

        # Only energy_ministry_1 matches all criteria
        assert len(result) == 1
        assert result[0]["id"] == "energy_ministry_1"

    def test_filter_no_criteria_returns_all_enabled(self, sample_domains_config):
        """Should return all enabled domains when no criteria specified."""
        result = filter_domains(sample_domains_config)

        # All enabled: energy_ministry_1, energy_ministry_2, legislative_1, regulatory_1, uncategorized_domain
        assert len(result) == 5

    def test_filter_returns_empty_when_no_match(self, sample_domains_config):
        """Should return empty list when no domains match."""
        result = filter_domains(
            sample_domains_config,
            category="energy_ministry",
            tags=["planning"]  # No energy_ministry has planning tag
        )
        assert result == []

    def test_filter_invalid_category_raises_error(self, sample_domains_config):
        """Should raise error for invalid category."""
        with pytest.raises(ConfigurationError):
            filter_domains(sample_domains_config, category="invalid")

    def test_filter_invalid_tag_raises_error(self, sample_domains_config):
        """Should raise error for invalid tag."""
        with pytest.raises(ConfigurationError):
            filter_domains(sample_domains_config, tags=["invalid"])

    def test_filter_invalid_policy_type_raises_error(self, sample_domains_config):
        """Should raise error for invalid policy type."""
        with pytest.raises(ConfigurationError):
            filter_domains(sample_domains_config, policy_types=["invalid"])


# =============================================================================
# LIST FUNCTIONS TESTS
# =============================================================================

class TestListFunctions:
    """Tests for list_categories, list_tags, list_policy_types functions."""

    def test_list_categories_returns_dict(self):
        """Should return dictionary with descriptions."""
        result = list_categories()
        assert isinstance(result, dict)
        assert len(result) > 0
        # Check it has descriptions
        for key, value in result.items():
            assert isinstance(key, str)
            assert isinstance(value, str)

    def test_list_tags_returns_dict(self):
        """Should return dictionary with descriptions."""
        result = list_tags()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_policy_types_returns_dict(self):
        """Should return dictionary with descriptions."""
        result = list_policy_types()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_functions_return_copies(self):
        """Should return copies, not the original dicts."""
        categories = list_categories()
        categories["test"] = "modified"
        assert "test" not in VALID_CATEGORIES


# =============================================================================
# DOMAIN STATS TESTS
# =============================================================================

class TestGetDomainStats:
    """Tests for get_domain_stats function."""

    def test_stats_total_domains(self, sample_domains_config):
        """Should count total domains."""
        stats = get_domain_stats(sample_domains_config)
        assert stats["total_domains"] == 6

    def test_stats_enabled_domains(self, sample_domains_config):
        """Should count enabled domains."""
        stats = get_domain_stats(sample_domains_config)
        assert stats["enabled_domains"] == 5

    def test_stats_by_category(self, sample_domains_config):
        """Should count by category."""
        stats = get_domain_stats(sample_domains_config)
        by_category = stats["by_category"]

        assert by_category["energy_ministry"] == 2  # Only enabled ones
        assert by_category["legislative"] == 1
        assert by_category["regulatory"] == 1
        assert by_category["(uncategorized)"] == 1

    def test_stats_by_tag(self, sample_domains_config):
        """Should count by tag."""
        stats = get_domain_stats(sample_domains_config)
        by_tag = stats["by_tag"]

        assert by_tag["efficiency"] == 3
        assert by_tag["mandates"] == 2
        assert by_tag["incentives"] == 1
        assert by_tag["planning"] == 1

    def test_stats_by_policy_type(self, sample_domains_config):
        """Should count by policy type."""
        stats = get_domain_stats(sample_domains_config)
        by_policy_type = stats["by_policy_type"]

        assert by_policy_type["law"] == 2
        assert by_policy_type["regulation"] == 2
        assert by_policy_type["guidance"] == 2
        assert by_policy_type["incentive"] == 1

    def test_stats_empty_config(self):
        """Should handle empty config."""
        stats = get_domain_stats({"domains": []})

        assert stats["total_domains"] == 0
        assert stats["enabled_domains"] == 0
        assert stats["by_category"] == {}
        assert stats["by_tag"] == {}
        assert stats["by_policy_type"] == {}


# =============================================================================
# INTEGRATION TESTS WITH ACTUAL CONFIG
# =============================================================================

class TestIntegrationWithActualConfig:
    """Integration tests using actual configuration files."""

    def test_filter_by_category_energy_ministry(self):
        """Should filter actual config by energy_ministry category."""
        from src.config.loader import load_settings

        _, domains_config, _ = load_settings()
        result = filter_domains_by_category(domains_config, "energy_ministry")

        # Should have several energy ministry domains
        assert len(result) > 0
        # All should have energy_ministry category
        for domain in result:
            assert domain.get("category") == "energy_ministry"

    def test_filter_by_tag_efficiency(self):
        """Should filter actual config by efficiency tag."""
        from src.config.loader import load_settings

        _, domains_config, _ = load_settings()
        result = filter_domains_by_tag(domains_config, "efficiency")

        # Should have several domains with efficiency tag
        assert len(result) > 0
        # All should have efficiency tag
        for domain in result:
            assert "efficiency" in domain.get("tags", [])

    def test_domain_stats_actual_config(self):
        """Should generate stats for actual config."""
        from src.config.loader import load_settings

        _, domains_config, _ = load_settings()
        stats = get_domain_stats(domains_config)

        # Should have totals
        assert stats["total_domains"] > 0
        assert stats["enabled_domains"] > 0
        # Should have categorization data
        assert len(stats["by_category"]) > 0

    def test_combined_filter_actual_config(self):
        """Should filter actual config with multiple criteria."""
        from src.config.loader import load_settings

        _, domains_config, _ = load_settings()
        result = filter_domains(
            domains_config,
            category="energy_ministry",
            tags=["efficiency"]
        )

        # Should have matches
        assert len(result) >= 0  # May or may not have matches depending on data
        # All results should match criteria
        for domain in result:
            assert domain.get("category") == "energy_ministry"
            assert "efficiency" in domain.get("tags", [])
