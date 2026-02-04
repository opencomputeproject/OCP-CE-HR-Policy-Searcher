"""Unit tests for keyword matching with stricter requirements."""

import pytest

from src.analysis.keywords import (
    COMPOUND_LANGUAGES,
    KeywordMatcher,
    KeywordMatch,
    KeywordMatchResult,
    StricterCheckResult,
)


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


# =============================================================================
# STRICTER REQUIREMENTS TESTS (Phase 2)
# =============================================================================


class TestStricterConfig:
    """Fixture for stricter requirements testing."""

    @pytest.fixture
    def stricter_config(self):
        """Configuration with all stricter requirements enabled."""
        return {
            "keywords": {
                "subject": {
                    "weight": 3.0,
                    "terms": {
                        "en": ["waste heat", "heat recovery", "heat reuse"],
                    },
                },
                "context": {
                    "weight": 1.0,
                    "terms": {
                        "en": ["data center", "data centre", "server farm"],
                    },
                },
                "policy_type": {
                    "weight": 2.0,
                    "terms": {
                        "en": ["regulation", "law", "directive", "policy"],
                    },
                },
                "incentives": {
                    "weight": 2.0,
                    "terms": {
                        "en": ["grant", "subsidy", "tax credit"],
                    },
                },
            },
            "thresholds": {
                "minimum_keyword_score": 5.0,
                "minimum_matches": 2,
            },
            "exclusions": ["cookie policy"],
            "stricter_requirements": {
                "required_combinations": {
                    "enabled": True,
                    "min_matches_per_category": 1,
                    "combinations": [
                        {"primary": "context", "secondary": "subject"},
                        {"primary": "context", "secondary": "policy_type"},
                        {"primary": "subject", "secondary": "policy_type"},
                        {"primary": "subject", "secondary": "incentives"},
                    ],
                },
                "density": {
                    "enabled": True,
                    "min_density": 1.0,
                    "categories_to_count": ["subject", "policy_type"],
                },
                "boost_keywords": {
                    "enabled": True,
                    "boost_amount": 3.0,
                    "terms": [
                        "data center heat reuse",
                        "waste heat recovery from data",
                    ],
                },
                "penalty_keywords": {
                    "enabled": True,
                    "penalty_amount": 2.0,
                    "terms": [
                        "privacy policy",
                        "terms of service",
                    ],
                },
            },
        }


class TestBoostKeywords(TestStricterConfig):
    """Tests for boost keyword functionality."""

    def test_boost_increases_score(self, stricter_config):
        """Boost keyword adds to score."""
        matcher = KeywordMatcher(stricter_config)
        result = matcher.match(
            "Our data center heat reuse program recovers waste heat."
        )

        assert result.boost_applied == 3.0
        assert "data center heat reuse" in result.boost_keywords_found
        assert result.final_score > result.score

    def test_multiple_boost_keywords(self, stricter_config):
        """Multiple boost keywords stack."""
        matcher = KeywordMatcher(stricter_config)
        result = matcher.match(
            "Data center heat reuse: waste heat recovery from data centers."
        )

        assert result.boost_applied == 6.0  # 3.0 * 2
        assert len(result.boost_keywords_found) == 2

    def test_boost_disabled(self):
        """No boost applied when disabled."""
        config = {
            "keywords": {"subject": {"weight": 1.0, "terms": {"en": ["heat"]}}},
            "stricter_requirements": {"boost_keywords": {"enabled": False}},
        }
        matcher = KeywordMatcher(config)
        result = matcher.match("Data center heat reuse program.")

        assert result.boost_applied == 0.0


class TestPenaltyKeywords(TestStricterConfig):
    """Tests for penalty keyword functionality."""

    def test_penalty_decreases_score(self, stricter_config):
        """Penalty keyword subtracts from score."""
        matcher = KeywordMatcher(stricter_config)
        result = matcher.match(
            "Data center waste heat information. Terms of service apply."
        )

        assert result.penalty_applied == 2.0
        assert "terms of service" in result.penalty_keywords_found
        assert result.final_score < result.score

    def test_final_score_minimum_zero(self, stricter_config):
        """Final score cannot go below zero."""
        matcher = KeywordMatcher(stricter_config)
        result = matcher.match("Terms of service. Privacy policy.")

        assert result.final_score == 0.0


