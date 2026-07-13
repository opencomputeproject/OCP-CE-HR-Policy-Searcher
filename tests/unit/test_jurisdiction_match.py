"""Tests for jurisdiction matching in search_policies.

Regression: a stored jurisdiction of "US" was invisible to a query for
"United States" / "USA" because the filter did a one-directional
substring match. Reader questions phrase countries in full, so the
match must be alias-aware and bidirectional — without false positives
like "US" matching "Belarus".
"""

from src.agent.tools import jurisdiction_matches


class TestUsAliases:
    def test_full_name_matches_abbreviation(self):
        assert jurisdiction_matches("United States", "US")
        assert jurisdiction_matches("USA", "US")
        assert jurisdiction_matches("united states of america", "US")

    def test_abbreviation_matches_full_name(self):
        assert jurisdiction_matches("US", "United States")

    def test_us_does_not_match_belarus(self):
        assert not jurisdiction_matches("US", "Belarus")

    def test_us_does_not_match_unrelated_country(self):
        assert not jurisdiction_matches("United States", "Sweden")


class TestUkAndEuAliases:
    def test_uk_full_name(self):
        assert jurisdiction_matches("United Kingdom", "UK")
        assert jurisdiction_matches("UK", "United Kingdom")

    def test_eu_matches_member_annotation(self):
        # "Sweden (EU)" should surface for an EU query
        assert jurisdiction_matches("EU", "Sweden (EU)")
        assert jurisdiction_matches("European Union", "Sweden (EU-wide directive)")


class TestPlainCountries:
    def test_exact_match(self):
        assert jurisdiction_matches("Sweden", "Sweden")

    def test_word_in_annotated_value(self):
        assert jurisdiction_matches("Sweden", "Sweden (EU)")
        assert jurisdiction_matches("Finland", "Finland (EU-wide regulation)")

    def test_case_insensitive(self):
        assert jurisdiction_matches("germany", "Germany")

    def test_non_match(self):
        assert not jurisdiction_matches("Germany", "Sweden")

    def test_empty_query_matches_everything(self):
        assert jurisdiction_matches("", "US")
        assert jurisdiction_matches("   ", "Sweden")
