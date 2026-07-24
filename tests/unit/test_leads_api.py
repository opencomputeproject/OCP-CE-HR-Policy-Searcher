"""Tests for tip endpoints and the admin gate middleware.

User-facing vocabulary is "Tips" (API paths, UI text); the storage layer
underneath stays LeadStore/Lead (see src/storage/leads.py) per the
2026-07 rename decision.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.storage.leads import Lead, LeadStore


@pytest.fixture
def lead_store(tmp_path):
    return LeadStore(data_dir=str(tmp_path))


@pytest.fixture
def client(lead_store, tmp_path, monkeypatch):
    from src.api.app import app
    from src.api import deps
    from src.api.routes import leads as tips_route

    monkeypatch.setenv("OCP_DATA_DIR", str(tmp_path))
    tips_route.reset_tip_limits_for_tests(data_dir=str(tmp_path))

    app.dependency_overrides[deps.get_lead_store] = lambda: lead_store
    app.dependency_overrides[deps.get_config] = lambda: MagicMock()
    app.dependency_overrides[deps.get_policy_store] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestTipRoutes:
    def test_list_empty(self, client):
        response = client.get("/api/tips")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    # Literal public IPs exercise the real SSRF guard without DNS.
    def test_submit_and_list(self, client):
        response = client.post(
            "/api/tips",
            json={"url": "https://8.8.8.8/heat-law", "note": "New Danish rule"},
        )
        assert response.status_code == 200
        assert client.get("/api/tips").json()["count"] == 1

    def test_submit_rejects_non_http(self, client):
        response = client.post("/api/tips", json={"url": "javascript:alert(1)"})
        assert response.status_code == 422

    def test_submit_rejects_private_and_metadata_urls(self, client):
        for bad in (
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://127.0.0.1/admin",
            "http://10.0.0.5/internal",
        ):
            response = client.post("/api/tips", json={"url": bad})
            assert response.status_code == 422, bad

    def test_duplicate_submission_conflicts(self, client):
        client.post("/api/tips", json={"url": "https://8.8.8.8/x"})
        response = client.post("/api/tips", json={"url": "https://8.8.8.8/x"})
        assert response.status_code == 409

    def test_dismiss(self, client, lead_store):
        lead = Lead(title="t", source_url="https://8.8.8.8/y")
        lead_store.add_leads([lead])
        response = client.post(f"/api/tips/{lead.lead_id}/dismiss")
        assert response.status_code == 200
        assert lead_store.get(lead.lead_id).status == "dismissed"

    def test_dismiss_unknown_404(self, client):
        assert client.post("/api/tips/nope/dismiss").status_code == 404

    def test_chase_runs_analysis_and_records(self, client, lead_store):
        lead = Lead(title="t", source_url="https://8.8.8.8/z")
        lead_store.add_leads([lead])
        with patch(
            "src.api.routes.leads.run_url_analysis",
            AsyncMock(return_value={"policy": {"url": "https://8.8.8.8/z"}}),
        ) as run:
            response = client.post(f"/api/tips/{lead.lead_id}/chase")
        assert response.status_code == 200
        run.assert_awaited_once()
        chased = lead_store.get(lead.lead_id)
        assert chased.status == "chased"
        assert chased.policy_url == "https://8.8.8.8/z"

    def test_chase_refuses_private_url_without_fetching(self, client, lead_store):
        # A news tip (bypasses the submission guard) pointed inward.
        lead = Lead(title="t", source_url="http://169.254.169.254/latest/meta-data/")
        lead_store.add_leads([lead])
        with patch("src.api.routes.leads.run_url_analysis", AsyncMock()) as run:
            response = client.post(f"/api/tips/{lead.lead_id}/chase")
        assert response.status_code == 400
        run.assert_not_awaited()


class TestNoteOnlyTips:
    """A tip may be a URL, a note, or both — only reject when both are empty."""

    def test_note_only_submission_accepted(self, client):
        response = client.post("/api/tips", json={"note": "Heard Ohio is drafting something"})
        assert response.status_code == 200
        # Response field names keep their internal (Lead/LeadStore) shape —
        # only the URL paths and UI text say "tip".
        body = client.get("/api/tips").json()
        assert body["count"] == 1
        assert body["leads"][0]["source_url"] == ""
        assert body["leads"][0]["snippet"] == "Heard Ohio is drafting something"

    def test_both_empty_rejected(self, client):
        response = client.post("/api/tips", json={})
        assert response.status_code == 422

    def test_blank_strings_rejected(self, client):
        response = client.post("/api/tips", json={"url": "  ", "note": "   "})
        assert response.status_code == 422

    def test_url_only_still_works(self, client):
        response = client.post("/api/tips", json={"url": "https://8.8.8.8/only-url"})
        assert response.status_code == 200

    def test_distinct_note_only_tips_both_kept(self, client):
        """Two different note-only tips must not collide on empty source_url."""
        r1 = client.post("/api/tips", json={"note": "First rumor"})
        r2 = client.post("/api/tips", json={"note": "Second, unrelated rumor"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert client.get("/api/tips").json()["count"] == 2

    def test_identical_note_only_tips_dedupe(self, client):
        """Same note text twice is a real duplicate, not two distinct tips."""
        client.post("/api/tips", json={"note": "Same rumor"})
        response = client.post("/api/tips", json={"note": "Same rumor"})
        assert response.status_code == 409
        assert client.get("/api/tips").json()["count"] == 1

    def test_note_only_tip_not_chaseable(self, client):
        response = client.post("/api/tips", json={"note": "No URL here"})
        lead_id = response.json()["lead_id"]
        chase = client.post(f"/api/tips/{lead_id}/chase")
        assert chase.status_code == 400
        assert "note" in chase.json()["detail"].lower()


class TestChaseOutcomes:
    """Chase outcomes are visible: no-policy, policy-found, and fetch-failed."""

    def test_no_policy_found_records_outcome(self, client, lead_store):
        lead = Lead(title="t", source_url="https://8.8.8.8/no-policy")
        lead_store.add_leads([lead])
        with patch(
            "src.api.routes.leads.run_url_analysis",
            AsyncMock(return_value={"policy": None}),
        ):
            response = client.post(f"/api/tips/{lead.lead_id}/chase")
        assert response.status_code == 200
        chased = lead_store.get(lead.lead_id)
        assert chased.status == "chased"
        assert chased.chase_outcome == "no_policy"
        assert chased.chased_at is not None

    def test_fetch_raising_exception_returns_structured_outcome_not_500(self, client, lead_store):
        """Regression: news.google.com-style redirect wrappers used to raise
        an unhandled exception through run_url_analysis, surfacing a raw 500.
        The chase must instead succeed with a clean fetch_failed outcome."""
        lead = Lead(title="t", source_url="https://8.8.8.8/google-news-wrapper")
        lead_store.add_leads([lead])
        with patch(
            "src.api.routes.leads.run_url_analysis",
            AsyncMock(side_effect=RuntimeError("too many redirects")),
        ):
            response = client.post(f"/api/tips/{lead.lead_id}/chase")
        assert response.status_code == 200
        body = response.json()
        assert body["analysis"]["outcome"] == "fetch_failed"
        assert "too many redirects" in body["analysis"]["error"]

        stored = lead_store.get(lead.lead_id)
        assert stored.chase_outcome == "fetch_failed"
        assert stored.status == "new"  # stays chaseable

    def test_tip_stays_chaseable_after_fetch_failure(self, client, lead_store):
        lead = Lead(title="t", source_url="https://8.8.8.8/retry-me")
        lead_store.add_leads([lead])
        with patch(
            "src.api.routes.leads.run_url_analysis",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            first = client.post(f"/api/tips/{lead.lead_id}/chase")
        assert first.status_code == 200

        with patch(
            "src.api.routes.leads.run_url_analysis",
            AsyncMock(return_value={"policy": {"url": "https://8.8.8.8/retry-me"}}),
        ):
            second = client.post(f"/api/tips/{lead.lead_id}/chase")
        assert second.status_code == 200
        assert lead_store.get(lead.lead_id).status == "chased"


class TestTipSubmissionRateLimit:
    def test_burst_limit_returns_429_with_retry_after(self, client, monkeypatch):
        from src.api.routes import leads as tips_route

        monkeypatch.setattr(tips_route, "TIPS_RATE_PER_MINUTE", 2)
        monkeypatch.setattr(tips_route, "TIPS_DAILY_LIMIT", 100)
        for i in range(2):
            resp = client.post("/api/tips", json={"url": f"https://8.8.8.8/burst-{i}"})
            assert resp.status_code == 200
        response = client.post("/api/tips", json={"url": "https://8.8.8.8/burst-over"})
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_daily_cap_returns_429(self, client, monkeypatch):
        from src.api.routes import leads as tips_route

        monkeypatch.setattr(tips_route, "TIPS_RATE_PER_MINUTE", 60)
        monkeypatch.setattr(tips_route, "TIPS_DAILY_LIMIT", 1)
        assert client.post(
            "/api/tips", json={"url": "https://8.8.8.8/daily-1"},
        ).status_code == 200
        response = client.post("/api/tips", json={"url": "https://8.8.8.8/daily-2"})
        assert response.status_code == 429
        assert "daily" in response.json()["detail"].lower()

    def test_distinct_ips_get_separate_buckets(self, client, monkeypatch):
        from src.api.routes import leads as tips_route

        monkeypatch.setattr(tips_route, "TIPS_RATE_PER_MINUTE", 1)
        monkeypatch.setattr(tips_route, "TIPS_DAILY_LIMIT", 100)
        r1 = client.post(
            "/api/tips", json={"url": "https://8.8.8.8/ip1"},
            headers={"X-Forwarded-For": "203.0.113.1"},
        )
        r2 = client.post(
            "/api/tips", json={"url": "https://8.8.8.8/ip2"},
            headers={"X-Forwarded-For": "203.0.113.2"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200  # different client, not throttled

    def test_rate_limit_checked_before_validation(self, client, monkeypatch):
        """The burst limit trips even for a request that would otherwise 422."""
        from src.api.routes import leads as tips_route

        monkeypatch.setattr(tips_route, "TIPS_RATE_PER_MINUTE", 1)
        monkeypatch.setattr(tips_route, "TIPS_DAILY_LIMIT", 100)
        assert client.post(
            "/api/tips", json={"url": "https://8.8.8.8/first"},
        ).status_code == 200
        response = client.post("/api/tips", json={})  # would otherwise be 422
        assert response.status_code == 429


class TestAdminGate:
    def test_health_reports_admin_mode(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        assert client.get("/health").json()["admin_required"] is True

    def test_reads_stay_open(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        assert client.get("/api/tips").status_code == 200

    def test_mutations_blocked_without_token(self, client, lead_store, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        lead = Lead(title="t", source_url="https://a.gov/q")
        lead_store.add_leads([lead])
        response = client.post(f"/api/tips/{lead.lead_id}/dismiss")
        assert response.status_code == 401

    def test_mutations_allowed_with_token(self, client, lead_store, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret123")
        lead = Lead(title="t", source_url="https://a.gov/r")
        lead_store.add_leads([lead])
        response = client.post(
            f"/api/tips/{lead.lead_id}/dismiss",
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
            "/api/tips", json={"url": "https://8.8.8.8/policy"},
        )
        assert response.status_code == 200

    def test_no_token_configured_means_open(self, client, lead_store, monkeypatch):
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
        lead = Lead(title="t", source_url="https://a.gov/s")
        lead_store.add_leads([lead])
        assert client.post(f"/api/tips/{lead.lead_id}/dismiss").status_code == 200