class TestRequiredCombinations(TestStricterConfig):
    """Tests for required keyword combination checking."""

    def test_combination_context_subject_satisfied(self, stricter_config):
        """Page satisfies context + subject combination."""
        matcher = KeywordMatcher(stricter_config)
        result = matcher.match(
            "The data center waste heat recovery system is efficient."
        )

        check = matcher.check_stricter_requirements(result, len("x" * 100))
        assert check.passed is True

    def test_combination_not_satisfied(self, stricter_config):
        """Page does not satisfy any required combination."""
        matcher = KeywordMatcher(stricter_config)
        result = matcher.match("The data center is located in downtown.")

        check = matcher.check_stricter_requirements(result, len("x" * 100))
        assert check.passed is False
        assert "combination" in check.reason.lower()

    def test_subject_policy_combination(self, stricter_config):
        """Subject + policy_type combination."""
        matcher = KeywordMatcher(stricter_config)
        result = matcher.match("Waste heat regulation requires heat recovery systems.")

        check = matcher.check_stricter_requirements(result, len("x" * 100))
        assert check.passed is True

    def test_subject_incentives_combination(self, stricter_config):
        """Subject + incentives combination."""
        matcher = KeywordMatcher(stricter_config)
        result = matcher.match("Apply for a grant to implement waste heat systems.")

        check = matcher.check_stricter_requirements(result, len("x" * 100))
        assert check.passed is True


class TestKeywordDensity(TestStricterConfig):
    """Tests for keyword density requirements."""

    def test_density_satisfied(self, stricter_config):
        """Content with sufficient keyword density passes."""
        # Disable combinations to isolate density check
        stricter_config["stricter_requirements"]["required_combinations"]["enabled"] = False
        matcher = KeywordMatcher(stricter_config)

        # High density: many keywords in short text
        text = "Waste heat regulation. Heat recovery law. Policy directive. " * 5
        result = matcher.match(text)
        check = matcher.check_stricter_requirements(result, len(text))

        assert check.passed is True

    def test_density_not_satisfied(self, stricter_config):
        """Content with insufficient keyword density fails."""
        stricter_config["stricter_requirements"]["required_combinations"]["enabled"] = False
        matcher = KeywordMatcher(stricter_config)

        # Very long text with few keywords
        text = "x " * 5000 + "waste heat regulation" + " x" * 5000
        result = matcher.match(text)
        check = matcher.check_stricter_requirements(result, len(text))

        assert check.passed is False
        assert "density" in check.reason.lower()


class TestCategoryRequirements:
    """Tests for category requirement checks."""

    @pytest.fixture
    def category_config(self):
        return {
            "keywords": {
                "subject": {"weight": 3.0, "terms": {"en": ["waste heat"]}},
                "context": {"weight": 1.0, "terms": {"en": ["data center"]}},
                "policy_type": {"weight": 2.0, "terms": {"en": ["regulation"]}},
            },
            "stricter_requirements": {
                "category_requirements": {
                    "enabled": True,
                    "require_all": ["subject", "context"],
                    "require_any": [],
                },
            },
        }

    def test_require_all_satisfied(self, category_config):
        """All required categories present."""
        matcher = KeywordMatcher(category_config)
        result = matcher.match("Data center waste heat systems.")

        check = matcher.check_stricter_requirements(result, 1000)
        assert check.passed is True

    def test_require_all_not_satisfied(self, category_config):
        """Missing required category."""
        matcher = KeywordMatcher(category_config)
        result = matcher.match("Data center operations.")

        check = matcher.check_stricter_requirements(result, 1000)
        assert check.passed is False
        assert "subject" in check.reason


class TestIsRelevantStricter(TestStricterConfig):
    """Tests for is_relevant with stricter requirements."""

    def test_relevant_content_passes_all_checks(self, stricter_config):
        """Content that passes all checks is relevant."""
        matcher = KeywordMatcher(stricter_config)
        text = (
            "This data center waste heat recovery regulation requires "
            "all facilities to implement heat reuse systems. "
        ) * 10

        result = matcher.match(text)
        assert matcher.is_relevant(result, len(text)) is True

    def test_passes_score_fails_combination(self, stricter_config):
        """High score but no valid combination is not relevant."""
        matcher = KeywordMatcher(stricter_config)
        # Only subject keywords, no context/policy/incentives
        text = "Waste heat recovery. Heat reuse systems. " * 20

        result = matcher.match(text)
        assert result.final_score >= 5.0
        assert matcher.is_relevant(result, len(text)) is False


