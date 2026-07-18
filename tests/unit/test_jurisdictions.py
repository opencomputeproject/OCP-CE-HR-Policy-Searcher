"""Tests for the canonical jurisdiction registry (src/core/jurisdictions.py).

These pin the real mess in data/policies.json: the exact free-text
jurisdiction strings the LLM has written must resolve to canonical rows, and
every region slug currently used in config/domains/**/*.yaml must be known.
Unknown input must never crash — it returns None, warns, and is counted.
"""

import glob
import os

import pytest
import yaml

from src.core import jurisdictions
from src.core.config import VALID_REGIONS


@pytest.fixture(autouse=True)
def _reset_registry_caches():
    """Force a fresh load and clear the unresolved counter between tests."""
    jurisdictions._by_slug = None
    jurisdictions._alias_index = None
    jurisdictions._alias_by_len = None
    jurisdictions._unresolved.clear()
    yield


# --- The exact strings that exist in data/policies.json today ---

class TestRealPolicyStrings:
    def test_sweden_eu(self):
        j = jurisdictions.resolve_text("Sweden (EU)")
        assert j is not None and j.slug == "sweden" and j.iso3 == "SWE"

    def test_wallonia_belgium(self):
        j = jurisdictions.resolve_text("Wallonia, Belgium")
        assert j is not None and j.slug == "belgium" and j.iso3 == "BEL"

    def test_minnesota_usa(self):
        j = jurisdictions.resolve_text("Minnesota, USA")
        assert j is not None and j.slug == "minnesota" and j.kind == "us_state"
        assert jurisdictions.country_of(j).iso3 == "USA"

    def test_germany_variants_same_jurisdiction(self):
        a = jurisdictions.resolve_text("Germany (Federal)")
        b = jurisdictions.resolve_text("Germany (Peine, Lower Saxony)")
        assert a is not None and b is not None
        assert a.slug == b.slug == "germany" and a.iso3 == "DEU"

    def test_us_three_strings_one_jurisdiction(self):
        for s in ("US", "United States", "United States (Federal)"):
            j = jurisdictions.resolve_text(s)
            assert j is not None and j.slug == "us" and j.iso3 == "USA", s

    def test_european_union_and_finland_annotation(self):
        eu = jurisdictions.resolve_text("European Union")
        assert eu is not None and eu.slug == "eu" and eu.kind == "supranational"
        fin = jurisdictions.resolve_text("Finland (EU-wide regulation)")
        assert fin is not None and fin.slug == "finland"

    def test_england_united_kingdom(self):
        j = jurisdictions.resolve_text("England (United Kingdom)")
        assert j is not None and j.slug == "uk" and j.iso3 == "GBR"

    def test_brussels_capital_region_both_spellings(self):
        for s in ("Brussels Capital Region, Belgium",
                  "Brussels-Capital Region, Belgium"):
            j = jurisdictions.resolve_text(s)
            assert j is not None and j.slug == "belgium" and j.iso3 == "BEL", s

    @pytest.mark.parametrize("string, slug", [
        ("Denmark", "denmark"),
        ("Japan", "japan"),
        ("Netherlands", "netherlands"),
        ("New Jersey, United States", "new_jersey"),
        ("Washington State, USA", "washington"),
        ("Georgia, United States", "georgia"),
        ("Belgium (Flanders)", "belgium"),
        ("Flanders, Belgium", "belgium"),
        ("Connecticut, United States", "connecticut"),
        ("California, USA", "california"),
        ("Canada (Federal)", "canada"),
        ("Michigan, USA", "michigan"),
        ("European Union (analyzed by Sweden)", "eu"),
    ])
    def test_remaining_policy_strings(self, string, slug):
        j = jurisdictions.resolve_text(string)
        assert j is not None and j.slug == slug, string

    def test_georgia_with_us_context_is_the_state_not_a_country(self):
        j = jurisdictions.resolve_text("Georgia, United States")
        assert j.kind == "us_state"
        assert jurisdictions.country_of(j).slug == "us"


# --- Every slug used across the domain configs must resolve ---

class TestDomainConfigSlugs:
    def _config_slugs(self):
        slugs = set()
        root = os.path.join(os.path.dirname(__file__), "..", "..")
        pattern = os.path.join(root, "config", "domains", "**", "*.yaml")
        for path in glob.glob(pattern, recursive=True):
            if os.path.basename(path).startswith("_"):
                continue
            data = yaml.safe_load(open(path, encoding="utf-8")) or {}
            for dom in (data.get("domains") or []):
                for r in (dom.get("region") or []):
                    slugs.add(r)
        return slugs

    def test_every_domain_slug_resolves(self):
        unresolved = sorted(
            s for s in self._config_slugs() if jurisdictions.get(s) is None
        )
        assert unresolved == [], f"slugs missing from registry: {unresolved}"

    def test_registry_covers_valid_regions(self):
        missing = sorted(s for s in VALID_REGIONS if jurisdictions.get(s) is None)
        assert missing == [], f"VALID_REGIONS not in registry: {missing}"


# --- Rollups and group expansion ---

class TestRollups:
    def test_members_of_eu(self):
        members = {j.slug for j in jurisdictions.members_of("eu")}
        assert "sweden" in members and "germany" in members
        assert "us" not in members

    def test_country_of_zurich_is_switzerland(self):
        c = jurisdictions.country_of("zurich")
        assert c is not None and c.slug == "switzerland" and c.iso3 == "CHE"

    def test_country_of_country_is_itself(self):
        assert jurisdictions.country_of("germany").slug == "germany"

    def test_country_of_group_is_none(self):
        assert jurisdictions.country_of("nordic") is None

    def test_members_of_unknown_is_empty(self):
        assert jurisdictions.members_of("atlantis") == []

    def test_members_of_non_group_is_empty(self):
        assert jurisdictions.members_of("sweden") == []


# --- Unknown input never crashes ---

class TestUnknownInput:
    def test_unknown_returns_none_and_is_counted(self):
        assert jurisdictions.resolve_text("Kingdom of Atlantis") is None
        assert jurisdictions.unresolved_report().get("Kingdom of Atlantis") == 1

    def test_unknown_slug_get_returns_none(self):
        assert jurisdictions.get("narnia") is None

    def test_none_and_empty_never_raise(self):
        assert jurisdictions.resolve_text(None) is None
        assert jurisdictions.resolve_text("") is None
        assert jurisdictions.resolve_text("   ") is None
        assert jurisdictions.get(None) is None
        assert jurisdictions.country_of("narnia") is None

    def test_repeated_miss_increments_count(self):
        jurisdictions.resolve_text("Freedonia")
        jurisdictions.resolve_text("Freedonia")
        assert jurisdictions.unresolved_report()["Freedonia"] == 2
