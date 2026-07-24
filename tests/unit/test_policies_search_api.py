"""Tests for GET /api/policies/search - free-text search over stored policies.

Backed by PolicyStore.search_text() (src/storage/store.py). ``q`` is required
(1-200 chars); jurisdiction/policy_type/min_score compose with it exactly as
they do on GET /api/policies. The route is a public GET, so it must stay open
even with ADMIN_TOKEN set (AdminGateMiddleware only gates non-GET requests).
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.core.models import Policy, PolicyType
from src.storage.store import PolicyStore


def _policy(url, name, jurisdiction, summary, policy_type=PolicyType.LAW, score=5):
    return Policy(
        url=url,
        policy_name=name,
        jurisdiction=jurisdiction,
        policy_type=policy_type,
        summary=summary,
        relevance_score=score,
    )


@pytest.fixture
def store(tmp_path):
    s = PolicyStore(data_dir=str(tmp_path))
    s.add_policies([
        _policy(
            "https://heat.gov", "Heat Reuse Mandate", "US",
            "Requires heat reuse for data centres.", score=7,
        ),
        _policy(
            "https://de.gov", "Abwaermegesetz", "Germany",
            "Regelt die Nutzung von Abwärme.", score=6,
        ),
        _policy(
            "https://fr.gov", "Loi chaleur fatale", "France",
            "Encadre la chaleur fatale des centres de donnees.",
            policy_type=PolicyType.REGULATION, score=9,
        ),
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


def _urls(response):
    return {p["url"] for p in response.json()["policies"]}


class TestSearchEndpoint:
    def test_basic_query_returns_matching_policies(self, client):
        resp = client.get("/api/policies/search", params={"q": "heat reuse"})
        assert resp.status_code == 200
        body = resp.json()
        assert _urls(resp) == {"https://heat.gov"}
        assert body["total"] == 1
        assert body["query"] == "heat reuse"

    def test_response_envelope_shape(self, client):
        resp = client.get("/api/policies/search", params={"q": "centres"})
        body = resp.json()
        assert set(body.keys()) == {"policies", "total", "query"}
        assert body["total"] == len(body["policies"])

    def test_jurisdiction_filter_composes(self, client):
        resp = client.get(
            "/api/policies/search", params={"q": "centres", "jurisdiction": "france"},
        )
        assert _urls(resp) == {"https://fr.gov"}

    def test_policy_type_filter_composes(self, client):
        resp = client.get(
            "/api/policies/search", params={"q": "centres", "policy_type": "regulation"},
        )
        assert _urls(resp) == {"https://fr.gov"}

    def test_min_score_filter_composes(self, client):
        resp = client.get(
            "/api/policies/search", params={"q": "centres", "min_score": 8},
        )
        assert _urls(resp) == {"https://fr.gov"}

    def test_limit_param_is_honored(self, client):
        resp = client.get(
            "/api/policies/search", params={"q": "centres", "limit": 1},
        )
        assert resp.status_code == 200
        assert len(resp.json()["policies"]) == 1


class TestSearchValidation:
    def test_missing_q_is_422(self, client):
        resp = client.get("/api/policies/search")
        assert resp.status_code == 422

    def test_empty_q_is_422(self, client):
        resp = client.get("/api/policies/search", params={"q": ""})
        assert resp.status_code == 422

    def test_oversized_q_is_422(self, client):
        resp = client.get("/api/policies/search", params={"q": "a" * 201})
        assert resp.status_code == 422

    def test_limit_below_minimum_is_422(self, client):
        resp = client.get("/api/policies/search", params={"q": "heat", "limit": 0})
        assert resp.status_code == 422

    def test_limit_above_maximum_is_422(self, client):
        resp = client.get("/api/policies/search", params={"q": "heat", "limit": 101})
        assert resp.status_code == 422

    def test_default_limit_is_20(self, client):
        resp = client.get("/api/policies/search", params={"q": "heat"})
        assert resp.status_code == 200


class TestSearchIsPublicThroughAdminGate:
    def test_get_search_succeeds_with_admin_token_set_and_no_header(self, store, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret-token")

        from src.api.app import app
        from src.api import deps

        manager = MagicMock()
        manager.get_all_policies.return_value = []
        app.dependency_overrides[deps.get_policy_store] = lambda: store
        app.dependency_overrides[deps.get_scan_manager] = lambda: manager
        try:
            with TestClient(app) as c:
                resp = c.get("/api/policies/search", params={"q": "heat"})
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestSearchRouteNotShadowed:
    def test_search_path_is_not_captured_as_a_parameterized_route(self, client):
        """'/api/policies/search' must resolve to the search endpoint, not a
        path-parameter route matching 'search' as some other resource id."""
        resp = client.get("/api/policies/search", params={"q": "heat"})
        assert resp.status_code == 200
        assert "query" in resp.json()
