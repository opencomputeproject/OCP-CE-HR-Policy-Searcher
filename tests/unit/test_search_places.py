"""Tests for place suggestions: every suggestion MUST resolve.

Regression: the search box's autocomplete was populated with region
DESCRIPTIONS ("US state governments", "Nordic countries") that
resolve_place rejected - the UI suggested inputs that then failed.
"""

import pytest
from fastapi.testclient import TestClient

from src.core.search_plan import resolve_place, suggested_places


class TestSuggestedPlaces:
    def test_every_suggestion_resolves(self):
        for name in suggested_places():
            assert resolve_place(name)["kind"] != "unknown", name

    def test_alphabetized(self):
        names = suggested_places()
        assert names == sorted(names, key=str.lower)

    def test_no_duplicates(self):
        names = suggested_places()
        assert len(names) == len(set(names))

    def test_core_places_present(self):
        names = set(suggested_places())
        for expected in (
            "California", "Sweden", "Germany", "United States",
            "United Kingdom", "European Union", "Nordic",
        ):
            assert expected in names, expected

    def test_descriptions_not_leaked(self):
        # The old bug: VALID_REGIONS descriptions in the list.
        names = set(suggested_places())
        assert "US state governments" not in names
        assert "United States (federal and state)" not in names
        assert "Nordic countries" not in names


class TestResolveNaturalVariants:
    """Common human phrasings should resolve instead of erroring."""

    def test_nordic_countries(self):
        assert resolve_place("Nordic countries")["region_key"] == "nordic"

    def test_parenthetical_stripped(self):
        assert resolve_place("United States (federal and state)")["region_key"] == "us"

    def test_us_states_phrase(self):
        assert resolve_place("US states")["region_key"] == "us_states"
        assert resolve_place("US state governments")["region_key"] == "us_states"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    from src.api.app import app

    with TestClient(app) as c:
        yield c


class TestPlacesEndpoint:
    def test_returns_alphabetized_names(self, client):
        resp = client.get("/api/search/places")
        assert resp.status_code == 200
        data = resp.json()
        assert "California" in data["places"]
        assert data["places"] == sorted(data["places"], key=str.lower)
