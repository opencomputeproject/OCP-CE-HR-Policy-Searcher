"""Tests for GET /api/coverage (world-map coverage endpoint).

Coverage is computed at read time from the merged jurisdiction registry:
policies (data/policies.json) resolve via ``resolve_text`` and roll up to a
country via ``country_of``; policies that resolve above the country level land
in the ``supranational`` array. Source counts come from the domain configs'
``region`` tags via the same rollup.

These tests pin the same real jurisdiction strings that
``test_jurisdictions.py`` pins, and the invariant that every policy lands
somewhere: ``sum(country policies) + sum(supranational policies) == total``.
"""

import pytest
from fastapi.testclient import TestClient

from src.core import jurisdictions
from src.api.routes.coverage import compute_children, compute_coverage


@pytest.fixture(autouse=True)
def _reset_registry_caches():
    """Force a fresh registry load and clear the miss counter between tests."""
    jurisdictions._by_slug = None
    jurisdictions._alias_index = None
    jurisdictions._alias_by_len = None
    jurisdictions._unresolved.clear()
    yield


def _pol(jurisdiction, name, score=5):
    """Minimal policy dict shaped like data/policies.json rows."""
    return {
        "jurisdiction": jurisdiction,
        "policy_name": name,
        "relevance_score": score,
        "url": f"https://example.gov/{name.replace(' ', '-').lower()}",
    }


def _iso(text):
    return jurisdictions.resolve_text(text).iso_numeric


def _by_iso(countries, iso):
    return next((c for c in countries if c["iso_numeric"] == iso), None)


def _by_slug(supra, slug):
    return next((s for s in supra if s["slug"] == slug), None)


class TestPolicyAttribution:
    """The real jurisdiction strings resolve to the right map bucket."""

    def test_sweden_eu_string_lands_on_sweden_not_eu(self):
        # The registry attributes "Sweden (EU)" to Sweden, not the EU bucket —
        # the exact case the design proposal calls out.
        cov = compute_coverage([_pol("Sweden (EU)", "SE heat rule")], [])
        swe = _by_iso(cov["countries"], _iso("Sweden"))
        assert swe is not None and swe["policies"] == 1
        assert cov["supranational"] == []

    def test_european_union_string_lands_supranational(self):
        cov = compute_coverage([_pol("European Union", "EED Article 26")], [])
        assert cov["countries"] == []
        eu = _by_slug(cov["supranational"], "eu")
        assert eu is not None and eu["policies"] == 1
        assert "iso_numeric" not in eu  # supranational has no country shape

    def test_three_us_spellings_collapse_to_one_country(self):
        cov = compute_coverage(
            [
                _pol("US", "a"),
                _pol("United States", "b"),
                _pol("United States (Federal)", "c"),
            ],
            [],
        )
        us = _by_iso(cov["countries"], _iso("US"))
        assert us is not None and us["policies"] == 3
        assert len(cov["countries"]) == 1

    def test_us_state_rolls_up_to_country(self):
        cov = compute_coverage(
            [_pol("Minnesota, USA", "MN"), _pol("California, USA", "CA")], []
        )
        us = _by_iso(cov["countries"], _iso("US"))
        assert us is not None and us["policies"] == 2

    def test_region_country_form_rolls_up(self):
        # "Wallonia, Belgium" -> Belgium; "Germany (Federal)" -> Germany.
        cov = compute_coverage(
            [_pol("Wallonia, Belgium", "w"), _pol("Germany (Federal)", "g")], []
        )
        assert _by_iso(cov["countries"], _iso("Belgium"))["policies"] == 1
        assert _by_iso(cov["countries"], _iso("Germany"))["policies"] == 1


class TestSumInvariant:
    """Every policy lands somewhere: country + supranational == total."""

    def test_sum_equals_total_over_mixed_strings(self):
        policies = [
            _pol("Sweden (EU)", "1"),
            _pol("Sweden", "2"),
            _pol("Denmark", "3"),
            _pol("Minnesota, USA", "4"),
            _pol("US", "5"),
            _pol("United States (Federal)", "6"),
            _pol("European Union", "7"),
            _pol("Wallonia, Belgium", "8"),
            _pol("Germany (Federal)", "9"),
        ]
        cov = compute_coverage(policies, [])
        country_total = sum(c["policies"] for c in cov["countries"])
        supra_total = sum(s["policies"] for s in cov["supranational"])
        assert country_total + supra_total == len(policies)
        assert cov["totals"]["policies"] == len(policies)


