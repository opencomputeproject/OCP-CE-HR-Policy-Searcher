"""Tests for GET /api/search/plan (place-first search planning)."""

import pytest
from fastapi.testclient import TestClient

from src.core.config import ConfigLoader


@pytest.fixture
def config_loader(tmp_path):
    config = tmp_path / "config"
    domains_dir = config / "domains"
    domains_dir.mkdir(parents=True)

    (config / "settings.yaml").write_text("crawl:\n  max_depth: 2\n", encoding="utf-8")
    (domains_dir / "sites.yaml").write_text(
        "domains:\n"
        "  - id: ca_energy\n"
        "    name: California Energy Commission\n"
        "    base_url: https://www.energy.ca.gov\n"
        "    region: [california, us_states, us]\n"
        "  - id: legiscan_api\n"
        "    name: LegiScan API\n"
        "    base_url: https://api.legiscan.com\n"
        "    region: [us, us_states]\n"
        "    source_type: legiscan\n",
        encoding="utf-8",
    )
    (config / "groups.yaml").write_text("groups: {}\n", encoding="utf-8")
    (config / "keywords.yaml").write_text(
        "categories:\n"
        "  heat:\n"
        "    weight: 3.0\n"
        "    terms:\n"
        "      en: [waste heat]\n"
        "thresholds:\n  min_score: 3.0\n  min_matches: 1\n",
        encoding="utf-8",
    )
    (config / "url_filters.yaml").write_text(
        "url_filters:\n  skip_paths: []\n", encoding="utf-8",
    )
    return ConfigLoader(config_dir=str(config))


@pytest.fixture
def client(config_loader, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    from src.api.app import app
    from src.api import deps

    app.dependency_overrides[deps.get_config] = lambda: config_loader
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestSearchPlan:
    def test_us_state_plan(self, client):
        resp = client.get("/api/search/plan", params={"place": "California"})
        assert resp.status_code == 200
        plan = resp.json()
        assert plan["place"]["kind"] == "us_state"
        assert plan["source_params"]["state"] == "CA"
        assert {s["id"] for s in plan["sources"]} == {"ca_energy", "legiscan_api"}
        assert plan["targets"]

    def test_terms_comma_parsed(self, client):
        resp = client.get(
            "/api/search/plan",
            params={"place": "California", "terms": "thermal energy network, heat reuse"},
        )
        assert resp.status_code == 200
        assert resp.json()["source_params"]["terms"] == [
            "thermal energy network", "heat reuse",
        ]

    def test_unknown_place_returns_warnings_not_error(self, client):
        resp = client.get("/api/search/plan", params={"place": "Atlantis"})
        assert resp.status_code == 200
        plan = resp.json()
        assert plan["sources"] == []
        assert plan["warnings"]

    def test_missing_place_rejected(self, client):
        assert client.get("/api/search/plan").status_code == 422

    def test_read_stays_open_with_admin_gate(self, config_loader, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "secret")

        from src.api.app import app
        from src.api import deps

        app.dependency_overrides[deps.get_config] = lambda: config_loader
        try:
            with TestClient(app) as c:
                resp = c.get("/api/search/plan", params={"place": "California"})
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()
