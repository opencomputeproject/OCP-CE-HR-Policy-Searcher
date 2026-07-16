"""Tests for place-first search planning (src/core/search_plan.py)."""

import pytest

from src.core.config import ConfigLoader
from src.core.search_plan import build_search_plan, resolve_place


@pytest.fixture
def config_dir(tmp_path):
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
        "  - id: sweden_regeringen\n"
        "    name: Government of Sweden\n"
        "    base_url: https://www.regeringen.se\n"
        "    region: [sweden, nordic, eu]\n",
        encoding="utf-8",
    )
    (domains_dir / "api_sources.yaml").write_text(
        "domains:\n"
        "  - id: legiscan_api\n"
        "    name: LegiScan API\n"
        "    base_url: https://api.legiscan.com\n"
        "    region: [us, us_states]\n"
        "    source_type: legiscan\n"
        "  - id: govinfo_api\n"
        "    name: GovInfo API\n"
        "    base_url: https://api.govinfo.gov\n"
        "    region: [us]\n"
        "    source_type: govinfo\n"
        "  - id: regulations_gov_api\n"
        "    name: Regulations.gov API\n"
        "    base_url: https://api.regulations.gov\n"
        "    region: [us]\n"
        "    source_type: regulations_gov\n"
        "  - id: riksdagen_api\n"
        "    name: Riksdagen API\n"
        "    base_url: https://data.riksdagen.se\n"
        "    region: [sweden, nordic, eu]\n"
        "    source_type: riksdagen\n"
        "  - id: eurlex_nim_tracker\n"
        "    name: EUR-Lex NIM Tracker\n"
        "    base_url: https://eur-lex.europa.eu\n"
        "    region: [eu]\n"
        "    source_type: eurlex_nim\n"
        "  - id: uk_bills_api\n"
        "    name: UK Bills API\n"
        "    base_url: https://bills-api.parliament.uk\n"
        "    region: [uk]\n"
        "    source_type: uk_bills\n",
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
    return config


@pytest.fixture
def loader(config_dir):
    return ConfigLoader(config_dir=str(config_dir))


class TestResolvePlace:
    def test_us_state(self):
        place = resolve_place("California")
        assert place["kind"] == "us_state"
        assert place["region_key"] == "california"
        assert place["state_code"] == "CA"
        assert place["display"] == "California"

    def test_us_state_two_words(self):
        place = resolve_place("new york")
        assert place["kind"] == "us_state"
        assert place["region_key"] == "new_york"
        assert place["state_code"] == "NY"

    def test_us_federal_aliases(self):
        for q in ("US", "USA", "United States", "america"):
            place = resolve_place(q)
            assert place["kind"] == "us_federal", q
            assert place["region_key"] == "us"

    def test_country(self):
        place = resolve_place("Sweden")
        assert place["kind"] == "country"
        assert place["region_key"] == "sweden"

    def test_country_alias_czechia(self):
        assert resolve_place("Czechia")["region_key"] == "czech_republic"

    def test_uk_aliases(self):
        for q in ("UK", "United Kingdom", "Britain"):
            assert resolve_place(q)["region_key"] == "uk", q

    def test_eu_aliases(self):
        for q in ("EU", "European Union"):
            place = resolve_place(q)
            assert place["kind"] == "eu", q
            assert place["region_key"] == "eu"

    def test_region_group(self):
        place = resolve_place("Nordic")
        assert place["kind"] == "region_group"
        assert place["region_key"] == "nordic"

    def test_unknown(self):
        place = resolve_place("Atlantis")
        assert place["kind"] == "unknown"

    def test_empty(self):
        assert resolve_place("")["kind"] == "unknown"


class TestBuildSearchPlan:
    def test_us_state_plan_includes_state_sites_and_us_law_apis(self, loader):
        plan = build_search_plan("California", terms=None, config=loader)
        ids = {s["id"] for s in plan["sources"]}
        assert "ca_energy" in ids            # state website
        assert "legiscan_api" in ids         # covers all US states
        assert "govinfo_api" in ids          # federal layer
        assert "regulations_gov_api" in ids  # federal rulemaking (early)
        assert "riksdagen_api" not in ids

    def test_us_state_plan_scopes_legiscan_to_state(self, loader):
        plan = build_search_plan("California", terms=None, config=loader)
        assert plan["source_params"]["state"] == "CA"

    def test_us_state_targets_resolvable_by_config(self, loader):
        plan = build_search_plan("California", terms=None, config=loader)
        resolved = {d["id"] for d in loader.get_enabled_domains(plan["targets"])}
        assert {s["id"] for s in plan["sources"]} == resolved

    def test_eu_country_plan_includes_transposition(self, loader):
        plan = build_search_plan("Sweden", terms=None, config=loader)
        ids = {s["id"] for s in plan["sources"]}
        assert "sweden_regeringen" in ids
        assert "riksdagen_api" in ids
        assert "eurlex_nim_tracker" in ids   # EU member -> NIM tracker
        assert "legiscan_api" not in ids

    def test_channels_derived_from_sources(self, loader):
        plan = build_search_plan("Sweden", terms=None, config=loader)
        assert set(plan["channels"]) == {"crawl", "law_apis", "transposition"}

    def test_terms_flow_into_source_params(self, loader):
        plan = build_search_plan("California", terms=["thermal energy network"], config=loader)
        assert plan["source_params"]["terms"] == ["thermal energy network"]

    def test_no_terms_omits_terms_param(self, loader):
        plan = build_search_plan("California", terms=None, config=loader)
        assert "terms" not in plan["source_params"]

    def test_unknown_place_warns_and_has_no_targets(self, loader):
        plan = build_search_plan("Atlantis", terms=None, config=loader)
        assert plan["sources"] == []
        assert plan["targets"] == ""
        assert any("Atlantis" in w for w in plan["warnings"])

    def test_missing_api_key_warned(self, loader, monkeypatch):
        monkeypatch.delenv("GOVINFO_API_KEY", raising=False)
        plan = build_search_plan("California", terms=None, config=loader)
        assert any("GOVINFO_API_KEY" in w for w in plan["warnings"])
        govinfo = next(s for s in plan["sources"] if s["id"] == "govinfo_api")
        assert govinfo["requires_key"] is True
        assert govinfo["key_present"] is False

    def test_legiscan_estimate_present_for_us(self, loader, monkeypatch):
        monkeypatch.setenv("LEGISCAN_API_KEY", "x")
        plan = build_search_plan("California", terms=None, config=loader)
        est = plan["estimate"]["legiscan"]
        assert est is not None
        assert est["max_queries"] > 0
        assert "remaining" in est

    def test_legiscan_estimate_absent_for_sweden(self, loader):
        plan = build_search_plan("Sweden", terms=None, config=loader)
        assert plan["estimate"]["legiscan"] is None

    def test_llm_ceiling_scales_with_cost_level(self, loader):
        low = build_search_plan("Sweden", terms=None, config=loader, cost_level="low")
        high = build_search_plan("Sweden", terms=None, config=loader, cost_level="high")
        assert high["estimate"]["llm_ceiling_usd"] > low["estimate"]["llm_ceiling_usd"]

    def test_sources_have_descriptions(self, loader):
        plan = build_search_plan("Sweden", terms=None, config=loader)
        for source in plan["sources"]:
            assert source["description"]
            assert source["kind"] in {"website", "law_api", "transposition"}

    def test_uk_devolved_includes_uk_bills(self, loader):
        plan = build_search_plan("Scotland", terms=None, config=loader)
        ids = {s["id"] for s in plan["sources"]}
        assert "uk_bills_api" in ids
