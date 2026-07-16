"""Tests for Google Sheets integration and Policy sheet methods.

The Staging schema mirrors the OCP "Heat Reuse Policies Database" tab: the
first 13 columns match that tab exactly, followed by PolicyPulse extras.
"""

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from src.core.models import Policy, PolicyType, VerificationFlag
from src.core.policy_schema import STAGING_HEADERS


class TestPolicySheetHeaders:
    """Test Policy.sheet_headers()."""

    def test_header_count(self):
        # 13 master-database columns + 15 PolicyPulse extras.
        assert len(Policy.sheet_headers()) == 28

    def test_master_columns_match_database_order(self):
        headers = Policy.sheet_headers()
        assert headers[0] == "Geographical Area"
        assert headers[1] == "Country"
        assert headers[2] == "Region"
        assert headers[3] == "Name"
        assert headers[4] == "Incentive, Standard, or Enabler?"
        assert headers[5].startswith("Type (")
        assert headers[6] == "Description"
        assert headers[7] == "Exclusive to Data Centers?"
        assert headers[8] == "Status"
        assert headers[9] == "Date Issued (newest version)"
        assert headers[10] == "Link"
        assert headers[11] == "Notes"
        assert headers[12] == "Person Who Added it to the Database"

    def test_extra_columns_present(self):
        headers = Policy.sheet_headers()
        assert headers[13] == "Relevance Score"
        assert "Scan ID" in headers
        assert "Domain ID" in headers
        assert "Referenced URLs" in headers
        assert "Lifecycle Stage" in headers

    def test_headers_are_strings(self):
        for h in Policy.sheet_headers():
            assert isinstance(h, str)


class TestPolicyToSheetRow:
    """Test Policy.to_sheet_row()."""

    def test_full_row(self):
        policy = Policy(
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
            error_details=None,
            review_status="new",
            scan_id="scan_123",
            domain_id="bmwk_de",
            lifecycle_stage="enacted",
            verification_flags=[VerificationFlag.GENERIC_NAME],
        )
        row = policy.to_sheet_row()

        assert len(row) == 28
        # Master columns
        assert row[0] == "Europe"          # Geographical Area
        assert row[1] == "Germany"         # Country
        assert row[2] == "National"        # Region
        assert row[3] == "Test Act"        # Name
        assert row[4] == ""                # Incentive/Standard/Enabler (curation)
        assert row[5] == "Legislation"     # Type
        assert row[6] == "A test law"      # Description
        assert row[7] == ""                # Exclusive to Data Centers (curation)
        assert row[8] == "Enacted"         # Status
        assert row[9] == "2024-03-01"      # Date Issued
        assert row[10] == "https://example.gov/policy"  # Link
        assert row[11] == ""               # Notes (curation)
        assert row[12] == "PolicyPulse (automated)"     # Person who added
        # Extras
        assert row[13] == 9                # Relevance Score
        assert row[14] == "enacted"        # Lifecycle Stage (raw)
        assert row[15] == "law"            # Policy Type (raw)
        assert row[16] == "Must reuse heat"  # Key Requirements
        assert row[17] == "EnEfG-2024"     # Bill Number
        assert row[18] == "German"         # Source Language
        assert row[19] == "2024-06-15T10:30:00"  # Discovered At
        assert row[20] == "success"        # Crawl Status
        assert row[21] == "new"            # Review Status
        assert row[22] == "generic_name"   # Verification Flags
        assert row[25] == "scan_123"       # Scan ID
        assert row[26] == "bmwk_de"        # Domain ID
        assert row[27] == ""               # Error Details

    def test_empty_optionals(self):
        policy = Policy(
            url="https://example.gov",
            policy_name="Basic",
            jurisdiction="US",
            policy_type=PolicyType.REGULATION,
            summary="Minimal",
            relevance_score=5,
        )
        row = policy.to_sheet_row()

        assert len(row) == 28
        assert row[0] == "North America"   # US -> North America
        assert row[1] == "USA"
        assert row[2] == "National"
        assert row[8] == ""    # Status (lifecycle unknown)
        assert row[9] == ""    # Date Issued (no effective_date)
        assert row[16] == ""   # Key Requirements
        assert row[17] == ""   # Bill Number
        assert row[22] == ""   # Verification Flags
        assert row[23] == ""   # Referenced Policies
        assert row[24] == ""   # Referenced URLs
        assert row[27] == ""   # Error Details

    def test_multiple_verification_flags(self):
        policy = Policy(
            url="https://example.gov",
            policy_name="Flagged Policy",
            jurisdiction="US",
            policy_type=PolicyType.LAW,
            summary="Multiple flags",
            relevance_score=8,
            verification_flags=[
                VerificationFlag.JURISDICTION_MISMATCH,
                VerificationFlag.FUTURE_DATE,
            ],
        )
        row = policy.to_sheet_row()
        assert row[22] == "jurisdiction_mismatch, future_date"

    def test_row_with_referenced_policies(self):
        """Referenced policies and URLs should serialize with semicolons."""
        policy = Policy(
            url="https://example.gov/policy",
            policy_name="Heat Reuse Directive",
            jurisdiction="EU",
            policy_type=PolicyType.DIRECTIVE,
            summary="EU-wide heat reuse requirements",
            relevance_score=9,
            referenced_policies=["EU EED Art 26", "EnEfG §12"],
            referenced_urls=["https://eur-lex.europa.eu/x", "https://bmwk.de/y"],
        )
        row = policy.to_sheet_row()
        assert row[0] == "Europe"
        assert row[1] == "EU Member States"
        assert row[23] == "EU EED Art 26; EnEfG §12"
        assert row[24] == "https://eur-lex.europa.eu/x; https://bmwk.de/y"

    def test_row_matches_headers_length(self):
        policy = Policy(
            url="https://example.gov",
            policy_name="Match Test",
            jurisdiction="UK",
            policy_type=PolicyType.DIRECTIVE,
            summary="Length check",
            relevance_score=7,
        )
        assert len(policy.to_sheet_row()) == len(Policy.sheet_headers())


