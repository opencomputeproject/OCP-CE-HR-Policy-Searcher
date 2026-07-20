"""Tests for GET /api/policies?place=<registry-slug>.

``place`` resolves each stored policy's free-text jurisdiction through the
canonical registry (src/core/jurisdictions.py) and matches when the resolved
jurisdiction IS the place, or rolls up to it via country_of. Country slugs are
therefore descendant-inclusive (place=us also returns every US state policy);
subnational and supranational slugs match only themselves. An unknown slug is
a 404 in the standard envelope. ``place`` composes with the existing filters.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.core.models import Policy, PolicyType
from src.storage.store import PolicyStore


def _policy(url, jurisdiction, score=5):
    return Policy(
        url=url,
        policy_name=f"Policy {url[-1]}",
        jurisdiction=jurisdiction,
        policy_type=PolicyType.LAW,
        summary="s",
        relevance_score=score,
    )


@pytest.fixture
def store(tmp_path):
    s = PolicyStore(data_dir=str(tmp_path))
    s.add_policies([
        _policy("https://a.gov/1", "US", score=9),
        _policy("https://a.gov/2", "Minnesota, USA", score=3),
        _policy("https://a.gov/3", "California, USA", score=7),
        _policy("https://a.gov/4", "Sweden", score=5),
        _policy("https://a.gov/5", "Sweden (EU)", score=5),
        _policy("https://a.gov/6", "European Union", score=5),
        _policy("https://a.gov/7", "Wallonia, Belgium", score=5),
        _policy("https://a.gov/8", "Brussels, Belgium", score=5),
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


class TestCountryPlaceIsDescendantInclusive:
    def test_place_us_includes_federal_and_state_policies(self, client):
        resp = client.get("/api/policies", params={"place": "us"})
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/1", "https://a.gov/2", "https://a.gov/3"}

    def test_place_belgium_includes_national_and_regional_policies(self, client):
        resp = client.get("/api/policies", params={"place": "belgium"})
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/7", "https://a.gov/8"}

    def test_place_sweden_includes_the_eu_annotated_string(self, client):
        # "Sweden (EU)" resolves to Sweden, not the EU - country_of(sweden) is
        # sweden itself via equality, and the annotated string must too.
        resp = client.get("/api/policies", params={"place": "sweden"})
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/4", "https://a.gov/5"}


class TestSubnationalPlaceIsExactOnly:
    def test_place_california_matches_only_california(self, client):
        resp = client.get("/api/policies", params={"place": "california"})
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/3"}


class TestSupranationalPlaceIsEqualityOnly:
    def test_place_eu_matches_only_the_eu_string_not_sweden_eu(self, client):
        resp = client.get("/api/policies", params={"place": "eu"})
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/6"}


class TestUnknownPlaceSlug:
    def test_unknown_slug_returns_404_standard_envelope(self, client):
        resp = client.get("/api/policies", params={"place": "atlantis"})
        assert resp.status_code == 404
        assert "detail" in resp.json()


class TestPlaceComposesWithExistingFilters:
    def test_place_and_min_score_compose(self, client):
        resp = client.get("/api/policies", params={"place": "us", "min_score": 5})
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/1", "https://a.gov/3"}

    def test_no_place_param_leaves_existing_behavior_unchanged(self, client):
        resp = client.get("/api/policies", params={"min_score": 9})
        assert resp.status_code == 200
        assert _urls(resp) == {"https://a.gov/1"}
