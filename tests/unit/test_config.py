import pytest


@pytest.mark.small
def test_new_zealand_is_a_valid_region():
    """The NZ PCO source's region must validate (registry has had the row
    since the wave-1 sources PR; VALID_REGIONS lagged behind it)."""
    from src.core.config import VALID_REGIONS
    assert "new_zealand" in VALID_REGIONS


class TestYamlLoader:
    """_load_yaml goes through libyaml's C parser when the build has it."""

    @pytest.mark.small
    def test_the_c_loader_is_used_when_libyaml_is_present(self):
        import yaml

        from src.core import config

        if not yaml.__with_libyaml__:
            pytest.skip("this PyYAML build has no libyaml; SafeLoader fallback applies")
        assert config._YAML_LOADER is yaml.CSafeLoader

    @pytest.mark.small
    def test_every_config_file_reads_identically_under_both_parsers(self):
        """The speed-up is only free if the two parsers agree on every file
        the app actually loads - not a sample, all of them."""
        from pathlib import Path

        import yaml

        from src.core.config import _load_yaml

        files = sorted((Path(__file__).resolve().parents[2] / "config").rglob("*.yaml"))
        assert files, "no config files found - wrong repo root?"
        for path in files:
            pure = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader) or {}
            assert _load_yaml(path) == pure, path.name


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
