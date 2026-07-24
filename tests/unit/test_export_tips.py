"""Tests for the LeadStore-to-Sheets tip export command.

gspread is mocked via a FakeSheetsClient standing in for
src.output.sheets.SheetsClient (imported lazily inside export_tips_to_sheet),
matching the mocking style in tests/unit/test_import_sheet.py: no network.
"""

import pytest

from src.output.export_tips import ExportSummary, export_tips_to_sheet, main
from src.storage.leads import Lead, LeadStore


class FakeSheetsClient:
    """Stands in for src.output.sheets.SheetsClient — never touches the network."""

    connect_calls = 0
    exported_leads: list = []
    exported_sheet_name = None

    def __init__(self, credentials_b64, spreadsheet_id):
        self.credentials_b64 = credentials_b64
        self.spreadsheet_id = spreadsheet_id

    def connect(self):
        FakeSheetsClient.connect_calls += 1

    def export_tips(self, leads, sheet_name="Tips"):
        FakeSheetsClient.exported_leads = list(leads)
        FakeSheetsClient.exported_sheet_name = sheet_name
        return len(leads)


@pytest.fixture
def sheets_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
    monkeypatch.setenv(
        "GOOGLE_CREDENTIALS",
        "ZmFrZS1jcmVkZW50aWFscy1sb25nLWVub3VnaC10by1wYXNzLXRoZS1sZW5ndGgtY2hlY2s=",
    )
    monkeypatch.setenv("SPREADSHEET_ID", "sheet-123")
    monkeypatch.setattr("src.output.sheets.SheetsClient", FakeSheetsClient)
    FakeSheetsClient.connect_calls = 0
    FakeSheetsClient.exported_leads = []
    FakeSheetsClient.exported_sheet_name = None
    yield


class TestExportTipsToSheet:
    def test_exports_all_queued_tips(self, sheets_env, tmp_path):
        store = LeadStore(data_dir=str(tmp_path))
        store.add_leads([
            Lead(title="A", source_url="https://a.gov/1"),
            Lead(title="B", source_url="https://b.gov/2"),
        ])

        summary = export_tips_to_sheet(data_dir=str(tmp_path))

        assert summary.total_tips == 2
        assert summary.exported == 2
        assert FakeSheetsClient.connect_calls == 1
        assert len(FakeSheetsClient.exported_leads) == 2

    def test_default_sheet_name_is_tips(self, sheets_env, tmp_path):
        LeadStore(data_dir=str(tmp_path))
        export_tips_to_sheet(data_dir=str(tmp_path))
        assert FakeSheetsClient.exported_sheet_name == "Tips"

    def test_sheet_name_override(self, sheets_env, tmp_path):
        LeadStore(data_dir=str(tmp_path))
        export_tips_to_sheet(data_dir=str(tmp_path), sheet_name="TipsStaging")
        assert FakeSheetsClient.exported_sheet_name == "TipsStaging"

    def test_empty_queue_exports_zero(self, sheets_env, tmp_path):
        LeadStore(data_dir=str(tmp_path))
        summary = export_tips_to_sheet(data_dir=str(tmp_path))
        assert summary.total_tips == 0
        assert summary.exported == 0

    def test_not_configured_raises_value_error(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GOOGLE_CREDENTIALS", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("SPREADSHEET_ID", raising=False)

        with pytest.raises(ValueError, match="not configured"):
            export_tips_to_sheet(data_dir=str(tmp_path))


class TestExportTipsCLI:
    """CLI argument wiring — export_tips_to_sheet itself is stubbed here."""

    def test_prints_summary_and_returns_zero(self, monkeypatch, capsys):
        fake_summary = ExportSummary(total_tips=5, exported=5)
        monkeypatch.setattr(
            "src.output.export_tips.export_tips_to_sheet", lambda **kwargs: fake_summary,
        )

        code = main([])

        assert code == 0
        out = capsys.readouterr().out
        assert "Tips in queue: 5" in out
        assert "Exported to sheet: 5" in out

    def test_data_dir_and_sheet_name_flags_passed_through(self, monkeypatch, tmp_path):
        captured = {}

        def fake_export(**kwargs):
            captured.update(kwargs)
            return ExportSummary()

        monkeypatch.setattr("src.output.export_tips.export_tips_to_sheet", fake_export)

        code = main(["--data-dir", str(tmp_path), "--sheet-name", "TipsStaging"])

        assert code == 0
        assert captured["data_dir"] == str(tmp_path)
        assert captured["sheet_name"] == "TipsStaging"

    def test_not_configured_returns_one(self, monkeypatch, capsys):
        def fake_export(**kwargs):
            raise ValueError("Google Sheets is not configured — set GOOGLE_CREDENTIALS.")

        monkeypatch.setattr("src.output.export_tips.export_tips_to_sheet", fake_export)

        code = main([])

        assert code == 1
        assert "not configured" in capsys.readouterr().out
