"""Tests for the source diagnostic (src/sources/check.py)."""

from src.sources import SOURCE_REGISTRY
from src.sources.check import source_key_status


class TestSourceKeyStatus:
    def test_reports_every_registered_source(self):
        rows = source_key_status()
        ids = {r["id"] for r in rows}
        assert ids == set(SOURCE_REGISTRY)

    def test_keyless_sources_need_no_key(self):
        rows = {r["id"]: r for r in source_key_status()}
        # riksdagen/uk_bills/etc. declare no api_key_env
        assert rows["riksdagen"]["api_key_env"] is None
        assert rows["riksdagen"]["ready"] is True

    def test_keyed_source_not_ready_without_key(self, monkeypatch):
        monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
        rows = {r["id"]: r for r in source_key_status()}
        assert rows["legiscan"]["api_key_env"] == "LEGISCAN_API_KEY"
        assert rows["legiscan"]["ready"] is False

    def test_keyed_source_ready_with_key(self, monkeypatch):
        monkeypatch.setenv("GOVINFO_API_KEY", "abc123")
        rows = {r["id"]: r for r in source_key_status()}
        assert rows["govinfo"]["ready"] is True

    def test_status_never_exposes_the_key_value(self, monkeypatch):
        monkeypatch.setenv("DIP_API_KEY", "super-secret-value")
        rows = source_key_status()
        assert not any("super-secret-value" in str(r) for r in rows)