class TestTopPolicyNames:
    def test_top_names_capped_at_three_and_ranked_by_score(self):
        policies = [
            _pol("Sweden", "low", score=1),
            _pol("Sweden", "high", score=9),
            _pol("Sweden", "mid", score=5),
            _pol("Sweden", "lowest", score=0),
        ]
        cov = compute_coverage(policies, [])
        swe = _by_iso(cov["countries"], _iso("Sweden"))
        assert swe["policies"] == 4
        assert swe["top_policy_names"] == ["high", "mid", "low"]


class TestCountrySlug:
    """Every country entry carries the registry slug the map/panel need to
    call /api/policies?place=<slug> - added alongside iso_numeric, not in
    place of it."""

    def test_country_entry_carries_its_registry_slug(self):
        cov = compute_coverage(
            [_pol("Sweden (EU)", "s"), _pol("Wallonia, Belgium", "w")], []
        )
        swe = _by_iso(cov["countries"], _iso("Sweden"))
        bel = _by_iso(cov["countries"], _iso("Belgium"))
        assert swe["slug"] == "sweden"
        assert bel["slug"] == "belgium"

    def test_country_reached_only_via_source_still_carries_slug(self):
        cov = compute_coverage([], [{"id": "d1", "region": ["denmark"]}])
        dk = _by_iso(cov["countries"], _iso("Denmark"))
        assert dk["slug"] == "denmark"


class TestSourceAttribution:
    def _domains(self):
        return [
            {"id": "d1", "region": ["germany", "bayern"]},   # both -> Germany
            {"id": "d2", "region": ["us", "california"]},     # both -> US
            {"id": "d3", "region": ["eu"]},                   # supranational, no country
            {"id": "d4", "region": ["france"]},
            {"id": "d5", "region": []},                       # counts only in totals
        ]

    def test_domain_counted_once_per_country_despite_multiple_tags(self):
        cov = compute_coverage([], self._domains())
        assert _by_iso(cov["countries"], _iso("Germany"))["sources"] == 1
        assert _by_iso(cov["countries"], _iso("US"))["sources"] == 1
        assert _by_iso(cov["countries"], _iso("France"))["sources"] == 1

    def test_eu_only_source_does_not_create_a_country(self):
        cov = compute_coverage([], self._domains())
        # No country entry is created solely from an EU tag.
        assert all(c["iso_numeric"] is not None for c in cov["countries"])
        # EU has no policies here, so it is not a supranational entry either.
        assert cov["supranational"] == []

    def test_totals_sources_counts_every_domain(self):
        cov = compute_coverage([], self._domains())
        assert cov["totals"]["sources"] == 5

    def test_country_appears_with_sources_but_no_policies(self):
        cov = compute_coverage([], [{"id": "d1", "region": ["denmark"]}])
        dk = _by_iso(cov["countries"], _iso("Denmark"))
        assert dk is not None and dk["sources"] == 1 and dk["policies"] == 0


class TestDiagnostics:
    def test_unresolved_policy_string_is_reported(self):
        cov = compute_coverage([_pol("Kingdom of Atlantis", "x")], [])
        assert "Kingdom of Atlantis" in cov["diagnostics"]["unresolved_policies"]

    def test_unresolved_region_slug_is_reported(self):
        cov = compute_coverage([], [{"id": "d", "region": ["narnia"]}])
        assert "narnia" in cov["diagnostics"]["unresolved_region_slugs"]

    def test_clean_data_has_no_unresolved(self):
        cov = compute_coverage(
            [_pol("Sweden", "s")], [{"id": "d", "region": ["denmark"]}]
        )
        assert cov["diagnostics"]["unresolved_policies"] == []
        assert cov["diagnostics"]["unresolved_region_slugs"] == []


