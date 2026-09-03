"""Tests for the reviewer's-column-to-PolicyStore import (WP-2, ADR-0005).

The sheet is exercised through `--from-csv` against the fixture
(`tests/fixtures/review_column_2026-09-02.csv`, her real 143 rows, verbatim)
and through mocked worksheets for the live-sheet path - no network, no
`.env`, matching the mocking style in test_import_sheet.py.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.config import ConfigLoader
from src.core.models import AppSettings, OutputSettings, Policy, PolicyType
from src.eval.sheet_labels import ReviewLabel
from src.output.import_reviews import (
    Change,
    ImportSummary,
    apply_import,
    import_reviews,
    main,
    plan_import,
)
from src.storage.store import PolicyStore

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "review_column_2026-09-02.csv"
CNDCP_URL = "https://www.climateneutraldatacentre.net/"

# The real fixture's verdict counts (checked against the parser directly,
# not guessed): 32 keep, 88 remove -> 120 decidable; 13 tbd, 9 blank, 1
# unreachable. 32 + 88 + 13 + 9 + 1 = 143.
FIXTURE_DECIDABLE = 120
FIXTURE_TBD = 13
FIXTURE_BLANK = 9
FIXTURE_UNREACHABLE = 1


def _make_policy(url: str, **overrides) -> Policy:
    defaults = dict(
        url=url,
        policy_name="Climate Neutral Data Centre Pact (CNDCP)",
        jurisdiction="EU Member States",
        policy_type=PolicyType.MATCHING_PLATFORM,
        summary="Voluntary industry pact.",
        relevance_score=6,
    )
    defaults.update(overrides)
    return Policy(**defaults)


def _store_with_cndcp(tmp_path) -> PolicyStore:
    store = PolicyStore(data_dir=str(tmp_path))
    store.add_policies([_make_policy(CNDCP_URL)])
    return store


def _audit_lines(tmp_path) -> list[str]:
    audit_file = tmp_path / "logs" / "audit.jsonl"
    if not audit_file.exists():
        return []
    return [line for line in audit_file.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestImportReviewsFixtureIntegration:
    """The fails-today case: her real CNDCP row, read from the fixture CSV,
    must reject the stored policy with her actual reason."""

    @pytest.mark.medium
    def test_the_reviewers_removal_becomes_rejected_with_her_reason(self, tmp_path):
        store = _store_with_cndcp(tmp_path)
        config = ConfigLoader()

        summary = import_reviews(config, store, dry_run=False, from_csv=str(FIXTURE_PATH))

        assert summary.changed == 1
        policies = {p["url"]: p for p in store.get_all()}
        assert policies[CNDCP_URL]["review_status"] == "rejected"
        assert policies[CNDCP_URL]["review_note"] == "private sector initiative"

    @pytest.mark.medium
    def test_second_run_is_idempotent_and_writes_no_further_audit_lines(self, tmp_path):
        store = _store_with_cndcp(tmp_path)
        config = ConfigLoader()

        import_reviews(config, store, dry_run=False, from_csv=str(FIXTURE_PATH))
        lines_after_first = _audit_lines(tmp_path)
        assert len(lines_after_first) == 1

        second = import_reviews(config, store, dry_run=False, from_csv=str(FIXTURE_PATH))

        assert second.changed == 0
        assert _audit_lines(tmp_path) == lines_after_first

    @pytest.mark.medium
    def test_dry_run_against_empty_store_reports_counts_and_writes_nothing(self, tmp_path):
        store = PolicyStore(data_dir=str(tmp_path))
        config = ConfigLoader()

        summary = import_reviews(config, store, dry_run=True, from_csv=str(FIXTURE_PATH))

        assert summary.changed == 0
        assert summary.unmatched == FIXTURE_DECIDABLE  # nothing in the store to match
        assert summary.tbd == FIXTURE_TBD
        assert summary.blank == FIXTURE_BLANK
        assert summary.unreachable == FIXTURE_UNREACHABLE
        assert len(summary.changes) == 0
        assert store.get_all() == []
        assert _audit_lines(tmp_path) == []

    @pytest.mark.medium
    def test_non_dry_run_against_empty_store_still_writes_nothing(self, tmp_path):
        """Every decidable label is unmatched (empty store), so a real run
        and a dry run must produce identical counts and no writes."""
        store = PolicyStore(data_dir=str(tmp_path))
        config = ConfigLoader()

        summary = import_reviews(config, store, dry_run=False, from_csv=str(FIXTURE_PATH))

        assert summary.changed == 0
        assert summary.unmatched == FIXTURE_DECIDABLE
        assert store.get_all() == []
        assert _audit_lines(tmp_path) == []


class TestPlanImportPure:
    """plan_import is pure: no store, no network, just labels + existing
    rows in, Changes out."""

    @pytest.mark.small
    def test_keep_maps_to_keep_status(self):
        labels = [ReviewLabel(url="https://a.gov/x", verdict="keep", categories=(),
                               reason_text="", row_number=2)]
        existing = [{"url": "https://a.gov/x", "review_status": "new"}]

        changes = plan_import(labels, existing, keep_status="reviewed")

        assert changes == [Change(url="https://a.gov/x", from_status="new",
                                   to_status="reviewed", note=None)]

    @pytest.mark.small
    def test_remove_maps_to_rejected_with_her_reason(self):
        labels = [ReviewLabel(url="https://a.gov/x", verdict="remove",
                               categories=("bad_link",), reason_text="link is dead",
                               row_number=2)]
        existing = [{"url": "https://a.gov/x", "review_status": "new"}]

        changes = plan_import(labels, existing, keep_status="reviewed")

        assert changes == [Change(url="https://a.gov/x", from_status="new",
                                   to_status="rejected", note="link is dead")]

    @pytest.mark.small
    def test_remove_with_no_reason_gets_the_placeholder_note(self):
        labels = [ReviewLabel(url="https://a.gov/x", verdict="remove", categories=(),
                               reason_text="", row_number=2)]
        existing = [{"url": "https://a.gov/x", "review_status": "new"}]

        changes = plan_import(labels, existing, keep_status="reviewed")

        assert changes[0].note == "reviewer: no reason given"

    @pytest.mark.small
    def test_promoted_is_never_downgraded_to_reviewed(self):
        labels = [ReviewLabel(url="https://a.gov/x", verdict="keep", categories=(),
                               reason_text="", row_number=2)]
        existing = [{"url": "https://a.gov/x", "review_status": "promoted"}]

        changes = plan_import(labels, existing, keep_status="reviewed")

        assert changes == []

    @pytest.mark.small
    def test_keep_status_promoted_maps_keep_to_promoted(self):
        labels = [ReviewLabel(url="https://a.gov/x", verdict="keep", categories=(),
                               reason_text="", row_number=2)]
        existing = [{"url": "https://a.gov/x", "review_status": "new"}]

        changes = plan_import(labels, existing, keep_status="promoted")

        assert changes == [Change(url="https://a.gov/x", from_status="new",
                                   to_status="promoted", note=None)]

    @pytest.mark.small
    def test_a_row_already_at_the_target_status_with_the_same_note_is_unchanged(self):
        labels = [ReviewLabel(url="https://a.gov/x", verdict="remove",
                               categories=("bad_link",), reason_text="link is dead",
                               row_number=2)]
        existing = [{"url": "https://a.gov/x", "review_status": "rejected",
                     "review_note": "link is dead"}]

        assert plan_import(labels, existing, keep_status="reviewed") == []

    @pytest.mark.small
    def test_tbd_blank_and_unreachable_produce_no_change(self):
        labels = [
            ReviewLabel(url="https://a.gov/1", verdict="tbd", categories=("judgement",),
                        reason_text="hmm", row_number=2),
            ReviewLabel(url="https://a.gov/2", verdict="blank", categories=(),
                        reason_text="", row_number=3),
            ReviewLabel(url="https://a.gov/3", verdict="unreachable", categories=(),
                        reason_text="Not able to access the article", row_number=4),
        ]
        existing = [
            {"url": "https://a.gov/1", "review_status": "new"},
            {"url": "https://a.gov/2", "review_status": "new"},
            {"url": "https://a.gov/3", "review_status": "new"},
        ]

        assert plan_import(labels, existing, keep_status="reviewed") == []

    @pytest.mark.small
    def test_a_url_not_in_the_store_produces_no_change(self):
        labels = [ReviewLabel(url="https://nowhere.gov/x", verdict="remove",
                               categories=("bad_link",), reason_text="dead link",
                               row_number=2)]

        assert plan_import(labels, [], keep_status="reviewed") == []

    @pytest.mark.small
    def test_url_matching_tolerates_a_trailing_slash_difference(self):
        """The label's URL is already normalize_url()'d (read_review_labels);
        the stored URL may carry a trailing slash the sheet's link did not -
        matching must not miss that, and the Change must carry the URL
        exactly as stored so update_review_status's exact match still hits."""
        labels = [ReviewLabel(url="https://a.gov/x", verdict="remove",
                               categories=("bad_link",), reason_text="dead",
                               row_number=2)]
        existing = [{"url": "https://a.gov/x/", "review_status": "new"}]

        changes = plan_import(labels, existing, keep_status="reviewed")

        assert changes == [Change(url="https://a.gov/x/", from_status="new",
                                   to_status="rejected", note="dead")]


