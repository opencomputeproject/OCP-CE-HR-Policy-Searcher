"""Tests for `evidence` on GET /api/policies and GET /api/policies/search
(WP-5): the screener's document kind and its two quotes ride on the row,
so a reviewer can see why it exists without re-reading the source page.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.core.models import Policy, PolicyType
from src.storage.store import PolicyStore

pytestmark = pytest.mark.medium


def _policy(url, evidence=None):
    return Policy(
        url=url,
        policy_name=f"Policy {url[-1]}",
        jurisdiction="US",
        policy_type=PolicyType.LAW,
        summary="s",
        relevance_score=7,
        evidence=evidence,
    )


@pytest.fixture
def store(tmp_path):
    s = PolicyStore(data_dir=str(tmp_path))
    s.add_policies([
        _policy("https://us.gov/1", evidence={
            "kind": "bill",
            "dc_quote": "This bill concerns data centers.",
            "heat_quote": "Operators must reuse waste heat.",
            "quote_verified": True,
        }),
        _policy("https://us.gov/2"),
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


def _by_url(response):
    return {p["url"]: p for p in response.json()["policies"]}


class TestListPoliciesEvidence:
    def test_a_policy_with_evidence_exposes_it(self, client):
        resp = client.get("/api/policies")
        assert resp.status_code == 200
        policy = _by_url(resp)["https://us.gov/1"]
        assert policy["evidence"]["kind"] == "bill"
        assert policy["evidence"]["dc_quote"] == "This bill concerns data centers."
        assert policy["evidence"]["heat_quote"] == "Operators must reuse waste heat."
        assert policy["evidence"]["quote_verified"] is True

    def test_a_policy_without_evidence_gives_none(self, client):
        resp = client.get("/api/policies")
        policy = _by_url(resp)["https://us.gov/2"]
        assert policy["evidence"] is None


class TestSearchPoliciesEvidence:
    def test_a_policy_with_evidence_exposes_it(self, client):
        resp = client.get("/api/policies/search", params={"q": "Policy"})
        policy = _by_url(resp)["https://us.gov/1"]
        assert policy["evidence"]["kind"] == "bill"

    def test_a_policy_without_evidence_gives_none(self, client):
        resp = client.get("/api/policies/search", params={"q": "Policy"})
        policy = _by_url(resp)["https://us.gov/2"]
        assert policy["evidence"] is None