class TestNullIsoCountries:
    """A country the registry has no iso_numeric for (Kosovo today) belongs in
    the off-map tray keyed by slug - never in countries under a None key, and
    never colliding with another null-iso territory."""

    def _add_country(self, slug, name, iso3, code):
        from src.core.jurisdictions import Jurisdiction
        jurisdictions._load()
        jurisdictions._by_slug[slug] = Jurisdiction(
            slug=slug, name=name, kind="country",
            iso3=iso3, iso_numeric=None, code=code,
        )
        for key in (slug, jurisdictions._normalize(name)):
            jurisdictions._alias_index[key] = slug
        jurisdictions._alias_by_len = sorted(
            jurisdictions._alias_index.items(), key=lambda kv: -len(kv[0])
        )

    def test_null_iso_country_goes_offmap_not_countries(self):
        self._add_country("kosovo", "Kosovo", "XKX", "XK")
        cov = compute_coverage([_pol("Kosovo", "k1")], [])
        assert cov["countries"] == []
        ks = _by_slug(cov["supranational"], "kosovo")
        assert ks is not None and ks["policies"] == 1
        assert "iso_numeric" not in ks

    def test_null_iso_countries_do_not_collide(self):
        self._add_country("kosovo", "Kosovo", "XKX", "XK")
        self._add_country("northern_cyprus", "Northern Cyprus", "XNC", "XN")
        cov = compute_coverage(
            [_pol("Kosovo", "k"), _pol("Northern Cyprus", "n")], []
        )
        assert {s["slug"] for s in cov["supranational"]} == {
            "kosovo", "northern_cyprus"
        }
        assert all(s["policies"] == 1 for s in cov["supranational"])
        assert all(c["iso_numeric"] is not None for c in cov["countries"])

    def test_null_iso_country_source_counted_offmap(self):
        self._add_country("kosovo", "Kosovo", "XKX", "XK")
        cov = compute_coverage([], [{"id": "d1", "region": ["kosovo"]}])
        ks = _by_slug(cov["supranational"], "kosovo")
        assert ks is not None and ks["sources"] == 1 and ks["policies"] == 0
        assert cov["countries"] == []


class TestUnresolvedEdges:
    def test_policy_without_jurisdiction_key_does_not_crash(self):
        cov = compute_coverage(
            [{"policy_name": "x", "url": "u", "relevance_score": 1}], []
        )
        assert cov["countries"] == [] and cov["supranational"] == []
        assert cov["diagnostics"]["unresolved_policies"] == ["(no jurisdiction)"]
        assert cov["totals"]["policies"] == 1

    def test_resolved_without_a_country_is_reported_not_placed(self):
        from src.core.jurisdictions import Jurisdiction
        jurisdictions._load()
        # A state whose parent chain never reaches a country -> country_of None,
        # kind not supra/group -> falls through to the unresolved diagnostic.
        jurisdictions._by_slug["orphan_state"] = Jurisdiction(
            slug="orphan_state", name="Orphan State", kind="us_state",
            iso_numeric=None, parent=None,
        )
        for key in ("orphan_state", jurisdictions._normalize("Orphan State")):
            jurisdictions._alias_index[key] = "orphan_state"
        jurisdictions._alias_by_len = sorted(
            jurisdictions._alias_index.items(), key=lambda kv: -len(kv[0])
        )
        cov = compute_coverage([_pol("Orphan State", "x")], [])
        assert cov["countries"] == [] and cov["supranational"] == []
        assert "Orphan State" in cov["diagnostics"]["unresolved_policies"]


# --- Route wiring (registration + response shape) ---

class _FakeStore:
    def __init__(self, policies):
        self._policies = policies

    def get_all(self):
        return list(self._policies)


class _FakeConfig:
    def __init__(self, domains):
        self._domains = domains

    def get_enabled_domains(self, group="all"):
        return list(self._domains)


class _FakePolicy:
    """Stands in for a core.models.Policy - only model_dump is exercised."""

    def __init__(self, data):
        self._data = data

    def model_dump(self, mode="json"):
        return dict(self._data)


