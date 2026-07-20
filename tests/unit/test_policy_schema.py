"""Tests for the Staging schema mapping (Policy -> Heat Reuse DB columns)."""

from datetime import date, datetime

from src.core.models import Policy, PolicyType, VerificationFlag
from src.core.policy_schema import (
    MASTER_HEADERS,
    STAGING_HEADERS,
    from_staging_row,
    split_jurisdiction,
    status_label,
    type_label,
)


def _row(policy: Policy) -> dict:
    """Header-keyed row dict, matching what gspread's get_all_records() returns."""
    return dict(zip(STAGING_HEADERS, policy.to_sheet_row()))


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


class TestFromStagingRow:
    """Test from_staging_row() — the inverse mapping used by import_sheet."""

    def _full_policy(self, **overrides) -> Policy:
        defaults = dict(
            url="https://example.gov/policy",
            policy_name="Test Act",
            jurisdiction="Germany",
            policy_type=PolicyType.LAW,
            summary="A test law",
            relevance_score=9,
            effective_date=date(2024, 3, 1),
            source_language="German",
            bill_number="EnEfG-2024",
            key_requirements="Must reuse heat",
            discovered_at=datetime(2024, 6, 15, 10, 30, 0),
            crawl_status="success",
            review_status="new",
            scan_id="scan_123",
            domain_id="bmwk_de",
            lifecycle_stage="enacted",
            verification_flags=[VerificationFlag.GENERIC_NAME],
            referenced_policies=["EU EED Art 26"],
            referenced_urls=["https://eur-lex.europa.eu/x"],
        )
        defaults.update(overrides)
        return Policy(**defaults)

    def test_round_trip_full_row(self):
        policy = self._full_policy()
        kwargs = from_staging_row(_row(policy))
        rebuilt = Policy(**kwargs)

        assert rebuilt.url == policy.url
        assert rebuilt.policy_name == policy.policy_name
        assert rebuilt.jurisdiction == "Germany"
        assert rebuilt.policy_type == PolicyType.LAW
        assert rebuilt.summary == policy.summary
        assert rebuilt.relevance_score == 9
        assert rebuilt.effective_date == date(2024, 3, 1)
        assert rebuilt.source_language == "German"
        assert rebuilt.bill_number == "EnEfG-2024"
        assert rebuilt.key_requirements == "Must reuse heat"
        assert rebuilt.discovered_at == datetime(2024, 6, 15, 10, 30, 0)
        assert rebuilt.crawl_status == "success"
        assert rebuilt.review_status == "new"
        assert rebuilt.scan_id == "scan_123"
        assert rebuilt.domain_id == "bmwk_de"
        assert rebuilt.lifecycle_stage == "enacted"
        assert rebuilt.verification_flags == [VerificationFlag.GENERIC_NAME]
        assert rebuilt.referenced_policies == ["EU EED Art 26"]
        assert rebuilt.referenced_urls == ["https://eur-lex.europa.eu/x"]

    def test_sheets_rendered_datetime_with_single_digit_hour(self):
        """Google Sheets re-renders ISO datetimes on read ("2026-07-07 6:28:07",
        no zero-padded hour) - 56 of 122 real Staging rows failed on this
        before the strptime normalization."""
        policy = self._full_policy()
        row = _row(policy)
        row["Discovered At"] = "2026-07-07 6:28:07"
        rebuilt = Policy(**from_staging_row(row))
        assert rebuilt.discovered_at == datetime(2026, 7, 7, 6, 28, 7)

    def test_round_trip_us_state_jurisdiction(self):
        policy = self._full_policy(jurisdiction="New Jersey")
        kwargs = from_staging_row(_row(policy))
        assert kwargs["jurisdiction"] == "New Jersey"

    def test_round_trip_uk_devolved_jurisdiction(self):
        policy = self._full_policy(jurisdiction="Scotland")
        kwargs = from_staging_row(_row(policy))
        assert kwargs["jurisdiction"] == "Scotland"

    def test_minimal_row_defaults(self):
        policy = Policy(
            url="https://example.gov",
            policy_name="Basic",
            jurisdiction="US",
            policy_type=PolicyType.REGULATION,
            summary="Minimal",
            relevance_score=5,
        )
        kwargs = from_staging_row(_row(policy))
        rebuilt = Policy(**kwargs)

        assert rebuilt.url == policy.url
        assert rebuilt.bill_number is None
        assert rebuilt.key_requirements is None
        assert rebuilt.error_details is None
        assert rebuilt.verification_flags == []
        assert rebuilt.referenced_policies == []
        assert rebuilt.referenced_urls == []
        assert rebuilt.lifecycle_stage == "unknown"
        assert rebuilt.crawl_status == "success"
        assert rebuilt.review_status == "new"

    def test_missing_headers_return_blank_url_and_name(self):
        """A row missing the Link/Name columns maps to empty strings, not KeyError."""
        kwargs = from_staging_row({})
        assert kwargs["url"] == ""
        assert kwargs["policy_name"] == ""
        assert kwargs["relevance_score"] == 0
        assert kwargs["policy_type"] == "unknown"
        assert kwargs["lifecycle_stage"] == "unknown"

    def test_unknown_extra_column_ignored(self):
        policy = self._full_policy()
        row = _row(policy)
        row["Some Future Column"] = "unused value"
        kwargs = from_staging_row(row)
        assert kwargs["url"] == policy.url
        assert "Some Future Column" not in kwargs

    def test_zero_relevance_score_not_treated_as_missing(self):
        policy = self._full_policy(relevance_score=0)
        kwargs = from_staging_row(_row(policy))
        assert kwargs["relevance_score"] == "0"