class TestSheetsClient:
    """Test SheetsClient with mocked gspread."""

    def test_append_policies(self):
        """SheetsClient.append_policies calls gspread correctly."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"

        mock_sheet = MagicMock()
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet

        policies = [
            Policy(
                url="https://a.gov/p1",
                policy_name="Policy A",
                jurisdiction="US",
                policy_type=PolicyType.LAW,
                summary="Summary A",
                relevance_score=8,
            ),
            Policy(
                url="https://b.gov/p2",
                policy_name="Policy B",
                jurisdiction="Germany",
                policy_type=PolicyType.REGULATION,
                summary="Summary B",
                relevance_score=6,
            ),
        ]

        count = client.append_policies(policies)

        assert count == 2
        mock_sheet.append_rows.assert_called_once()
        rows = mock_sheet.append_rows.call_args[0][0]
        assert len(rows) == 2
        # URL is the "Link" column (index 10), not column A.
        link_col = STAGING_HEADERS.index("Link")
        assert rows[0][link_col] == "https://a.gov/p1"
        assert rows[1][link_col] == "https://b.gov/p2"

    def test_append_empty_list(self):
        """SheetsClient.append_policies returns 0 for empty list."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)
        assert client.append_policies([]) == 0

    def test_get_existing_urls_reads_link_column(self):
        """get_existing_urls locates the Link column by header, not column A."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)

        link_idx = STAGING_HEADERS.index("Link") + 1  # 1-based
        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = list(STAGING_HEADERS)
        mock_sheet.col_values.return_value = ["Link", "https://a.gov", "https://b.gov"]
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet

        urls = client.get_existing_urls()

        mock_sheet.col_values.assert_called_once_with(link_idx)
        assert urls == {"https://a.gov", "https://b.gov"}
