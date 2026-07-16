"""Tests for the review workflow: status filter, PATCH review, sheet link."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.core.models import Policy, PolicyType
from src.storage.store import PolicyStore


def _policy(url: str, review_status: str = "new") -> Policy:
    return Policy(
        url=url,
        policy_name=f"Policy {url[-1]}",
        jurisdiction="Sweden",
        policy_type=PolicyType.LAW,
        summary="s",
        relevance_score=7,
        review_status=review_status,
    )


@pytest.fixture
def store(tmp_path):
    s = PolicyStore(data_dir=str(tmp_path))
    s.add_policies([
        _policy("https://a.gov/1", "new"),
        _policy("https://a.gov/2", "reviewed"),
        _policy("https://a.gov/3", "new"),
    ])
    return s


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    from src.api.app import app
    from src.api import deps

    manager = MagicMock()
    manager.get_all_policies.return_value = []
    app.dependency_overrides[deps.get_policy_store] = lambda: store
    app.dependency_overrides[deps.get_scan_manager] = lambda: manager
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestReviewStatusFilter:
    def test_filter_new(self, client):
        resp = client.get("/api/policies", params={"review_status": "new"})
        assert resp.status_code == 200
        urls = {p["url"] for p in resp.json()["policies"]}
        assert urls == {"https://a.gov/1", "https://a.gov/3"}

    def test_no_filter_returns_all(self, client):
        assert client.get("/api/policies").json()["count"] == 3


class TestUpdateReviewStatus:
    def test_mark_reviewed(self, client, store):
        resp = client.patch(
            "/api/policies/review",
            json={"url": "https://a.gov/1", "review_status": "reviewed"},
        )
        assert resp.status_code == 200
        assert resp.json()["review_status"] == "reviewed"
        stored = {p["url"]: p for p in store.get_all()}
        assert stored["https://a.gov/1"]["review_status"] == "reviewed"

    def test_unknown_url_404(self, client):
        resp = client.patch(
            "/api/policies/review",
            json={"url": "https://nope.gov", "review_status": "reviewed"},
        )
        assert resp.status_code == 404

    def test_invalid_status_rejected(self, client):
        resp = client.patch(
            "/api/policies/review",
            json={"url": "https://a.gov/1", "review_status": "banana"},
        )
        assert resp.status_code == 422

    def test_requires_admin_token_when_gate_active(self, store, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret")

        from src.api.app import app
        from src.api import deps

        app.dependency_overrides[deps.get_policy_store] = lambda: store
        try:
            with TestClient(app) as c:
                resp = c.patch(
                    "/api/policies/review",
                    json={"url": "https://a.gov/1", "review_status": "reviewed"},
                )
                assert resp.status_code == 401
                resp = c.patch(
                    "/api/policies/review",
                    json={"url": "https://a.gov/1", "review_status": "reviewed"},
                    headers={"X-Admin-Token": "secret"},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestSheetLink:
    def test_open_when_no_gate(self, client, monkeypatch):
        monkeypatch.setenv("SPREADSHEET_ID", "sheet-id-123")
        resp = client.get("/api/settings/sheet")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert "sheet-id-123" in data["url"]

    def test_unconfigured(self, client, monkeypatch):
        monkeypatch.delenv("SPREADSHEET_ID", raising=False)
        resp = client.get("/api/settings/sheet")
        assert resp.status_code == 200
        assert resp.json()["configured"] is False

    def test_admin_only_when_gate_active(self, store, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret")
        monkeypatch.setenv("SPREADSHEET_ID", "sheet-id-123")

        from src.api.app import app
        from src.api import deps

        app.dependency_overrides[deps.get_policy_store] = lambda: store
        try:
            with TestClient(app) as c:
                assert c.get("/api/settings/sheet").status_code == 401
                resp = c.get(
                    "/api/settings/sheet", headers={"X-Admin-Token": "secret"},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestStoreUpdateReviewStatus:
    def test_updates_and_persists(self, tmp_path):
        s = PolicyStore(data_dir=str(tmp_path))
        s.add_policies([_policy("https://a.gov/1")])
        assert s.update_review_status("https://a.gov/1", "promoted") is True

        reloaded = PolicyStore(data_dir=str(tmp_path))
        assert reloaded.get_all()[0]["review_status"] == "promoted"

    def test_unknown_url_returns_false(self, tmp_path):
        s = PolicyStore(data_dir=str(tmp_path))
        assert s.update_review_status("https://nope.gov", "reviewed") is False