class TestKeywordMatchResultNew:
    """Tests for new KeywordMatchResult features."""

    def test_categories_matched(self):
        """categories_matched returns unique categories."""
        result = KeywordMatchResult(
            matches=[
                KeywordMatch("heat", "subject", 3.0, 1, "..."),
                KeywordMatch("data center", "context", 1.0, 1, "..."),
                KeywordMatch("waste heat", "subject", 3.0, 1, "..."),
            ],
            score=7.0,
            unique_matches=3,
        )

        assert result.categories_matched == {"subject", "context"}

    def test_category_match_count(self):
        """category_match_count returns correct count."""
        result = KeywordMatchResult(
            matches=[
                KeywordMatch("heat", "subject", 3.0, 1, "..."),
                KeywordMatch("waste heat", "subject", 3.0, 1, "..."),
                KeywordMatch("data center", "context", 1.0, 1, "..."),
            ],
            score=7.0,
            unique_matches=3,
        )

        assert result.category_match_count("subject") == 2
        assert result.category_match_count("context") == 1
        assert result.category_match_count("nonexistent") == 0

    def test_final_score_with_boost_penalty(self):
        """final_score correctly applies boost and penalty."""
        result = KeywordMatchResult(
            matches=[],
            score=10.0,
            unique_matches=3,
            boost_applied=5.0,
            penalty_applied=3.0,
        )

        assert result.final_score == 12.0  # 10 + 5 - 3


class TestGetFilterStats(TestStricterConfig):
    """Tests for get_filter_stats method."""

    def test_stats_contains_all_fields(self, stricter_config):
        """Stats dict contains all expected fields."""
        matcher = KeywordMatcher(stricter_config)
        text = "Data center waste heat regulation with data center heat reuse."

        result = matcher.match(text)
        stats = matcher.get_filter_stats(result, len(text))

        assert "passed" in stats
        assert "base_score" in stats
        assert "boost_applied" in stats
        assert "penalty_applied" in stats
        assert "final_score" in stats
        assert "categories_matched" in stats
        assert "density" in stats
        assert "stricter_passed" in stats


class TestEdgeCasesStricter:
    """Tests for edge cases with stricter requirements."""

    def test_empty_stricter_config(self):
        """Empty stricter_requirements config still works."""
        config = {
            "keywords": {"subject": {"weight": 1.0, "terms": {"en": ["heat"]}}},
            "stricter_requirements": {},
        }
        matcher = KeywordMatcher(config)
        result = matcher.match("Heat systems.")

        check = matcher.check_stricter_requirements(result, 100)
        assert check.passed is True

    def test_zero_content_length(self):
        """Zero content length doesn't cause division error."""
        config = {
            "keywords": {"subject": {"weight": 1.0, "terms": {"en": ["heat"]}}},
            "stricter_requirements": {
                "density": {"enabled": True, "min_density": 1.0}
            },
        }
        matcher = KeywordMatcher(config)
        result = matcher.match("Heat")

        check = matcher.check_stricter_requirements(result, 0)
        assert check is not None  # Should not raise error


# =============================================================================
# COMPOUND-WORD LANGUAGE TESTS
# =============================================================================


class TestCompoundLanguagesConstant:
    """Tests for the COMPOUND_LANGUAGES constant."""

    def test_compound_languages_includes_expected(self):
        """COMPOUND_LANGUAGES should contain de, nl, sv, da."""
        assert "de" in COMPOUND_LANGUAGES
        assert "nl" in COMPOUND_LANGUAGES
        assert "sv" in COMPOUND_LANGUAGES
        assert "da" in COMPOUND_LANGUAGES

    def test_compound_languages_excludes_non_compound(self):
        """COMPOUND_LANGUAGES should not contain en, fr, it, es."""
        assert "en" not in COMPOUND_LANGUAGES
        assert "fr" not in COMPOUND_LANGUAGES
        assert "it" not in COMPOUND_LANGUAGES
        assert "es" not in COMPOUND_LANGUAGES