class TestApplyImport:
    @pytest.mark.medium
    def test_writes_one_audit_line_per_change(self, tmp_path):
        store = _store_with_cndcp(tmp_path)
        changes = [Change(url=CNDCP_URL, from_status="new", to_status="rejected",
                           note="private sector initiative")]

        count = apply_import(store, changes, data_dir=str(tmp_path))

        assert count == 1
        lines = _audit_lines(tmp_path)
        assert len(lines) == 1
        import json
        event = json.loads(lines[0])
        assert event["event"] == "review_imported"
        assert event["url"] == CNDCP_URL
        assert event["from_status"] == "new"
        assert event["to_status"] == "rejected"
        assert event["source"] == "sheet column AC"

        policies = {p["url"]: p for p in store.get_all()}
        assert policies[CNDCP_URL]["review_status"] == "rejected"

    @pytest.mark.medium
    def test_empty_changes_writes_nothing(self, tmp_path):
        store = _store_with_cndcp(tmp_path)

        count = apply_import(store, [], data_dir=str(tmp_path))

        assert count == 0
        assert _audit_lines(tmp_path) == []


class FakeSheetsClient:
    """Stands in for src.output.sheets.SheetsClient - never touches the network."""

    rows: list[dict] = []
    connect_calls = 0
    constructed_with: list[tuple] = []

    def __init__(self, credentials_b64, spreadsheet_id):
        self.credentials_b64 = credentials_b64
        self.spreadsheet_id = spreadsheet_id
        FakeSheetsClient.constructed_with.append((credentials_b64, spreadsheet_id))

    def connect(self):
        FakeSheetsClient.connect_calls += 1

    def read_staging_rows(self, sheet_name="Staging"):
        return FakeSheetsClient.rows


