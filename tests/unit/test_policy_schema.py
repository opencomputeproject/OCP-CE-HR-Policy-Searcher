"""Tests for the Staging schema mapping (Policy -> Heat Reuse DB columns)."""

from src.core.policy_schema import (
    MASTER_HEADERS,
    STAGING_HEADERS,
    split_jurisdiction,
    status_label,
    type_label,
)


class TestStagingHeaders:
    def test_master_headers_first_thirteen(self):
        assert STAGING_HEADERS[:13] == MASTER_HEADERS
        assert len(MASTER_HEADERS) == 13

    def test_link_column_position(self):
        # scan_manager dedupes on this column; it must be findable by header.
        assert STAGING_HEADERS.index("Link") == 10


class TestSplitJurisdiction:
    def test_us_state_full_name(self):
        assert split_jurisdiction("New Jersey") == ("North America", "USA", "New Jersey")

    def test_us_state_case_insensitive(self):
        assert split_jurisdiction("california") == ("North America", "USA", "California")

    def test_us_federal_variants(self):
        for j in ("US", "USA", "United States", "United States of America", "Federal"):
            assert split_jurisdiction(j) == ("North America", "USA", "National")

    def test_eu_wide(self):
        assert split_jurisdiction("EU") == ("Europe", "EU Member States", "Regional")
        assert split_jurisdiction("EU Member States") == (
            "Europe", "EU Member States", "Regional",
        )

    def test_uk_national_and_devolved(self):
        assert split_jurisdiction("United Kingdom") == (
            "Europe", "United Kingdom", "National",
        )
        assert split_jurisdiction("Scotland") == (
            "Europe", "United Kingdom", "Scotland",
        )

    def test_european_country(self):
        assert split_jurisdiction("Germany") == ("Europe", "Germany", "National")
        assert split_jurisdiction("Denmark") == ("Europe", "Denmark", "National")

    def test_apac_and_middle_east(self):
        assert split_jurisdiction("Singapore") == (
            "Asia-Pacific", "Singapore", "National",
        )
        assert split_jurisdiction("UAE") == (
            "Middle East", "United Arab Emirates", "National",
        )

    def test_canada(self):
        assert split_jurisdiction("Canada") == ("North America", "Canada", "National")

    def test_trailing_parenthetical_qualifier(self):
        # The extraction LLM stores values like "Sweden (EU)" and
        # "Finland (EU-wide regulation)" — these must still resolve.
        assert split_jurisdiction("Sweden (EU)") == ("Europe", "Sweden", "National")
        assert split_jurisdiction("Finland (EU-wide regulation)") == (
            "Europe", "Finland", "National",
        )
        assert split_jurisdiction("California (US)") == (
            "North America", "USA", "California",
        )
        assert split_jurisdiction("EU (data centre rules)") == (
            "Europe", "EU Member States", "Regional",
        )

    def test_trailing_state_word(self):
        assert split_jurisdiction("New York State") == (
            "North America", "USA", "New York",
        )

    def test_embedded_place_containment(self):
        assert split_jurisdiction("Stockholm, Sweden") == (
            "Europe", "Sweden", "National",
        )

    def test_unknown_preserved_in_country(self):
        assert split_jurisdiction("Atlantis") == ("", "Atlantis", "")

    def test_empty(self):
        assert split_jurisdiction("") == ("", "", "")
        assert split_jurisdiction(None) == ("", "", "")

    def test_district_of_columbia_lowercase_of(self):
        assert split_jurisdiction("District of Columbia") == (
            "North America", "USA", "District of Columbia",
        )


class TestTypeLabel:
    def test_known_types(self):
        assert type_label("law") == "Legislation"
        assert type_label("grant") == "Grant Program"
        assert type_label("matching_platform") == "Voluntary Initiative"
        assert type_label("tax_incentive") == "Tax Credit"

    def test_unknown_blank(self):
        assert type_label("unknown") == ""
        assert type_label("nonsense") == ""


class TestStatusLabel:
    def test_known_stages(self):
        assert status_label("enacted") == "Enacted"
        assert status_label("in_committee") == "In Committee"
        assert status_label("proposed") == "Proposed"

    def test_unknown_blank(self):
        assert status_label("unknown") == ""
        assert status_label("") == ""
        assert status_label(None) == ""