class TestCompoundWordMatching:
    """Tests for compound-word language matching (German, Dutch, Swedish, Danish)."""

    @pytest.fixture
    def compound_config(self):
        """Config with compound-word language keywords."""
        return {
            "keywords": {
                "subject": {
                    "weight": 3.0,
                    "terms": {
                        "en": ["waste heat", "heat recovery"],
                        "de": ["Abwärme", "Wärmerückgewinnung"],
                        "nl": ["restwarmte", "warmteterugwinning"],
                        "sv": ["spillvärme", "värmeåtervinning"],
                        "da": ["overskudsvarme", "spildvarme"],
                    },
                },
                "context": {
                    "weight": 1.0,
                    "terms": {
                        "en": ["data center"],
                        "de": ["Rechenzentrum", "Rechenzentren"],
                        "nl": ["datacentrum"],
                        "sv": ["datacenter"],
                        "da": ["datacenter"],
                    },
                },
                "policy_type": {
                    "weight": 2.0,
                    "terms": {
                        "en": ["regulation", "law"],
                        "de": ["Verordnung", "Gesetz", "Pflicht"],
                        "nl": ["verordening", "wet"],
                        "sv": ["förordning", "lag"],
                        "da": ["forordning", "lov"],
                    },
                },
            },
            "thresholds": {
                "minimum_keyword_score": 5.0,
                "minimum_matches": 2,
            },
            "exclusions": [],
        }

    # --- German compound word tests ---

    def test_german_keyword_in_compound_word(self, compound_config):
        """German 'Abwärme' should match inside 'Rechenzentrumsabwärme'."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match("Die Rechenzentrumsabwärme kann genutzt werden.")

        assert result.has_matches
        assert any(m.keyword == "Abwärme" for m in result.matches)

    def test_german_keyword_standalone(self, compound_config):
        """German 'Abwärme' should still match as a standalone word."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match("Die Abwärme aus dem Betrieb ist nutzbar.")

        assert result.has_matches
        assert any(m.keyword == "Abwärme" for m in result.matches)

    def test_german_rechenzentrum_in_compound(self, compound_config):
        """'Rechenzentrum' should match inside 'Rechenzentrumsabwärme'."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match("Die Rechenzentrumsabwärme wird genutzt.")

        assert any(m.keyword == "Rechenzentrum" for m in result.matches)

    def test_german_verordnung_in_compound(self, compound_config):
        """'Verordnung' should match inside 'Energieverordnung'."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match("Die Energieverordnung regelt die Abwärmenutzung.")

        assert any(m.keyword == "Verordnung" for m in result.matches)

    def test_german_pflicht_in_compound(self, compound_config):
        """'Pflicht' should match inside 'Abwärmenutzungspflicht'."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match("Die Abwärmenutzungspflicht gilt ab 2025.")

        assert any(m.keyword == "Pflicht" for m in result.matches)

    def test_german_multiple_compounds_in_sentence(self, compound_config):
        """Multiple German compound words should all match."""
        matcher = KeywordMatcher(compound_config)
        text = "Die Rechenzentrumsabwärme unterliegt der Energieverordnung."
        result = matcher.match(text)

        keywords_found = {m.keyword for m in result.matches}
        assert "Abwärme" in keywords_found
        assert "Rechenzentrum" in keywords_found
        assert "Verordnung" in keywords_found

    # --- Dutch compound word test ---

    def test_dutch_keyword_in_compound(self, compound_config):
        """Dutch 'restwarmte' should match inside 'restwarmtebenutting'."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match("De restwarmtebenutting van datacentra.")

        assert any(m.keyword == "restwarmte" for m in result.matches)

    # --- Swedish compound word test ---

    def test_swedish_keyword_in_compound(self, compound_config):
        """Swedish 'spillvärme' should match inside 'spillvärmeanvändning'."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match("Spillvärmeanvändning från datacenter ökar.")

        assert any(m.keyword == "spillvärme" for m in result.matches)

    # --- Danish compound word test ---

    def test_danish_keyword_in_compound(self, compound_config):
        """Danish 'overskudsvarme' should match inside 'overskudsvarmeudnyttelse'."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match("Overskudsvarmeudnyttelse er vigtig.")

        assert any(m.keyword == "overskudsvarme" for m in result.matches)

    # --- English word boundaries preserved ---

    def test_english_word_boundaries_preserved(self, compound_config):
        """English keywords should still use word boundaries."""
        matcher = KeywordMatcher(compound_config)
        # "regulations" should NOT match "regulation" with \b
        result = matcher.match("These are general heating systems.")

        assert not any(m.keyword == "heat recovery" for m in result.matches)

    def test_english_exact_word_still_matches(self, compound_config):
        """English keywords with word boundaries still match exact words."""
        matcher = KeywordMatcher(compound_config)
        result = matcher.match(
            "The new regulation on waste heat from data centers."
        )

        assert any(m.keyword == "regulation" for m in result.matches)
        assert any(m.keyword == "waste heat" for m in result.matches)


