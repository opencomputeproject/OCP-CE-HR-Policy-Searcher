import pytest


def test_new_zealand_is_a_valid_region():
    """The NZ PCO source's region must validate (registry has had the row
    since the wave-1 sources PR; VALID_REGIONS lagged behind it)."""
    from src.core.config import VALID_REGIONS
    assert "new_zealand" in VALID_REGIONS


class TestReviewSpreadsheetIdFallback:
    """output.review_spreadsheet_id (WP-2, ADR-0005): falls back to
    spreadsheet_id when unset, and the POLICYSEARCH__OUTPUT__... env
    override wins over both the yaml value and that fallback."""

    @pytest.mark.small
    def test_falls_back_to_spreadsheet_id_when_unset(self, monkeypatch):
        from src.core.config import ConfigLoader

        monkeypatch.setenv("SPREADSHEET_ID", "sheet-of-record-123")
        monkeypatch.delenv("POLICYSEARCH__OUTPUT__REVIEW_SPREADSHEET_ID", raising=False)

        settings = ConfigLoader().settings

        assert settings.output.spreadsheet_id == "sheet-of-record-123"
        assert settings.output.review_spreadsheet_id == "sheet-of-record-123"

    @pytest.mark.small
    def test_env_override_wins_over_the_fallback(self, monkeypatch):
        from src.core.config import ConfigLoader

        monkeypatch.setenv("SPREADSHEET_ID", "sheet-of-record-123")
        monkeypatch.setenv(
            "POLICYSEARCH__OUTPUT__REVIEW_SPREADSHEET_ID", "sheet-of-record-copy-456",
        )

        settings = ConfigLoader().settings

        assert settings.output.spreadsheet_id == "sheet-of-record-123"
        assert settings.output.review_spreadsheet_id == "sheet-of-record-copy-456"

    @pytest.mark.small
    def test_neither_set_leaves_both_none(self, monkeypatch):
        from src.core.config import ConfigLoader

        monkeypatch.delenv("SPREADSHEET_ID", raising=False)
        monkeypatch.delenv("POLICYSEARCH__OUTPUT__REVIEW_SPREADSHEET_ID", raising=False)

        settings = ConfigLoader().settings

        assert settings.output.spreadsheet_id is None
        assert settings.output.review_spreadsheet_id is None


class TestOutputSettingsWP2Defaults:
    @pytest.mark.small
    def test_import_reviews_before_scan_defaults_false(self):
        from src.core.config import ConfigLoader

        settings = ConfigLoader().settings

        assert settings.output.import_reviews_before_scan is False

    @pytest.mark.small
    def test_review_keep_status_defaults_reviewed(self):
        from src.core.config import ConfigLoader

        settings = ConfigLoader().settings

        assert settings.output.review_keep_status == "reviewed"
