"""Unit tests for keyword matching."""

import pytest

from src.analysis.keywords import KeywordMatcher, KeywordMatch, KeywordMatchResult


class TestKeywordMatcher:
    """Tests for KeywordMatcher class."""

    @pytest.fixture
    def simple_config(self):
        """Simple keyword config for testing."""
        return {
            "keywords": {
                "subject": {
                    "weight": 3.0,
                    "terms": {
                        "en": ["waste heat", "heat reuse", "heat recovery"],
                        "de": ["Abwärme"],
                    }
                },
                "policy_type": {
                    "weight": 2.0,
                    "terms": {
                        "en": ["regulation", "law", "directive"],
                    }
                },
            },
            "thresholds": {
                "minimum_keyword_score": 5.0,
                "minimum_matches": 2,
            },
            "exclusions": ["job posting", "newsletter signup"],
        }

    def test_init_compiles_patterns(self, simple_config):
        """Should compile regex patterns from config."""
        matcher = KeywordMatcher(simple_config)

        # 3 English subject + 1 German subject + 3 policy_type = 7
        assert matcher.total_keywords == 7

    def test_match_single_keyword(self, simple_config):
        """Should match a single keyword."""
        matcher = KeywordMatcher(simple_config)
        text = "This policy focuses on waste heat from data centers."

        result = matcher.match(text)

        assert result.has_matches
        assert len(result.matches) == 1
        assert result.matches[0].keyword == "waste heat"
        assert result.matches[0].category == "subject"
        assert result.matches[0].weight == 3.0

    def test_match_multiple_keywords(self, simple_config):
        """Should match multiple keywords and calculate score."""
        matcher = KeywordMatcher(simple_config)
        text = "New regulation on waste heat recovery from data centers."

        result = matcher.match(text)

        assert result.has_matches
        assert result.unique_matches >= 2
        # waste heat (3.0) + heat recovery (3.0) + regulation (2.0) = 8.0
        assert result.score >= 5.0

    def test_match_counts_occurrences(self, simple_config):
        """Should count multiple occurrences of same keyword."""
        matcher = KeywordMatcher(simple_config)
        text = "Waste heat here and waste heat there, waste heat everywhere."

        result = matcher.match(text)

        waste_heat_match = next(m for m in result.matches if m.keyword == "waste heat")
        assert waste_heat_match.count == 3
        # 3 occurrences * 3.0 weight = 9.0
        assert result.score == 9.0

    def test_match_case_insensitive(self, simple_config):
        """Should match regardless of case."""
        matcher = KeywordMatcher(simple_config)
        text = "WASTE HEAT is important. Waste Heat is valuable."

        result = matcher.match(text)

        assert result.has_matches
        waste_heat_match = next(m for m in result.matches if m.keyword == "waste heat")
        assert waste_heat_match.count == 2

    def test_match_german_terms(self, simple_config):
        """Should match non-English terms."""
        matcher = KeywordMatcher(simple_config)
        text = "Die Abwärme aus Rechenzentren kann genutzt werden."

        result = matcher.match(text)

        assert result.has_matches
        assert any(m.keyword == "Abwärme" for m in result.matches)

    def test_no_match_returns_empty(self, simple_config):
        """Should return empty result when no matches."""
        matcher = KeywordMatcher(simple_config)
        text = "This text has nothing relevant to data center energy."

        result = matcher.match(text)

        assert not result.has_matches
        assert result.matches == []
        assert result.score == 0.0
        assert result.unique_matches == 0

    def test_exclusion_returns_empty(self, simple_config):
        """Should return empty result when exclusion term found."""
        matcher = KeywordMatcher(simple_config)
        text = "Job posting: Engineer for waste heat recovery project."

        result = matcher.match(text)

        assert not result.has_matches
        assert result.score == 0.0

    def test_match_provides_context(self, simple_config):
        """Should provide context around matched keyword."""
        matcher = KeywordMatcher(simple_config)
        text = "Some prefix text about waste heat and some suffix text."

        result = matcher.match(text)

        assert result.matches[0].context
        assert "waste heat" in result.matches[0].context.lower()


class TestKeywordMatchResult:
    """Tests for KeywordMatchResult dataclass."""

    def test_has_matches_true(self):
        """has_matches should be True when matches exist."""
        result = KeywordMatchResult(
            matches=[KeywordMatch("test", "cat", 1.0, 1, "ctx")],
            score=1.0,
            unique_matches=1,
        )
        assert result.has_matches is True

    def test_has_matches_false(self):
        """has_matches should be False when no matches."""
        result = KeywordMatchResult(matches=[], score=0.0, unique_matches=0)
        assert result.has_matches is False


class TestIsRelevant:
    """Tests for is_relevant method."""

    @pytest.fixture
    def matcher(self):
        return KeywordMatcher({
            "keywords": {
                "subject": {"weight": 3.0, "terms": {"en": ["keyword1", "keyword2", "keyword3"]}},
            },
            "thresholds": {
                "minimum_keyword_score": 5.0,
                "minimum_matches": 2,
            },
        })

    def test_relevant_when_above_thresholds(self, matcher):
        """Should be relevant when score and matches above thresholds."""
        # keyword1 (3) + keyword2 (3) = 6.0 score, 2 unique matches
        text = "keyword1 and keyword2 are present"
        result = matcher.match(text)

        assert matcher.is_relevant(result) is True

    def test_not_relevant_low_score(self, matcher):
        """Should not be relevant when score below threshold."""
        # Only 1 keyword = 3.0 score, below 5.0 threshold
        text = "only keyword1 here"
        result = matcher.match(text)

        assert matcher.is_relevant(result) is False

    def test_not_relevant_few_matches(self, matcher):
        """Should not be relevant when unique matches below threshold."""
        # Same keyword 3 times = 9.0 score but only 1 unique match
        text = "keyword1 keyword1 keyword1"
        result = matcher.match(text)

        assert result.score == 9.0
        assert result.unique_matches == 1
        assert matcher.is_relevant(result) is False


class TestIntegrationWithActualConfig:
    """Integration tests using actual keywords.yaml."""

    def test_load_actual_keywords(self):
        """Should load and use actual keyword configuration."""
        from src.config.loader import load_settings

        _, _, keywords_config = load_settings()
        matcher = KeywordMatcher(keywords_config)

        # Should have many keywords loaded
        assert matcher.total_keywords > 100  # We have 400+ keywords

    def test_match_real_policy_text(self):
        """Should match text that looks like a real policy."""
        from src.config.loader import load_settings

        _, _, keywords_config = load_settings()
        matcher = KeywordMatcher(keywords_config)

        policy_text = """
        Energy Efficiency Directive (2023/1791)

        This regulation establishes requirements for data center operators
        regarding waste heat recovery and reuse. Data centers with capacity
        above 500 kW must report their energy consumption and make waste heat
        available to district heating networks where economically viable.

        Key requirements include annual energy efficiency reporting and
        heat recovery planning for new facilities.
        """

        result = matcher.match(policy_text)

        assert result.has_matches
        assert result.score > 5.0  # Should score well above threshold
        assert result.unique_matches >= 2
