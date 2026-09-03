"""Tests for `read_in_english_url` on GET /api/policies and
GET /api/policies/search (WP-9a / ADR-0009): a reviewer who reads only
English gets a translated-page link for a non-English source, and null for
an English one. The app never stores this URL - it is computed at response
time from src.core.urls.translated_url.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.core.models import Policy, PolicyType
from src.storage.store import PolicyStore

pytestmark = pytest.mark.medium


def _policy(url, jurisdiction, source_language, score=5):
    return Policy(
        url=url,
        policy_name=f"Policy {url[-1]}",
        jurisdiction=jurisdiction,
        policy_type=PolicyType.LAW,
        summary="s",
        relevance_score=score,
        source_language=source_language,
    )


@pytest.fixture
def store(tmp_path):
    s = PolicyStore(data_dir=str(tmp_path))
    s.add_policies([
        _policy("https://nl.gov/1", "Netherlands", "Dutch"),
        _policy("https://us.gov/2", "US", "English"),
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


class TestListPoliciesReadInEnglishUrl:
    def test_non_english_source_gets_a_translated_link(self, client):
        resp = client.get("/api/policies")
        assert resp.status_code == 200
        policy = _by_url(resp)["https://nl.gov/1"]
        assert policy["read_in_english_url"].startswith("https://nl-gov.translate.goog/1")

    def test_english_source_gets_null(self, client):
        resp = client.get("/api/policies")
        policy = _by_url(resp)["https://us.gov/2"]
        assert policy["read_in_english_url"] is None


class TestSearchPoliciesReadInEnglishUrl:
    def test_non_english_source_gets_a_translated_link(self, client):
        resp = client.get("/api/policies/search", params={"q": "Policy"})
        policy = _by_url(resp)["https://nl.gov/1"]
        assert policy["read_in_english_url"].startswith("https://nl-gov.translate.goog/1")

    def test_english_source_gets_null(self, client):
        resp = client.get("/api/policies/search", params={"q": "Policy"})
        policy = _by_url(resp)["https://us.gov/2"]
        assert policy["read_in_english_url"] is None
