"""Tests for Google Sheets integration and Policy sheet methods."""

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from src.core.models import Policy, PolicyType, VerificationFlag


class TestPolicySheetHeaders:
    """Test Policy.sheet_headers()."""

    def test_header_count(self):
        headers = Policy.sheet_headers()
        assert len(headers) == 19

    def test_header_order(self):
        headers = Policy.sheet_headers()
        assert headers[0] == "URL"
        assert headers[1] == "Policy Name"
        assert headers[5] == "Relevance Score"
        assert headers[14] == "Scan ID"
        assert headers[15] == "Domain ID"
        assert headers[16] == "Verification Flags"
        assert headers[17] == "Referenced Policies"
        assert headers[18] == "Referenced URLs"

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
            verification_flags=[VerificationFlag.GENERIC_NAME],
        )
        row = policy.to_sheet_row()

        assert len(row) == 19
        assert row[0] == "https://example.gov/policy"
        assert row[1] == "Test Act"
        assert row[2] == "Germany"
        assert row[3] == "law"
        assert row[4] == "A test law"
        assert row[5] == 9
        assert row[6] == "German"
        assert row[7] == "2024-03-01"
        assert row[8] == "EnEfG-2024"
        assert row[9] == "Must reuse heat"
        assert row[10] == "2024-06-15T10:30:00"
        assert row[11] == "success"
        assert row[12] == ""  # error_details is None
        assert row[13] == "new"
        assert row[14] == "scan_123"
        assert row[15] == "bmwk_de"
        assert row[16] == "generic_name"
        assert row[17] == ""  # referenced_policies (empty)
        assert row[18] == ""  # referenced_urls (empty)

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

        assert len(row) == 19
        assert row[7] == ""   # effective_date
        assert row[8] == ""   # bill_number
        assert row[9] == ""   # key_requirements
        assert row[12] == ""  # error_details
        assert row[14] == ""  # scan_id
        assert row[15] == ""  # domain_id
        assert row[16] == ""  # verification_flags
        assert row[17] == ""  # referenced_policies
        assert row[18] == ""  # referenced_urls

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
        assert row[16] == "jurisdiction_mismatch, future_date"

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
                jurisdiction="DE",
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
        assert rows[0][0] == "https://a.gov/p1"
        assert rows[1][0] == "https://b.gov/p2"

    def test_append_empty_list(self):
        """SheetsClient.append_policies returns 0 for empty list."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)
        assert client.append_policies([]) == 0

    def test_get_existing_urls(self):
        """SheetsClient.get_existing_urls returns URL set."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)

        mock_sheet = MagicMock()
        mock_sheet.col_values.return_value = ["URL", "https://a.gov", "https://b.gov"]
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet

        urls = client.get_existing_urls()
        assert urls == {"https://a.gov", "https://b.gov"}
