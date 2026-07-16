"""Tests for lead endpoints and the admin gate middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.storage.leads import Lead, LeadStore


@pytest.fixture
def lead_store(tmp_path):
    return LeadStore(data_dir=str(tmp_path))


@pytest.fixture
def client(lead_store):
    from src.api.app import app
    from src.api import deps

    app.dependency_overrides[deps.get_lead_store] = lambda: lead_store
    app.dependency_overrides[deps.get_config] = lambda: MagicMock()
    app.dependency_overrides[deps.get_policy_store] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestLeadRoutes:
    def test_list_empty(self, client):
        response = client.get("/api/leads")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    # Literal public IPs exercise the real SSRF guard without DNS.
    def test_submit_and_list(self, client):
        response = client.post(
            "/api/leads",
            json={"url": "https://8.8.8.8/heat-law", "note": "New Danish rule"},
        )
        assert response.status_code == 200
        assert client.get("/api/leads").json()["count"] == 1

    def test_submit_rejects_non_http(self, client):
        response = client.post("/api/leads", json={"url": "javascript:alert(1)"})
        assert response.status_code == 422

    def test_submit_rejects_private_and_metadata_urls(self, client):
        for bad in (
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://127.0.0.1/admin",
            "http://10.0.0.5/internal",
        ):
            response = client.post("/api/leads", json={"url": bad})
            assert response.status_code == 422, bad

    def test_duplicate_submission_conflicts(self, client):
        client.post("/api/leads", json={"url": "https://8.8.8.8/x"})
        response = client.post("/api/leads", json={"url": "https://8.8.8.8/x"})
        assert response.status_code == 409

    def test_dismiss(self, client, lead_store):
        lead = Lead(title="t", source_url="https://8.8.8.8/y")
        lead_store.add_leads([lead])
        response = client.post(f"/api/leads/{lead.lead_id}/dismiss")
        assert response.status_code == 200
        assert lead_store.get(lead.lead_id).status == "dismissed"

    def test_dismiss_unknown_404(self, client):
        assert client.post("/api/leads/nope/dismiss").status_code == 404

    def test_chase_runs_analysis_and_records(self, client, lead_store):
        lead = Lead(title="t", source_url="https://8.8.8.8/z")
        lead_store.add_leads([lead])
        with patch(
            "src.api.routes.leads.run_url_analysis",
            AsyncMock(return_value={"policy": {"url": "https://8.8.8.8/z"}}),
        ) as run:
            response = client.post(f"/api/leads/{lead.lead_id}/chase")
        assert response.status_code == 200
        run.assert_awaited_once()
        chased = lead_store.get(lead.lead_id)
        assert chased.status == "chased"
        assert chased.policy_url == "https://8.8.8.8/z"

    def test_chase_refuses_private_url_without_fetching(self, client, lead_store):
        # A news lead (bypasses the submission guard) pointed inward.
        lead = Lead(title="t", source_url="http://169.254.169.254/latest/meta-data/")
        lead_store.add_leads([lead])
        with patch("src.api.routes.leads.run_url_analysis", AsyncMock()) as run:
            response = client.post(f"/api/leads/{lead.lead_id}/chase")
        assert response.status_code == 400
        run.assert_not_awaited()


class TestAdminGate:
    def test_health_reports_admin_mode(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        assert client.get("/health").json()["admin_required"] is True

    def test_reads_stay_open(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        assert client.get("/api/leads").status_code == 200

    def test_mutations_blocked_without_token(self, client, lead_store, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        lead = Lead(title="t", source_url="https://a.gov/q")
        lead_store.add_leads([lead])
        response = client.post(f"/api/leads/{lead.lead_id}/dismiss")
        assert response.status_code == 401

    def test_mutations_allowed_with_token(self, client, lead_store, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        lead = Lead(title="t", source_url="https://a.gov/r")
        lead_store.add_leads([lead])
        response = client.post(
            f"/api/leads/{lead.lead_id}/dismiss",
            headers={"X-Admin-Token": "secret123"},
        )
        assert response.status_code == 200

    def test_wrong_token_rejected(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        response = client.post(
            "/api/scans", json={"domains": "quick"},
            headers={"X-Admin-Token": "wrong"},
        )
        assert response.status_code == 401

    def test_community_submission_exempt(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        response = client.post(
            "/api/leads", json={"url": "https://8.8.8.8/policy"},
        )
        assert response.status_code == 200

    def test_no_token_configured_means_open(self, client, lead_store, monkeypatch):
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
        lead = Lead(title="t", source_url="https://a.gov/s")
        lead_store.add_leads([lead])
        assert client.post(f"/api/leads/{lead.lead_id}/dismiss").status_code == 200