@pytest.fixture
def sheets_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
    monkeypatch.setenv(
        "GOOGLE_CREDENTIALS",
        "ZmFrZS1jcmVkZW50aWFscy1sb25nLWVub3VnaC10by1wYXNzLXRoZS1sZW5ndGgtY2hlY2s=",
    )
    monkeypatch.setenv("SPREADSHEET_ID", "sheet-of-record")
    monkeypatch.delenv("POLICYSEARCH__OUTPUT__REVIEW_SPREADSHEET_ID", raising=False)
    monkeypatch.setattr("src.output.sheets.SheetsClient", FakeSheetsClient)
    FakeSheetsClient.rows = []
    FakeSheetsClient.connect_calls = 0
    FakeSheetsClient.constructed_with = []
    yield


class TestImportReviewsLiveSheetPath:
    @pytest.mark.medium
    def test_reads_from_review_spreadsheet_id_when_set(self, sheets_env, monkeypatch, tmp_path):
        monkeypatch.setenv("POLICYSEARCH__OUTPUT__REVIEW_SPREADSHEET_ID", "sheet-of-record-copy")
        FakeSheetsClient.rows = []
        store = PolicyStore(data_dir=str(tmp_path))
        config = ConfigLoader()

        import_reviews(config, store, dry_run=True)

        assert FakeSheetsClient.connect_calls == 1
        assert FakeSheetsClient.constructed_with[0][1] == "sheet-of-record-copy"

    @pytest.mark.medium
    def test_falls_back_to_spreadsheet_id_when_review_spreadsheet_id_unset(
        self, sheets_env, tmp_path,
    ):
        FakeSheetsClient.rows = []
        store = PolicyStore(data_dir=str(tmp_path))
        config = ConfigLoader()

        import_reviews(config, store, dry_run=True)

        assert FakeSheetsClient.constructed_with[0][1] == "sheet-of-record"

    @pytest.mark.medium
    def test_explicit_spreadsheet_id_argument_wins_over_settings(
        self, sheets_env, tmp_path,
    ):
        FakeSheetsClient.rows = []
        store = PolicyStore(data_dir=str(tmp_path))
        config = ConfigLoader()

        import_reviews(config, store, dry_run=True, spreadsheet_id="cli-override")

        assert FakeSheetsClient.constructed_with[0][1] == "cli-override"

    @pytest.mark.medium
    def test_not_configured_raises_value_error(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GOOGLE_CREDENTIALS", raising=False)
        monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
        monkeypatch.delenv("SPREADSHEET_ID", raising=False)
        monkeypatch.delenv("POLICYSEARCH__OUTPUT__REVIEW_SPREADSHEET_ID", raising=False)
        store = PolicyStore(data_dir=str(tmp_path))
        config = ConfigLoader()

        with pytest.raises(ValueError, match="not configured"):
            import_reviews(config, store, dry_run=True)


class TestMainCli:
    """CLI argument wiring - import_reviews itself is stubbed here, matching
    test_import_sheet.py's TestMainCLI style."""

    @pytest.mark.small
    def test_dry_run_prints_would_change_and_the_first_ten(self, monkeypatch, capsys):
        fake_summary = ImportSummary(
            changed=2, unchanged=1, unmatched=3, tbd=1, blank=1, unreachable=0,
            changes=[
                Change(url="https://a.gov/1", from_status="new", to_status="rejected",
                       note="bad link"),
                Change(url="https://a.gov/2", from_status="new", to_status="reviewed",
                       note=None),
            ],
        )
        monkeypatch.setattr(
            "src.output.import_reviews.import_reviews", lambda *a, **k: fake_summary,
        )

        code = main(["--dry-run", "--from-csv", str(FIXTURE_PATH)])

        assert code == 0
        out = capsys.readouterr().out
        assert "would change 2 rows" in out
        assert "https://a.gov/1: new -> rejected (bad link)" in out
        assert "https://a.gov/2: new -> reviewed ()" in out
        assert "(dry run" in out

    @pytest.mark.small
    def test_keep_as_flag_is_passed_through(self, monkeypatch):
        captured = {}

        def fake_import_reviews(config, store, **kwargs):
            captured.update(kwargs)
            return ImportSummary()

        monkeypatch.setattr("src.output.import_reviews.import_reviews", fake_import_reviews)
        monkeypatch.setattr("src.output.import_reviews.PolicyStore", lambda data_dir: MagicMock())

        code = main(["--from-csv", str(FIXTURE_PATH), "--keep-as", "promoted", "--dry-run"])

        assert code == 0
        assert captured["keep_status"] == "promoted"
        assert captured["from_csv"] == str(FIXTURE_PATH)

    @pytest.mark.small
    def test_not_configured_returns_one(self, monkeypatch, capsys):
        def fake_import_reviews(config, store, **kwargs):
            raise ValueError("Google Sheets is not configured.")

        monkeypatch.setattr("src.output.import_reviews.import_reviews", fake_import_reviews)
        monkeypatch.setattr("src.output.import_reviews.PolicyStore", lambda data_dir: MagicMock())

        code = main(["--dry-run"])

        assert code == 1
        assert "not configured" in capsys.readouterr().out

    @pytest.mark.small
    def test_add_reason_column_flag_calls_the_sheets_client_and_never_the_importer(
        self, monkeypatch, capsys,
    ):
        called_import = MagicMock()
        monkeypatch.setattr("src.output.import_reviews.import_reviews", called_import)

        fake_client = MagicMock()
        fake_client.add_reason_column.return_value = True
        monkeypatch.setattr(
            "src.output.sheets.SheetsClient", lambda credentials_b64, spreadsheet_id: fake_client,
        )
        monkeypatch.setenv("GOOGLE_CREDENTIALS",
                            "ZmFrZS1jcmVkZW50aWFscy1sb25nLWVub3VnaC10by1wYXNzLXRoZS1sZW5ndGgtY2hlY2s=")
        monkeypatch.setenv("SPREADSHEET_ID", "sheet-of-record")

        code = main(["--add-reason-column"])

        assert code == 0
        assert called_import.call_count == 0
        assert fake_client.connect.call_count == 1
        assert fake_client.add_reason_column.call_count == 1
        assert "Added" in capsys.readouterr().out

    @pytest.mark.small
    def test_add_reason_column_prints_when_already_present(self, monkeypatch, capsys):
        fake_client = MagicMock()
        fake_client.add_reason_column.return_value = False
        monkeypatch.setattr(
            "src.output.sheets.SheetsClient", lambda credentials_b64, spreadsheet_id: fake_client,
        )
        monkeypatch.setenv("GOOGLE_CREDENTIALS",
                            "ZmFrZS1jcmVkZW50aWFscy1sb25nLWVub3VnaC10by1wYXNzLXRoZS1sZW5ndGgtY2hlY2s=")
        monkeypatch.setenv("SPREADSHEET_ID", "sheet-of-record")

        code = main(["--add-reason-column"])

        assert code == 0
        assert "already" in capsys.readouterr().out.lower()


class TestSettingsWiring:
    """AppSettings/OutputSettings carry the WP-2 fields the importer reads."""

    @pytest.mark.small
    def test_default_keep_status_is_reviewed(self):
        assert AppSettings().output.review_keep_status == "reviewed"

    @pytest.mark.small
    def test_default_import_reviews_before_scan_is_false(self):
        assert AppSettings().output.import_reviews_before_scan is False

    @pytest.mark.small
    def test_review_spreadsheet_id_defaults_to_none_on_a_bare_model(self):
        """The bare pydantic model's own default (no ConfigLoader fallback
        applied) - the loader-level fallback is covered in test_config.py."""
        assert OutputSettings(spreadsheet_id="sheet-123").review_spreadsheet_id is None