class TestCompoundWordIntegration:
    """Integration test with actual config for German compound words."""

    def test_german_policy_text_with_actual_config(self):
        """German policy text with compound words should match using real config."""
        from src.config.loader import load_settings

        _, _, keywords_config = load_settings()
        matcher = KeywordMatcher(keywords_config)

        german_text = """
        Energieeffizienzgesetz (EnEfG)

        Dieses Gesetz regelt die Anforderungen an Betreiber von Rechenzentren
        hinsichtlich der Abwärmenutzung. Rechenzentren mit einer Leistung von
        über 500 kW müssen ihre Rechenzentrumsabwärme für Fernwärmenetze
        verfügbar machen, soweit dies wirtschaftlich zumutbar ist.

        Die Abwärmenutzungspflicht tritt ab 2025 in Kraft. Eine Wärmeplanung
        ist für alle neuen Rechenzentren verpflichtend.
        """

        result = matcher.match(german_text)

        assert result.has_matches
        assert result.score > 5.0
        assert result.unique_matches >= 3

        keywords_found = {m.keyword for m in result.matches}
        assert "Abwärme" in keywords_found or "Abwärmenutzung" in keywords_found
        assert "Rechenzentrum" in keywords_found or "Rechenzentren" in keywords_found


# =============================================================================
# GET_FAILURE_REASON TESTS
# =============================================================================


class TestGetFailureReason(TestStricterConfig):
    """Tests for get_failure_reason method."""

    def test_get_failure_reason_below_score(self, stricter_config):
        """Should return score reason when score is below threshold."""
        matcher = KeywordMatcher(stricter_config)
        # Single low-weight keyword = below min score of 5.0
        result = KeywordMatchResult(
            matches=[KeywordMatch("data center", "context", 1.0, 1, "...")],
            score=1.0,
            unique_matches=1,
        )

        reason = matcher.get_failure_reason(result, 1000)
        assert "Below min score" in reason
        assert "5.0" in reason

    def test_get_failure_reason_below_matches(self, stricter_config):
        """Should return matches reason when unique matches below threshold."""
        matcher = KeywordMatcher(stricter_config)
        # High score but only 1 unique match (threshold is 2)
        result = KeywordMatchResult(
            matches=[KeywordMatch("waste heat", "subject", 3.0, 5, "...")],
            score=15.0,
            unique_matches=1,
        )

        reason = matcher.get_failure_reason(result, 1000)
        assert "Below min matches" in reason
        assert "2" in reason

    def test_get_failure_reason_no_combination(self, stricter_config):
        """Should return combination reason when no required combo satisfied."""
        matcher = KeywordMatcher(stricter_config)
        # Two subject keywords but no context/policy_type/incentives
        result = KeywordMatchResult(
            matches=[
                KeywordMatch("waste heat", "subject", 3.0, 1, "..."),
                KeywordMatch("heat recovery", "subject", 3.0, 1, "..."),
            ],
            score=6.0,
            unique_matches=2,
        )

        reason = matcher.get_failure_reason(result, 1000)
        assert "combination" in reason.lower()

    def test_get_failure_reason_passes(self, stricter_config):
        """Should return empty string when content passes all checks."""
        matcher = KeywordMatcher(stricter_config)
        text = (
            "This data center waste heat recovery regulation requires "
            "all facilities to implement heat reuse systems. "
        ) * 10

        result = matcher.match(text)
        reason = matcher.get_failure_reason(result, len(text))
        assert reason == ""