class _FakeManager:
    def __init__(self, policies=None):
        self._policies = policies or []

    def get_all_policies(self):
        return list(self._policies)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    from src.api.app import app
    from src.api import deps

    store = _FakeStore([_pol("Sweden (EU)", "s"), _pol("European Union", "e")])
    config = _FakeConfig([{"id": "d1", "region": ["sweden"]}])
    app.dependency_overrides[deps.get_policy_store] = lambda: store
    app.dependency_overrides[deps.get_scan_manager] = lambda: _FakeManager([])
    app.dependency_overrides[deps.get_config] = lambda: config
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _coverage_client(store, manager, config):
    from src.api.app import app
    from src.api import deps

    app.dependency_overrides[deps.get_policy_store] = lambda: store
    app.dependency_overrides[deps.get_scan_manager] = lambda: manager
    app.dependency_overrides[deps.get_config] = lambda: config
    return app


class TestRouteWiring:
    def test_coverage_endpoint_shape(self, client):
        resp = client.get("/api/coverage")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"countries", "supranational", "totals"}
        assert body["totals"] == {"sources": 1, "policies": 2}
        swe = _by_iso(body["countries"], _iso("Sweden"))
        assert swe["policies"] == 1 and swe["sources"] == 1
        assert set(swe) == {"name", "slug", "iso_numeric", "sources", "policies",
                            "top_policy_names", "children_with_data"}
        assert swe["slug"] == "sweden"
        assert swe["children_with_data"] == 0
        eu = _by_slug(body["supranational"], "eu")
        assert eu["policies"] == 1
        assert set(eu) == {"name", "slug", "sources", "policies", "top_policy_names"}

    def test_unresolved_endpoint(self, client):
        resp = client.get("/api/coverage/unresolved")
        assert resp.status_code == 200
        body = resp.json()
        assert body["unresolved_policies"] == []
        assert body["unresolved_region_slugs"] == []


class TestFreshness:
    """Coverage must reflect in-memory scan results, not just the persisted
    snapshot - the same freshness /api/policies gives (merge, dedupe by URL)."""

    def test_in_memory_scan_policies_are_merged(self):
        store = _FakeStore([_pol("Sweden", "persisted")])
        manager = _FakeManager([_FakePolicy(_pol("Denmark", "just-scanned"))])
        app = _coverage_client(store, manager, _FakeConfig([]))
        try:
            with TestClient(app) as c:
                body = c.get("/api/coverage").json()
        finally:
            app.dependency_overrides.clear()
        assert body["totals"]["policies"] == 2
        assert _by_iso(body["countries"], _iso("Denmark"))["policies"] == 1

    def test_duplicate_url_across_store_and_manager_counted_once(self):
        shared = _pol("Sweden", "same-policy")
        store = _FakeStore([shared])
        manager = _FakeManager([_FakePolicy(dict(shared))])
        app = _coverage_client(store, manager, _FakeConfig([]))
        try:
            with TestClient(app) as c:
                body = c.get("/api/coverage").json()
        finally:
            app.dependency_overrides.clear()
        assert body["totals"]["policies"] == 1
        assert _by_iso(body["countries"], _iso("Sweden"))["policies"] == 1


# --- GET /api/coverage/children (per-country state/province drill-down) ---
#
# data/policies.json is gitignored runtime output; test_full_pipeline.py's own
# isolation note says tests "must not see the developer's real data/policies.json".
# So, like test_jurisdictions.py, the real strings are pinned here as literals
# rather than read from the live file at test time.

