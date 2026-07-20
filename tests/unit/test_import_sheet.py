"""Tests for the Staging-sheet-to-PolicyStore import command.

gspread is mocked via a FakeSheetsClient standing in for
src.output.sheets.SheetsClient (imported lazily inside import_from_sheet),
matching the mocking style in tests/unit/test_sheets.py: no network calls.
"""

import pytest

from src.core.models import Policy, PolicyType
from src.core.policy_schema import STAGING_HEADERS
from src.output.import_sheet import ImportSummary, import_from_sheet, main, map_row_to_policy
from src.storage.store import PolicyStore


def _make_policy(url: str = "https://a.gov/p1", **overrides) -> Policy:
    defaults = dict(
        url=url,
        policy_name="Test Policy",
        jurisdiction="Germany",
        policy_type=PolicyType.LAW,
        summary="A test policy",
        relevance_score=7,
    )
    defaults.update(overrides)
    return Policy(**defaults)


def _row(policy: Policy) -> dict:
    """Header-keyed row dict, matching what gspread's get_all_records() returns."""
    return dict(zip(STAGING_HEADERS, policy.to_sheet_row()))


class FakeSheetsClient:
    """Stands in for src.output.sheets.SheetsClient — never touches the network."""

    rows: list[dict] = []
    connect_calls = 0

    def __init__(self, credentials_b64, spreadsheet_id):
        self.credentials_b64 = credentials_b64
        self.spreadsheet_id = spreadsheet_id

    def connect(self):
        FakeSheetsClient.connect_calls += 1

    def read_staging_rows(self, sheet_name="Staging"):
        return FakeSheetsClient.rows


@pytest.fixture
def sheets_env(monkeypatch):
    """Configure Sheets as reachable, backed by FakeSheetsClient."""
    monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
    monkeypatch.setenv(
        "GOOGLE_CREDENTIALS",
        "ZmFrZS1jcmVkZW50aWFscy1sb25nLWVub3VnaC10by1wYXNzLXRoZS1sZW5ndGgtY2hlY2s=",
    )
    monkeypatch.setenv("SPREADSHEET_ID", "sheet-123")
    monkeypatch.setattr("src.output.sheets.SheetsClient", FakeSheetsClient)
    FakeSheetsClient.rows = []
    FakeSheetsClient.connect_calls = 0
    yield


class TestMapRowToPolicy:
    def test_valid_row_maps(self):
        policy = _make_policy(jurisdiction="Germany")
        mapped = map_row_to_policy(_row(policy), row_number=2)
        assert mapped.url == policy.url
        assert mapped.policy_name == policy.policy_name
        assert mapped.policy_type == PolicyType.LAW
        assert mapped.relevance_score == 7
        assert mapped.jurisdiction == "Germany"

    def test_missing_url_raises_with_row_number(self):
        row = _row(_make_policy())
        row["Link"] = ""
        with pytest.raises(ValueError, match=r"row 5.*missing URL"):
            map_row_to_policy(row, row_number=5)

    def test_non_web_url_scheme_rejected(self):
        """The URL becomes a clickable href for every visitor - a curator
        sheet cell must not be able to smuggle a javascript: link through."""
        row = _row(_make_policy())
        row["Link"] = "javascript:alert(1)"
        with pytest.raises(ValueError, match=r"row 7.*http"):
            map_row_to_policy(row, row_number=7)

    def test_missing_name_raises_with_row_number(self):
        row = _row(_make_policy())
        row["Name"] = ""
        with pytest.raises(ValueError, match=r"row 3.*missing Name"):
            map_row_to_policy(row, row_number=3)

    def test_invalid_relevance_score_raises(self):
        row = _row(_make_policy())
        row["Relevance Score"] = "not-a-number"
        with pytest.raises(ValueError, match="row 4"):
            map_row_to_policy(row, row_number=4)

    def test_unknown_extra_column_tolerated(self):
        policy = _make_policy()
        row = _row(policy)
        row["Some Future Column"] = "unused"
        mapped = map_row_to_policy(row, row_number=2)
        assert mapped.url == policy.url


