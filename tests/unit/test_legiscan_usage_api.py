"""Tests for GET /api/settings/legiscan-usage."""

from fastapi.testclient import TestClient

# Import once at module load so app.py's import-time load_dotenv(override=True)
# runs before any per-test monkeypatch.delenv (otherwise a later first import
# would re-populate the key from .env and undo the patch).
from src.api.app import app


def _client():
    return TestClient(app)


def test_reports_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
    with _client() as c:
        body = c.get("/api/settings/legiscan-usage").json()
    assert body == {"configured": False}


def test_reports_usage_with_key(monkeypatch, tmp_path):
    monkeypatch.setenv("LEGISCAN_API_KEY", "test-key")
    from src.sources import legiscan
    monkeypatch.setattr(legiscan, "USAGE_FILE", tmp_path / "legiscan_usage.json")
    legiscan._record_usage(1200)
    with _client() as c:
        body = c.get("/api/settings/legiscan-usage").json()
    assert body["configured"] is True
    assert body["used"] == 1200
    assert body["remaining"] == legiscan.MONTHLY_QUERY_LIMIT - 1200
    assert body["limit"] == 30000