class TestChildrenOfCountry:
    """The exact strings + counts that resolve to a US state in
    data/policies.json today (17 total): New Jersey x5, Minnesota x4,
    Washington State x3, Georgia x2, Connecticut x1, California x1, Michigan x1
    — same real strings test_jurisdictions.py pins."""

    _US_STATE_STRINGS = (
        ["New Jersey, United States"] * 5
        + ["Minnesota, USA"] * 4
        + ["Washington State, USA"] * 3
        + ["Georgia, United States"] * 2
        + ["Connecticut, United States"]
        + ["California, USA"]
        + ["Michigan, USA"]
    )

    def _us_policies(self):
        state_policies = [
            _pol(s, f"state-{i}") for i, s in enumerate(self._US_STATE_STRINGS)
        ]
        national_policies = [
            _pol("US", "federal-a"), _pol("United States (Federal)", "federal-b"),
        ]
        other_policies = [_pol("Sweden", "unrelated")]
        return state_policies + national_policies + other_policies

    def test_us_children_include_states_with_policies(self):
        policies = self._us_policies()
        # Derive the expected count dynamically via resolve_text rather than
        # hardcoding "17" — proves the bucketing rule, not just the fixture.
        expected_state_count = sum(
            1 for p in policies
            if jurisdictions.resolve_text(p["jurisdiction"]).kind == "us_state"
        )
        result = compute_children("us", policies, [])
        assert sum(c["policies"] for c in result["children"]) == expected_state_count
        assert result["national"]["policies"] == 2
        # Sweden's policy must not leak into the US breakdown.
        total_in_response = (
            sum(c["policies"] for c in result["children"]) + result["national"]["policies"]
        )
        assert total_in_response == len(policies) - 1

    def test_us_children_with_data_is_positive_and_reconciles(self):
        policies = self._us_policies()
        cov = compute_coverage(policies, [])
        us = _by_iso(cov["countries"], _iso("US"))
        assert us["children_with_data"] > 0
        result = compute_children("us", policies, [])
        # Every policy resolves to exactly one jurisdiction (resolve_text), so
        # national + children reconciles exactly with the world view's total
        # for that country.
        assert result["totals"]["policies"] == us["policies"]

    def test_children_sorted_by_policies_desc_then_name(self):
        result = compute_children("us", self._us_policies(), [])
        slugs = [c["slug"] for c in result["children"]]
        assert slugs[0] == "new_jersey"  # 5 policies, the most
        assert slugs[1] == "minnesota"  # 4 policies

    def test_top_policy_names_capped_at_three_per_child(self):
        result = compute_children("us", self._us_policies(), [])
        nj = next(c for c in result["children"] if c["slug"] == "new_jersey")
        assert len(nj["top_policy_names"]) == 3


class TestChildrenSourcesBucketing:
    """Sources bucket per-region-tag (a domain tagged for a child slug counts
    for that child; tagged for the country slug counts for national), so a
    domain tagged for both the country and one of its states legitimately
    appears in both buckets. ``totals.sources`` however counts DISTINCT
    domains — the same semantics as the world endpoint's per-country number —
    so the honest invariant is ``national + sum(children) >= totals``, with
    equality only when no domain spans buckets."""

    def test_domain_tagged_for_child_counts_only_for_that_child(self):
        domains = [{"id": "d1", "region": ["california"]}]
        result = compute_children("us", [], domains)
        ca = next(c for c in result["children"] if c["slug"] == "california")
        assert ca["sources"] == 1
        assert result["national"]["sources"] == 0
        assert result["totals"]["sources"] == 1

    def test_domain_tagged_for_country_counts_for_national_only(self):
        domains = [{"id": "d1", "region": ["us"]}]
        result = compute_children("us", [], domains)
        assert result["national"]["sources"] == 1
        assert result["children"] == []  # no data landed on any state
        assert result["totals"]["sources"] == 1

    def test_domain_tagged_for_both_appears_in_both_buckets_but_totals_dedupes(self):
        domains = [{"id": "d1", "region": ["us", "california"]}]
        result = compute_children("us", [], domains)
        assert result["national"]["sources"] == 1
        ca = next(c for c in result["children"] if c["slug"] == "california")
        assert ca["sources"] == 1
        # One distinct domain: totals dedupes, buckets keep the real overlap.
        assert result["totals"]["sources"] == 1
        bucket_sum = result["national"]["sources"] + sum(
            c["sources"] for c in result["children"]
        )
        assert bucket_sum >= result["totals"]["sources"]


class TestChildrenNoDataOmitted:
    def test_child_with_zero_sources_and_zero_policies_is_omitted(self):
        # Switzerland has one registered subnational child (zurich) but no
        # data attributed to it here — it must not appear as a zero row.
        result = compute_children(
            "switzerland", [_pol("Switzerland", "national-only")], []
        )
        assert result["children"] == []
        assert result["national"]["policies"] == 1

    def test_country_with_no_registered_children_returns_empty_children(self):
        # Denmark has no us_state/subnational rows in the registry at all.
        cov_policies = [_pol("Denmark", "a"), _pol("Denmark", "b")]
        cov = compute_coverage(cov_policies, [])
        dk = _by_iso(cov["countries"], _iso("Denmark"))
        result = compute_children("denmark", cov_policies, [])
        assert result["children"] == []
        assert result["national"]["policies"] == dk["policies"] == 2
        assert result["totals"] == {"sources": dk["sources"], "policies": dk["policies"]}