class TestImportFromSheet:
    def test_imports_valid_rows(self, sheets_env, tmp_path):
        FakeSheetsClient.rows = [
            _row(_make_policy("https://a.gov/1")),
            _row(_make_policy("https://b.gov/2")),
        ]
        summary = import_from_sheet(data_dir=str(tmp_path))

        assert summary.rows_read == 2
        assert summary.imported == 2
        assert summary.duplicates == 0
        assert summary.invalid == 0
        assert summary.invalid_rows == []
        assert FakeSheetsClient.connect_calls == 1

        store = PolicyStore(data_dir=str(tmp_path))
        assert len(store.get_all()) == 2

    def test_invalid_row_skipped_and_reported(self, sheets_env, tmp_path):
        bad_row = _row(_make_policy("https://a.gov/1"))
        bad_row["Link"] = ""
        FakeSheetsClient.rows = [bad_row, _row(_make_policy("https://b.gov/2"))]

        summary = import_from_sheet(data_dir=str(tmp_path))

        assert summary.rows_read == 2
        assert summary.imported == 1
        assert summary.invalid == 1
        assert summary.invalid_rows == [2]  # row 1 is the header

        store = PolicyStore(data_dir=str(tmp_path))
        assert len(store.get_all()) == 1

    def test_idempotent_second_run_imports_zero_new(self, sheets_env, tmp_path):
        FakeSheetsClient.rows = [_row(_make_policy("https://a.gov/1"))]

        first = import_from_sheet(data_dir=str(tmp_path))
        second = import_from_sheet(data_dir=str(tmp_path))

        assert first.imported == 1
        assert first.duplicates == 0
        assert second.imported == 0
        assert second.duplicates == 1

        store = PolicyStore(data_dir=str(tmp_path))
        assert len(store.get_all()) == 1

    def test_dry_run_writes_nothing(self, sheets_env, tmp_path):
        FakeSheetsClient.rows = [_row(_make_policy("https://a.gov/1"))]

        summary = import_from_sheet(data_dir=str(tmp_path), dry_run=True)

        assert summary.imported == 1
        assert summary.duplicates == 0
        store = PolicyStore(data_dir=str(tmp_path))
        assert store.get_all() == []

    def test_dry_run_previews_duplicates_without_writing(self, sheets_env, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        store.add_policies([_make_policy("https://a.gov/1")])
        FakeSheetsClient.rows = [
            _row(_make_policy("https://a.gov/1")),
            _row(_make_policy("https://b.gov/2")),
        ]

        summary = import_from_sheet(data_dir=str(tmp_path), dry_run=True)

        assert summary.imported == 1
        assert summary.duplicates == 1
        store2 = PolicyStore(data_dir=str(tmp_path))
        assert len(store2.get_all()) == 1  # unchanged

    def test_empty_sheet_returns_zeroed_summary(self, sheets_env, tmp_path):
        FakeSheetsClient.rows = []
        summary = import_from_sheet(data_dir=str(tmp_path))
        assert summary.rows_read == 0
        assert summary.imported == 0
        assert summary.duplicates == 0
        assert summary.invalid == 0

    def test_not_configured_raises_value_error(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GOOGLE_CREDENTIALS", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("SPREADSHEET_ID", raising=False)

        with pytest.raises(ValueError, match="not configured"):
            import_from_sheet(data_dir=str(tmp_path))


class TestMainCLI:
    """CLI argument wiring — import_from_sheet itself is stubbed here."""

    def test_prints_summary_and_returns_zero(self, monkeypatch, capsys):
        fake_summary = ImportSummary(
            rows_read=3, imported=2, duplicates=1, invalid=0, invalid_rows=[],
        )
        monkeypatch.setattr(
            "src.output.import_sheet.import_from_sheet", lambda **kwargs: fake_summary,
        )

        code = main([])

        assert code == 0
        out = capsys.readouterr().out
        assert "Rows read from Staging: 3" in out
        assert "Imported new: 2" in out
        assert "Duplicates skipped: 1" in out
        assert "Invalid skipped: 0" in out

    def test_reports_invalid_row_numbers(self, monkeypatch, capsys):
        fake_summary = ImportSummary(
            rows_read=2, imported=1, duplicates=0, invalid=1, invalid_rows=[3],
        )
        monkeypatch.setattr(
            "src.output.import_sheet.import_from_sheet", lambda **kwargs: fake_summary,
        )

        main([])

        assert "Invalid row numbers: 3" in capsys.readouterr().out

    def test_dry_run_and_data_dir_flags_passed_through(self, monkeypatch, tmp_path, capsys):
        captured = {}

        def fake_import(**kwargs):
            captured.update(kwargs)
            return ImportSummary()

        monkeypatch.setattr("src.output.import_sheet.import_from_sheet", fake_import)

        code = main(["--dry-run", "--data-dir", str(tmp_path)])

        assert code == 0
        assert captured["dry_run"] is True
        assert captured["data_dir"] == str(tmp_path)
        assert "dry run" in capsys.readouterr().out

    def test_not_configured_returns_one(self, monkeypatch, capsys):
        def fake_import(**kwargs):
            raise ValueError("Google Sheets is not configured — set GOOGLE_CREDENTIALS.")

        monkeypatch.setattr("src.output.import_sheet.import_from_sheet", fake_import)

        code = main([])

        assert code == 1
        assert "not configured" in capsys.readouterr().out
