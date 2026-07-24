"""Tests for GET /api/policies?lifecycle_stage=<stage> and
GET /api/policies/search?...&lifecycle_stage=<stage>.

Exact match against the known LIFECYCLE_STAGES vocabulary
(src.core.models.LIFECYCLE_STAGES); an unknown stage is a 422 in the
standard envelope. Composes with the existing filters.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.core.models import Policy, PolicyType
from src.storage.store import PolicyStore


def _policy(url, lifecycle_stage, score=5):
    return Policy(
        url=url,
        policy_name=f"Policy {url[-1]}",
        jurisdiction="Sweden",
        policy_type=PolicyType.LAW,
        summary="s",
        relevance_score=score,
        lifecycle_stage=lifecycle_stage,
    )


@pytest.fixture
def store(tmp_path):
    s = PolicyStore(data_dir=str(tmp_path))
    s.add_policies([
        _policy("https://a.gov/1", "proposed", score=9),
        _policy("https://a.gov/2", "consultation", score=3),
        _policy("https://a.gov/3", "consultation", score=7),
        _policy("https://a.gov/4", "enacted", score=5),
        _policy("https://a.gov/5", "unknown", score=5),
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


class TestListPoliciesLifecycleStage:
    def test_exact_match_single_stage(self, client):
        resp = client.get("/api/policies", params={"lifecycle_stage": "consultation"})
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/2", "https://a.gov/3"}

    def test_unknown_stage_rejected(self, client):
        resp = client.get("/api/policies", params={"lifecycle_stage": "bogus_stage"})
        assert resp.status_code == 422
        assert "detail" in resp.json()

    def test_composes_with_min_score(self, client):
        resp = client.get(
            "/api/policies", params={"lifecycle_stage": "consultation", "min_score": 5},
        )
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/3"}

    def test_no_param_leaves_existing_behavior_unchanged(self, client):
        resp = client.get("/api/policies")
        assert resp.status_code == 200
        assert len(resp.json()["policies"]) == 5


class TestSearchPoliciesLifecycleStage:
    def test_exact_match_single_stage(self, client):
        resp = client.get(
            "/api/policies/search", params={"q": "Policy", "lifecycle_stage": "enacted"},
        )
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/4"}

    def test_unknown_stage_rejected(self, client):
        resp = client.get(
            "/api/policies/search", params={"q": "Policy", "lifecycle_stage": "bogus"},
        )
        assert resp.status_code == 422