class TestChildrenUnknownParent:
    def test_unknown_slug_returns_none(self):
        assert compute_children("atlantis", [], []) is None

    def test_non_country_parent_returns_none(self):
        # "california" is a real registry slug, but a us_state, not a country.
        assert compute_children("california", [], []) is None

    def test_supranational_parent_returns_none(self):
        assert compute_children("eu", [], []) is None


class TestChildrenGenericInvariant:
    """Not hardcoded to the US: walks every country the registry currently
    gives child jurisdictions to, and proves BOTH totals fields reconcile with
    the world endpoint's entry for that country. Belgian/German subnational
    rows landing in a parallel branch (per the map drill-down plan) get
    covered here automatically, with no test change."""

    def _countries_with_registered_children(self):
        jurisdictions._load()
        return [
            j for j in jurisdictions._by_slug.values()
            if j.kind == "country" and jurisdictions.children_of(j)
        ]

    def test_every_drillable_country_reconciles_with_world_entry(self):
        countries = self._countries_with_registered_children()
        assert countries, "registry currently has no country with subnational/us_state children"

        policies = []
        domains = []
        for country in countries:
            policies.append(_pol(country.name, f"{country.slug}-national"))
            children = jurisdictions.children_of(country)
            for child in children:
                policies.append(_pol(child.name, f"{child.slug}-policy"))
                domains.append(
                    {"id": f"src-{child.slug}", "region": [child.slug]}
                )
            # A multi-tag domain spanning national + first child: the world
            # endpoint counts it once for the country, so totals.sources here
            # must too (per-bucket counts still both see it).
            domains.append(
                {
                    "id": f"src-{country.slug}-span",
                    "region": [country.slug, children[0].slug],
                }
            )

        cov = compute_coverage(policies, domains)
        drillable = [c for c in cov["countries"] if c["children_with_data"] > 0]
        assert drillable, "fixture should make every listed country drillable"

        for c in drillable:
            country = jurisdictions.resolve_text(c["name"])
            result = compute_children(country.slug, policies, domains)
            assert result["totals"]["policies"] == c["policies"], country.slug
            assert result["totals"]["sources"] == c["sources"], country.slug
            assert result["national"]["policies"] == 1
            assert len(result["children"]) == c["children_with_data"]
            bucket_sum = result["national"]["sources"] + sum(
                ch["sources"] for ch in result["children"]
            )
            assert bucket_sum >= result["totals"]["sources"], country.slug


# --- Route wiring: GET /api/coverage/children ---

class _ChildrenFakeStore:
    def __init__(self, policies):
        self._policies = policies

    def get_all(self):
        return list(self._policies)


@pytest.fixture
def children_client():
    from src.api.app import app
    from src.api import deps

    policies = (
        [_pol("New Jersey, United States", f"nj-{i}") for i in range(2)]
        + [_pol("US", "federal")]
    )
    store = _ChildrenFakeStore(policies)
    config = _FakeConfig([])
    app.dependency_overrides[deps.get_policy_store] = lambda: store
    app.dependency_overrides[deps.get_scan_manager] = lambda: _FakeManager([])
    app.dependency_overrides[deps.get_config] = lambda: config
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestChildrenRouteWiring:
    def test_children_endpoint_shape_for_us(self, children_client):
        resp = children_client.get("/api/coverage/children", params={"parent": "us"})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"parent", "national", "children", "totals"}
        assert body["parent"] == {
            "slug": "us", "name": "United States", "iso_numeric": "840",
        }
        assert body["national"]["policies"] == 1
        nj = next(c for c in body["children"] if c["slug"] == "new_jersey")
        assert nj["policies"] == 2 and nj["kind"] == "us_state" and nj["code"] == "US-NJ"
        assert body["totals"] == {"sources": 0, "policies": 3}

    def test_unknown_parent_returns_404_standard_envelope(self, children_client):
        resp = children_client.get(
            "/api/coverage/children", params={"parent": "atlantis"}
        )
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_non_country_parent_returns_404(self, children_client):
        resp = children_client.get(
            "/api/coverage/children", params={"parent": "california"}
        )
        assert resp.status_code == 404
        assert "detail" in resp.json()
