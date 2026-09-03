"""Tests for instrument-key normalisation and the InstrumentIndex used by
the same-instrument duplicate fold (WP-4).

See docs/HOW_IT_WORKS.md, "Same instrument, one row", and
docs/decisions/ADR-0010-same-instrument-folds-into-the-existing-row.md.
"""

import pytest

from src.core.instruments import InstrumentIndex, instrument_keys


@pytest.mark.small
class TestInstrumentKeysTable:
    """At least ten names, including the reviewer's four EnEfG variants."""

    def test_english_name_with_abbreviation(self):
        keys = instrument_keys("Energy Efficiency Act (EnEfG)")
        assert keys == {"energy efficiency act", "enefg"}

    def test_german_short_form_with_abbreviation(self):
        keys = instrument_keys("Energieeffizienzgesetz (EnEfG)")
        assert keys == {"energieeffizienzgesetz", "enefg"}

    def test_english_gloss_with_abbreviation(self):
        keys = instrument_keys("German Energy Efficiency Act for Data Centres (EnEfG)")
        assert keys == {"german energy efficiency act for data centres", "enefg"}

    def test_draft_bill_title_with_trailing_qualifier_still_yields_the_abbreviation(self):
        # The exact crawl-page title from the scanner's FAILS-TODAY test:
        # the " - Referentenentwurf" tail is a trailing qualifier, stripped
        # before the parenthesised abbreviation is read, so this still
        # shares the "enefg" key with the other three variants above.
        keys = instrument_keys("Energieeffizienzgesetz (EnEfG) - Referentenentwurf")
        assert keys == {"energieeffizienzgesetz", "enefg"}

    def test_duplicate_calls_dedupe_into_one_key(self):
        keys = instrument_keys(
            "American Energy Efficiency Act of 2024",
            "American Energy Efficiency Act of 2024",
        )
        assert keys == {"american energy efficiency act of 2024"}

    def test_year_suffix_is_dropped_and_yields_no_abbreviation(self):
        keys = instrument_keys("Climate Resilience Act (2024)")
        assert keys == {"climate resilience act"}

    def test_diacritics_are_folded(self):
        keys = instrument_keys("Loi sur l'efficacité énergétique")
        assert keys == {"loi sur l efficacite energetique"}

    def test_parenthetical_too_long_to_be_an_abbreviation(self):
        keys = instrument_keys(
            "Energieeffizienz-Gesetz (Deutsches Energieeffizienzgesetz "
            "für Rechenzentren)"
        )
        assert keys == {"energieeffizienz gesetz"}

    def test_empty_name_yields_nothing(self):
        assert instrument_keys("") == set()
        assert instrument_keys(None) == set()

    def test_multiple_names_in_one_call_union_their_keys(self):
        keys = instrument_keys(
            "Energy Efficiency Act (EnEfG)", "Climate Resilience Act (2024)",
        )
        assert keys == {"energy efficiency act", "enefg", "climate resilience act"}

    def test_short_keys_are_discarded(self):
        assert instrument_keys("Ab") == set()


@pytest.mark.small
class TestInstrumentIndex:
    def test_from_rows_ignores_rows_without_names(self):
        index = InstrumentIndex.from_rows([
            {"url": "https://a.gov/no-name"},
            {"policy_name": "", "policy_name_en": "", "url": "https://a.gov/blank"},
        ])
        assert index.match(instrument_keys("Anything At All")) is None

    def test_match_returns_the_url(self):
        index = InstrumentIndex.from_rows([
            {
                "policy_name": "Energy Efficiency Act (EnEfG)",
                "url": "https://www.gesetze-im-internet.de/enefg/",
            },
        ])
        keys = instrument_keys("Energieeffizienzgesetz (EnEfG)")
        assert index.match(keys) == "https://www.gesetze-im-internet.de/enefg/"

    def test_no_match_returns_none(self):
        index = InstrumentIndex.from_rows([
            {"policy_name": "Energy Efficiency Act (EnEfG)", "url": "https://a.gov/enefg"},
        ])
        assert index.match(instrument_keys("Unrelated Statute")) is None

    def test_a_policys_own_url_is_not_a_match_for_itself(self):
        index = InstrumentIndex.from_rows([
            {"policy_name": "Energy Efficiency Act (EnEfG)", "url": "https://a.gov/enefg"},
        ])
        keys = instrument_keys("Energy Efficiency Act (EnEfG)")
        assert index.match(keys, exclude_url="https://a.gov/enefg") is None
        # A different page with the same keys still matches.
        assert index.match(keys, exclude_url="https://other.gov/x") == "https://a.gov/enefg"

    def test_add_makes_a_later_match_hit(self):
        index = InstrumentIndex()
        keys = instrument_keys("Brand New Act (BNA)")
        assert index.match(keys) is None
        index.add({"policy_name": "Brand New Act (BNA)", "url": "https://a.gov/bna"})
        assert index.match(keys) == "https://a.gov/bna"

    def test_add_accepts_an_object_with_attributes_not_just_a_dict(self):
        """Scanner code adds Policy pydantic models, not dicts."""

        class _FakePolicy:
            policy_name = "Object Act (OA)"
            policy_name_en = None
            url = "https://a.gov/oa"

        index = InstrumentIndex()
        index.add(_FakePolicy())
        assert index.match(instrument_keys("Object Act (OA)")) == "https://a.gov/oa"

    def test_add_without_url_is_ignored(self):
        index = InstrumentIndex()
        index.add({"policy_name": "No Url Act (NUA)"})
        assert index.match(instrument_keys("No Url Act (NUA)")) is None