class TestURLBonus:
    """Test URL-based scoring bonuses."""

    @pytest.fixture
    def matcher(self):
        """Matcher with basic config for URL bonus tests."""
        return KeywordMatcher({
            "keywords": {
                "subject": {
                    "weight": 2.0,
                    "terms": {"en": ["waste heat", "heat reuse"]},
                },
                "context": {
                    "weight": 1.0,
                    "terms": {"en": ["data center", "energy"]},
                },
            },
            "thresholds": {
                "minimum_keyword_score": 5.0,
                "minimum_matches": 2,
            },
        })

    def test_gov_tld_bonus(self, matcher):
        """URLs on .gov domains get a bonus."""
        bonus = matcher.url_bonus("https://lis.virginia.gov/bill-details/123")
        assert bonus >= 1.0

    def test_gov_uk_tld_bonus(self, matcher):
        """URLs on .gov.uk domains get a bonus."""
        bonus = matcher.url_bonus("https://www.legislation.gov.uk/acts/2023")
        assert bonus >= 1.0

    def test_bill_path_bonus(self, matcher):
        """URLs with bill-related paths get a bonus."""
        bonus = matcher.url_bonus("https://example.com/bills/HB323")
        assert bonus >= 1.5

    def test_legislation_path_bonus(self, matcher):
        """URLs with /legislation/ path get a bonus."""
        bonus = matcher.url_bonus("https://example.com/legislation/2026")
        assert bonus >= 1.5

    def test_bill_number_bonus(self, matcher):
        """URLs with bill numbers (HB323, SB192) get a bonus."""
        bonus = matcher.url_bonus("https://example.com/detail?bill=HB323")
        assert bonus >= 1.0

    def test_sb_bill_number_bonus(self, matcher):
        """Senate bill numbers also get a bonus."""
        bonus = matcher.url_bonus("https://example.com/detail?val=SB192")
        assert bonus >= 1.0

    def test_no_bonus_for_generic_url(self, matcher):
        """Generic URLs without .gov or bill patterns get no bonus."""
        bonus = matcher.url_bonus("https://example.com/about")
        assert bonus == 0.0

    def test_combined_bonuses_stack(self, matcher):
        """All three bonuses stack: .gov + bill path + bill number."""
        bonus = matcher.url_bonus("https://lis.virginia.gov/bill-details/20261/HB323")
        assert bonus >= 3.0  # .gov (1.0) + /bill-/ (1.5) + HB323 (1.0) = 3.5

    def test_virginia_cgi_path_bonus(self, matcher):
        """Virginia CGI script paths get bill path bonus."""
        bonus = matcher.url_bonus("https://lis.virginia.gov/cgi-bin/legp604.exe?val=hb116")
        assert bonus >= 2.5  # .gov (1.0) + legp*.exe (1.5)

    def test_url_bonus_applied_in_is_relevant(self, matcher):
        """URL bonus is included in is_relevant() score check."""
        # Text with a score around 4.0 (below threshold of 5.0)
        text = "This data center uses waste heat for energy efficiency."
        result = matcher.match(text)
        # Without URL bonus: should fail
        assert not matcher.is_relevant(result, len(text))
        # With .gov + bill path bonus: should pass
        assert matcher.is_relevant(
            result, len(text),
            url="https://lis.virginia.gov/bill-details/20261/HB323",
        )

    def test_url_bonus_in_failure_reason(self, matcher):
        """Failure reason includes url_bonus when URL is provided."""
        text = "minimal content"
        result = matcher.match(text)
        reason = matcher.get_failure_reason(
            result, len(text),
            url="https://lis.virginia.gov/page",
        )
        assert "url_bonus=+1.0" in reason

    def test_url_bonus_in_filter_stats(self, matcher):
        """get_filter_stats includes url_bonus and effective_score."""
        text = "waste heat data center"
        result = matcher.match(text)
        stats = matcher.get_filter_stats(result, len(text),
                                         url="https://example.gov/bills/123")
        assert "url_bonus" in stats
        assert stats["url_bonus"] >= 2.5  # .gov + /bills/
        assert "effective_score" in stats
        assert stats["effective_score"] == stats["final_score"] + stats["url_bonus"]

    def test_empty_url_no_bonus(self, matcher):
        """Empty URL string gives no bonus."""
        assert matcher.url_bonus("") == 0.0

    def test_is_relevant_no_url_backward_compatible(self, matcher):
        """is_relevant without url param still works (backward compat)."""
        text = (
            "This data center uses waste heat recovery and heat reuse "
            "for energy efficiency regulation requirements."
        ) * 3
        result = matcher.match(text)
        # Should work without url parameter
        relevant = matcher.is_relevant(result, len(text))
        assert isinstance(relevant, bool)
