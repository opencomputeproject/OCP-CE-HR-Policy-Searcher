"""Tests for Google Sheets integration and Policy sheet methods.

The Staging schema mirrors the OCP "Heat Reuse Policies Database" tab: the
first 13 columns match that tab exactly, followed by PolicyPulse extras.
"""

from datetime import date, datetime
from unittest.mock import MagicMock

import gspread
import pytest

from src.core.models import Policy, PolicyType, VerificationFlag
from src.core.policy_schema import POLICYPULSE_APPENDED_HEADERS, STAGING_HEADERS, to_staging_row
from src.storage.leads import Lead


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
    """Test to_staging_row(), the Staging serialisation."""

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
        row = to_staging_row(policy)

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
        row = to_staging_row(policy)

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
        row = to_staging_row(policy)
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
        row = to_staging_row(policy)
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
        assert len(to_staging_row(policy)) == len(Policy.sheet_headers())


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
        mock_sheet.row_values.return_value = list(STAGING_HEADERS)
        mock_sheet.col_values.return_value = ["Link"]  # no existing URLs
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
        assert mock_sheet.append_rows.call_count == 1
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

    def test_append_policies_dedupes_within_batch(self):
        """Multiple policies sharing one source URL: only the first is kept."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"

        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = list(STAGING_HEADERS)
        mock_sheet.col_values.return_value = ["Link"]  # no existing URLs
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet

        policies = [
            Policy(
                url="https://a.gov/p1",
                policy_name="Policy A (first)",
                jurisdiction="US",
                policy_type=PolicyType.LAW,
                summary="Summary A",
                relevance_score=8,
            ),
            Policy(
                url="https://a.gov/p1",
                policy_name="Policy A (duplicate)",
                jurisdiction="US",
                policy_type=PolicyType.LAW,
                summary="Summary A dup",
                relevance_score=7,
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
        rows = mock_sheet.append_rows.call_args[0][0]
        assert len(rows) == 2
        name_col = STAGING_HEADERS.index("Name")
        assert rows[0][name_col] == "Policy A (first)"

    def test_append_policies_skips_existing_urls(self):
        """Policies whose URL is already on the sheet are not re-appended."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"

        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = list(STAGING_HEADERS)
        mock_sheet.col_values.return_value = ["Link", "https://a.gov/p1"]
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet

        policies = [
            Policy(
                url="https://a.gov/p1",
                policy_name="Already Staged",
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

        assert count == 1
        rows = mock_sheet.append_rows.call_args[0][0]
        assert len(rows) == 1
        link_col = STAGING_HEADERS.index("Link")
        assert rows[0][link_col] == "https://b.gov/p2"

    def test_append_policies_all_duplicates_skips_append_call(self):
        """If every policy is already staged, append_rows is never called."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"

        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = list(STAGING_HEADERS)
        mock_sheet.col_values.return_value = ["Link", "https://a.gov/p1"]
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet

        policies = [
            Policy(
                url="https://a.gov/p1",
                policy_name="Already Staged",
                jurisdiction="US",
                policy_type=PolicyType.LAW,
                summary="Summary A",
                relevance_score=8,
            ),
        ]

        count = client.append_policies(policies)

        assert count == 0
        assert mock_sheet.append_rows.call_count == 0
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

        assert mock_sheet.col_values.call_count == 1
        assert urls == {"https://a.gov", "https://b.gov"}

    def test_read_staging_rows_returns_records(self):
        """read_staging_rows returns gspread's header-keyed records as-is."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)

        records = [
            dict(zip(STAGING_HEADERS, ["Europe", "Germany", "National", "Test Act"] + [""] * 24)),
        ]
        mock_sheet = MagicMock()
        mock_sheet.get_all_records.return_value = records
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet

        rows = client.read_staging_rows()

        mock_spreadsheet.worksheet.assert_called_once_with("Staging")

        assert mock_spreadsheet.worksheet.call_count == 1
        assert mock_sheet.get_all_records.call_count == 1
        assert rows == records

    def test_read_staging_rows_missing_sheet_returns_empty(self):
        """A sheet that doesn't exist yet (brand-new spreadsheet) yields []."""
        try:
            from src.output.sheets import SheetsClient
        except ImportError:
            pytest.skip("gspread not installed")

        client = SheetsClient.__new__(SheetsClient)

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Staging")
        client._spreadsheet = mock_spreadsheet

        assert client.read_staging_rows() == []


@pytest.mark.small
class TestSheetsClientHeaderAlignment:
    """append_policies aligns to whatever header row the sheet actually
    has, appending only the PolicyPulse headers it is missing at the end -
    after any column PolicyPulse did not create, such as the reviewer's
    own - and never moving or renaming an existing header (WP-9a / ADR-0009).
    """

    REVIEWER_HEADER = (
        "Review (Is website trustworthy? Is the policy focused on data center "
        "heat reuse explicitly? Is it duplicative? Is it actually a policy? "
        "Are proposed and enacted policies differentiated?)"
    )

    def _client_with_reviewer_column(self):
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"
        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = list(STAGING_HEADERS) + [self.REVIEWER_HEADER]
        mock_sheet.col_values.return_value = ["Link"]  # no existing URLs
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet
        return client, mock_sheet

    def test_appends_policypulse_headers_after_reviewer_column(self):
        client, mock_sheet = self._client_with_reviewer_column()
        policy = Policy(
            url="https://nl.gov/wet",
            policy_name="Wet collectieve warmte",
            policy_name_en="Collective Heat Act",
            jurisdiction="Netherlands",
            policy_type=PolicyType.LAW,
            summary="s",
            relevance_score=7,
            source_language="Dutch",
        )

        client.append_policies([policy])

        # Header row: the reviewer's column (position 29) is untouched; the
        # two new PolicyPulse headers land at 30 (AD) and 31 (AE).
        assert mock_sheet.update.call_count == 1
        values, cell_range = mock_sheet.update.call_args[0]
        assert values == [["Name (English)", "Read in English"]]
        assert cell_range == "AD1:AE1"

        # Data row aligned to that 31-wide header row.
        rows = mock_sheet.append_rows.call_args[0][0]
        assert len(rows) == 1
        row = rows[0]
        assert len(row) == 31
        assert row[28] == ""                       # position 29: reviewer's column
        assert row[29] == "Collective Heat Act"     # position 30: Name (English)
        assert row[30].startswith("https://nl-gov.translate.goog/wet")  # position 31

    def test_second_call_does_not_append_headers_again(self):
        client, mock_sheet = self._client_with_reviewer_column()
        client.append_policies([
            Policy(
                url="https://nl.gov/wet", policy_name="Wet", jurisdiction="Netherlands",
                policy_type=PolicyType.LAW, summary="s", relevance_score=7,
            ),
        ])
        assert mock_sheet.update.call_count == 1

        # The sheet now actually carries the appended headers.
        mock_sheet.row_values.return_value = (
            list(STAGING_HEADERS) + [self.REVIEWER_HEADER, *POLICYPULSE_APPENDED_HEADERS]
        )
        mock_sheet.col_values.return_value = ["Link"]

        client.append_policies([
            Policy(
                url="https://nl.gov/wet2", policy_name="Wet 2", jurisdiction="Netherlands",
                policy_type=PolicyType.LAW, summary="s", relevance_score=7,
            ),
        ])

        assert mock_sheet.update.call_count == 1  # no second header-writing call
        assert mock_sheet.append_rows.call_count == 2

    def test_existing_headers_are_never_moved_or_renamed(self):
        """A plain sheet with no reviewer column: appending PolicyPulse
        headers must not touch the original 28, in text or in position."""
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"
        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = list(STAGING_HEADERS)
        mock_sheet.col_values.return_value = ["Link"]
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet

        client.append_policies([
            Policy(
                url="https://a.gov/p1", policy_name="Policy A", jurisdiction="US",
                policy_type=PolicyType.LAW, summary="s", relevance_score=8,
            ),
        ])

        values, cell_range = mock_sheet.update.call_args[0]
        assert values == [["Name (English)", "Read in English"]]
        assert cell_range == "AC1:AD1"
        link_col = STAGING_HEADERS.index("Link")
        rows = mock_sheet.append_rows.call_args[0][0]
        assert rows[0][link_col] == "https://a.gov/p1"

    def test_brand_new_sheet_gets_full_header_list(self):
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"
        mock_new_sheet = MagicMock()
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Staging")
        mock_spreadsheet.add_worksheet.return_value = mock_new_sheet
        client._spreadsheet = mock_spreadsheet

        sheet = client.get_staging_sheet()

        assert sheet is mock_new_sheet
        values, cell_range = mock_new_sheet.update.call_args[0]
        assert values == [list(STAGING_HEADERS) + POLICYPULSE_APPENDED_HEADERS]
        assert cell_range == "A1:AD1"  # 28 STAGING_HEADERS + 2 appended = 30 cols


class TestSheetsClientAddReasonColumn:
    """SheetsClient.add_reason_column (WP-2, ADR-0005) - explicit and off by
    default: only ever reached via `python -m src.output.import_reviews
    --add-reason-column`, never by a scan or the schedule runner."""

    REVIEWER_HEADER = (
        "Review (Is website trustworthy? Is the policy focused on data center "
        "heat reuse explicitly? Is it duplicative? Is it actually a policy? "
        "Are proposed and enacted policies differentiated?)"
    )

    def _client(self, header_row, row_count=1000, col_count=None):
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"
        sheet = MagicMock()
        sheet.row_values.return_value = list(header_row)
        sheet.row_count = row_count
        sheet.col_count = col_count if col_count is not None else len(header_row) + 10
        sheet.id = 456
        spreadsheet = MagicMock()
        spreadsheet.worksheet.return_value = sheet
        client._spreadsheet = spreadsheet
        return client, sheet, spreadsheet

    @pytest.mark.small
    def test_adds_header_after_the_reviewers_column_with_dropdown_validation(self):
        from src.eval.sheet_labels import CATEGORIES

        headers = list(STAGING_HEADERS) + [self.REVIEWER_HEADER]  # 29 headers
        client, sheet, spreadsheet = self._client(headers, row_count=1000)

        added = client.add_reason_column()

        assert added is True
        # Header written at column 30 (AD), nowhere else.
        values, cell_range = sheet.update.call_args[0]
        assert values == [["Reason (fixed list)"]]
        assert cell_range == "AD1:AD1"

        # One setDataValidation request, column 30 only, rows 2..1000.
        assert spreadsheet.batch_update.call_count == 1
        body = spreadsheet.batch_update.call_args[0][0]
        requests = body["requests"]
        assert len(requests) == 1
        rule_range = requests[0]["setDataValidation"]["range"]
        assert rule_range["sheetId"] == 456
        assert rule_range["startColumnIndex"] == 29
        assert rule_range["endColumnIndex"] == 30
        assert rule_range["startRowIndex"] == 1
        assert rule_range["endRowIndex"] == 1000
        condition = requests[0]["setDataValidation"]["rule"]["condition"]
        assert condition["type"] == "ONE_OF_LIST"
        assert [v["userEnteredValue"] for v in condition["values"]] == list(CATEGORIES)
        rule = requests[0]["setDataValidation"]["rule"]
        assert rule["showCustomUi"] is True
        assert rule["strict"] is False

    @pytest.mark.small
    def test_every_existing_header_is_untouched(self):
        headers = list(STAGING_HEADERS) + [self.REVIEWER_HEADER]
        client, sheet, _ = self._client(headers, row_count=1000)

        client.add_reason_column()

        # update() is called exactly once, for the new header only - the
        # other 29 headers are never part of any write.
        assert sheet.update.call_count == 1
        values, _ = sheet.update.call_args[0]
        assert values == [["Reason (fixed list)"]]

    @pytest.mark.small
    def test_widens_a_tab_with_no_spare_columns(self):
        headers = list(STAGING_HEADERS) + [self.REVIEWER_HEADER]
        client, sheet, _ = self._client(headers, row_count=1000, col_count=len(headers))

        client.add_reason_column()

        sheet.add_cols.assert_called_once_with(1)


        assert sheet.add_cols.call_count == 1
    @pytest.mark.small
    def test_a_tab_with_a_spare_column_is_not_widened(self):
        headers = list(STAGING_HEADERS) + [self.REVIEWER_HEADER]
        client, sheet, _ = self._client(headers, row_count=1000, col_count=len(headers) + 5)

        client.add_reason_column()

        assert sheet.add_cols.call_count == 0
    @pytest.mark.small
    def test_returns_false_and_changes_nothing_when_header_already_present(self):
        headers = list(STAGING_HEADERS) + [self.REVIEWER_HEADER, "Reason (fixed list)"]
        client, sheet, spreadsheet = self._client(headers, row_count=1000)

        added = client.add_reason_column()

        assert added is False
        assert sheet.update.call_count == 0
        assert sheet.add_cols.call_count == 0
        assert spreadsheet.batch_update.call_count == 0
    @pytest.mark.small
    def test_header_match_is_stripped_and_case_insensitive(self):
        headers = list(STAGING_HEADERS) + [self.REVIEWER_HEADER, "reason (FIXED LIST) "]
        client, sheet, spreadsheet = self._client(headers, row_count=1000)

        added = client.add_reason_column()

        assert added is False
        assert sheet.update.call_count == 0
    @pytest.mark.small
    def test_custom_sheet_name_header_and_options_are_honoured(self):
        client, sheet, spreadsheet = self._client(["A", "B"], row_count=50)

        added = client.add_reason_column(
            sheet_name="Other", header="My Reason", options=("x", "y"),
        )

        spreadsheet.worksheet.assert_called_once_with("Other")

        assert spreadsheet.worksheet.call_count == 1
        assert added is True
        values, cell_range = sheet.update.call_args[0]
        assert values == [["My Reason"]]
        assert cell_range == "C1:C1"
        requests = spreadsheet.batch_update.call_args[0][0]["requests"]
        condition = requests[0]["setDataValidation"]["rule"]["condition"]
        assert [v["userEnteredValue"] for v in condition["values"]] == ["x", "y"]


class TestSheetsClientUpdateReviewStatuses:
    """SheetsClient.update_review_statuses — one-way (app -> sheet), URL-matched
    batch write to the Review Status column. Used by the scan-end
    reconciliation pass (src/orchestration/scan_manager.py) to reflect a
    rejected policy's status onto its Staging row."""

    def _client_with_rows(self, urls):
        """A fake worksheet whose Link column holds `urls` in row order."""
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"
        mock_sheet = MagicMock()
        mock_sheet.row_values.return_value = list(STAGING_HEADERS)
        mock_sheet.col_values.return_value = ["Link", *urls]
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet
        return client, mock_sheet

    def test_matching_row_gets_rejected_status(self):
        client, mock_sheet = self._client_with_rows(["https://a.gov/p1", "https://b.gov/p2"])

        count = client.update_review_statuses({"https://a.gov/p1": "rejected"})

        assert count == 1
        assert mock_sheet.batch_update.call_count == 1
        updates = mock_sheet.batch_update.call_args[0][0]
        assert len(updates) == 1
        review_col = STAGING_HEADERS.index("Review Status") + 1
        expected_range = gspread.utils.rowcol_to_a1(2, review_col)  # row 2 = first data row
        assert updates[0]["range"] == expected_range
        assert updates[0]["values"] == [["rejected"]]

    def test_non_matching_rows_untouched(self):
        client, mock_sheet = self._client_with_rows(
            ["https://a.gov/p1", "https://b.gov/p2", "https://c.gov/p3"]
        )

        count = client.update_review_statuses({"https://b.gov/p2": "rejected"})

        assert count == 1
        updates = mock_sheet.batch_update.call_args[0][0]
        assert len(updates) == 1
        review_col = STAGING_HEADERS.index("Review Status") + 1
        expected_range = gspread.utils.rowcol_to_a1(3, review_col)  # row 3 = second data row
        assert updates[0]["range"] == expected_range

    def test_multiple_matches_batched_in_one_call(self):
        client, mock_sheet = self._client_with_rows(
            ["https://a.gov/p1", "https://b.gov/p2", "https://c.gov/p3"]
        )

        count = client.update_review_statuses(
            {"https://a.gov/p1": "rejected", "https://c.gov/p3": "rejected"}
        )

        assert count == 2
        assert mock_sheet.batch_update.call_count == 1
        updates = mock_sheet.batch_update.call_args[0][0]
        assert len(updates) == 2

    def test_url_not_on_sheet_is_tolerated_not_an_error(self):
        client, mock_sheet = self._client_with_rows(["https://a.gov/p1"])

        count = client.update_review_statuses({"https://nope.gov/x": "rejected"})

        assert count == 0
        assert mock_sheet.batch_update.call_count == 0
    def test_empty_input_returns_zero_without_touching_the_sheet(self):
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        assert client.update_review_statuses({}) == 0

    def test_missing_worksheet_returns_zero(self):
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Staging")
        client._spreadsheet = mock_spreadsheet

        assert client.update_review_statuses({"https://a.gov/p1": "rejected"}) == 0


class TestSheetsClientExportTips:
    """SheetsClient.export_tips — one-way batch export to the Tips worksheet."""

    def _client_with_sheet(self, existing=True):
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"
        mock_sheet = MagicMock()
        mock_spreadsheet = MagicMock()
        if existing:
            mock_spreadsheet.worksheet.return_value = mock_sheet
        else:
            mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Tips")
            mock_spreadsheet.add_worksheet.return_value = mock_sheet
        client._spreadsheet = mock_spreadsheet
        return client, mock_sheet, mock_spreadsheet

    def test_creates_worksheet_when_absent(self):
        try:
            from src.output.sheets import TIP_HEADERS
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, mock_spreadsheet = self._client_with_sheet(existing=False)

        client.export_tips([])

        assert mock_spreadsheet.add_worksheet.call_count == 1
        _, kwargs = mock_spreadsheet.add_worksheet.call_args
        assert kwargs["cols"] == len(TIP_HEADERS)

    def test_reuses_existing_worksheet(self):
        try:
            from src.output.sheets import SheetsClient  # noqa: F401
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, mock_spreadsheet = self._client_with_sheet(existing=True)

        client.export_tips([])

        assert mock_spreadsheet.add_worksheet.call_count == 0
        mock_spreadsheet.worksheet.assert_called_with("Tips")
        assert mock_spreadsheet.worksheet.call_count == 1
        assert mock_spreadsheet.add_worksheet.call_count == 0
        assert mock_spreadsheet.worksheet.call_count == 1

    def test_exports_expected_columns(self):
        try:
            from src.output.sheets import TIP_HEADERS
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, _ = self._client_with_sheet(existing=True)

        lead = Lead(
            title="Denmark heat mandate",
            source_url="https://news.example/article",
            snippet="A note",
            origin="community",
            status="new",
            found_at=datetime(2026, 7, 20, 9, 0, 0),
        )

        count = client.export_tips([lead])

        assert count == 1
        assert mock_sheet.update.call_count == 1
        values, _range = mock_sheet.update.call_args[0]
        assert values[0] == TIP_HEADERS
        row = values[1]
        assert row[TIP_HEADERS.index("Submitted At")] == "2026-07-20T09:00:00"
        assert row[TIP_HEADERS.index("Origin")] == "community"
        assert row[TIP_HEADERS.index("Title/Note")] == "Denmark heat mandate"
        assert row[TIP_HEADERS.index("URL")] == "https://news.example/article"
        assert row[TIP_HEADERS.index("Status")] == "new"
        assert row[TIP_HEADERS.index("Chase Outcome")] == ""

    def test_chase_outcome_no_policy(self):
        try:
            from src.output.sheets import TIP_HEADERS
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, _ = self._client_with_sheet(existing=True)

        lead = Lead(
            title="t", source_url="https://a.gov/x", status="chased",
            chase_outcome="no_policy",
        )
        client.export_tips([lead])

        row = mock_sheet.update.call_args[0][0][1]
        assert "nothing found" in row[TIP_HEADERS.index("Chase Outcome")].lower()

    def test_chase_outcome_policy_found_links_the_policy(self):
        try:
            from src.output.sheets import TIP_HEADERS
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, _ = self._client_with_sheet(existing=True)

        lead = Lead(
            title="t", source_url="https://a.gov/x", status="chased",
            policy_url="https://a.gov/x-final", chase_outcome="policy_found",
        )
        client.export_tips([lead])

        row = mock_sheet.update.call_args[0][0][1]
        assert "https://a.gov/x-final" in row[TIP_HEADERS.index("Chase Outcome")]

    def test_chase_outcome_fetch_failed(self):
        try:
            from src.output.sheets import TIP_HEADERS
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, _ = self._client_with_sheet(existing=True)

        lead = Lead(
            title="t", source_url="https://a.gov/x", status="new",
            chase_outcome="fetch_failed", chase_error="too many redirects",
        )
        client.export_tips([lead])

        row = mock_sheet.update.call_args[0][0][1]
        assert "too many redirects" in row[TIP_HEADERS.index("Chase Outcome")]

    def test_note_only_tip_url_column_empty(self):
        try:
            from src.output.sheets import TIP_HEADERS
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, _ = self._client_with_sheet(existing=True)

        lead = Lead(title="Rumor", source_url="", snippet="Heard something", origin="community")
        client.export_tips([lead])

        row = mock_sheet.update.call_args[0][0][1]
        assert row[TIP_HEADERS.index("URL")] == ""
        assert row[TIP_HEADERS.index("Title/Note")] == "Rumor"

    def test_empty_queue_clears_sheet_to_just_headers(self):
        try:
            from src.output.sheets import TIP_HEADERS
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, _ = self._client_with_sheet(existing=True)

        count = client.export_tips([])

        assert count == 0
        assert mock_sheet.clear.call_count == 1
        values, _range = mock_sheet.update.call_args[0]
        assert values == [TIP_HEADERS]

    def test_export_is_full_snapshot_not_append(self):
        """Re-export must not accumulate duplicate rows from prior calls —
        it clears and rewrites the whole sheet every time."""
        try:
            from src.output.sheets import SheetsClient  # noqa: F401
        except ImportError:
            pytest.skip("gspread not installed")
        client, mock_sheet, _ = self._client_with_sheet(existing=True)

        lead = Lead(title="t", source_url="https://a.gov/x")
        client.export_tips([lead])
        client.export_tips([lead])

        assert mock_sheet.clear.call_count == 2
        assert mock_sheet.append_rows.call_count == 0
class TestHeaderAlignmentAgainstARealTab:
    """Two things a MagicMock sheet cannot teach on its own (ADR-0009).

    A hand-typed header keeps its trailing space or its capitals, and the
    Sheets API refuses any write past the tab's last column. Both were
    found by reading the sheet of record, whose Staging tab is exactly as
    wide as its last column.
    """

    REVIEWER_HEADER = "Review (Is website trustworthy? Is it actually a policy?)"

    def _client(self, header_row, col_count):
        from src.output.sheets import SheetsClient

        client = SheetsClient.__new__(SheetsClient)
        client.spreadsheet_id = "test-id"
        sheet = MagicMock()
        sheet.row_values.return_value = list(header_row)
        sheet.col_values.return_value = ["Link"]
        sheet.col_count = col_count
        spreadsheet = MagicMock()
        spreadsheet.worksheet.return_value = sheet
        client._spreadsheet = spreadsheet
        return client, sheet

    @pytest.mark.small
    def test_a_tab_as_wide_as_its_reviewer_column_is_widened_before_the_headers_are_written(self):
        from src.core.policy_schema import POLICYPULSE_APPENDED_HEADERS

        headers = list(STAGING_HEADERS) + [self.REVIEWER_HEADER]
        client, sheet = self._client(headers, col_count=len(headers))
        client._ensure_policypulse_headers(sheet)
        sheet.add_cols.assert_called_once_with(len(POLICYPULSE_APPENDED_HEADERS))
        assert sheet.add_cols.call_count == 1
        written = sheet.update.call_args[0][0][0]
        assert written == list(POLICYPULSE_APPENDED_HEADERS)

    @pytest.mark.small
    def test_a_tab_with_spare_columns_is_not_widened(self):
        headers = list(STAGING_HEADERS) + [self.REVIEWER_HEADER]
        client, sheet = self._client(headers, col_count=len(headers) + 10)
        client._ensure_policypulse_headers(sheet)
        assert sheet.add_cols.call_count == 0

    @pytest.mark.small
    def test_a_hand_typed_header_with_a_trailing_space_still_receives_its_value(self):
        from src.core.policy_schema import POLICYPULSE_APPENDED_HEADERS
        from src.output.sheets import SheetsClient

        headers = [("Name " if h == "Name" else h) for h in STAGING_HEADERS]
        headers += ["name (english) "]  # already there, typed by hand, wrong case
        client, sheet = self._client(headers, col_count=len(headers) + 5)
        result = client._ensure_policypulse_headers(sheet)
        assert result[-2] == "name (english) "  # recognised in place, Read in English appended after
        assert "Name (English)" not in result, "recognised, so not appended twice"
        assert result.count("Read in English") == 1
        policy = Policy(
            url="https://example.nl/warmte", policy_name="Wet collectieve warmte",
            policy_name_en="Collective Heat Act", jurisdiction="Netherlands",
            policy_type=PolicyType.LAW, summary="s", relevance_score=7,
            source_language="nl",
        )
        row = SheetsClient._aligned_row(policy, result)
        assert row[headers.index("Name ")] == "Wet collectieve warmte"
        assert row[result.index("name (english) ")] == "Collective Heat Act"
        assert len(POLICYPULSE_APPENDED_HEADERS) == 2

