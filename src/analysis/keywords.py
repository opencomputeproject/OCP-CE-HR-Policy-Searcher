"""Keyword matching with stricter requirements for cost optimization.

This module provides keyword-based filtering to identify potentially relevant
policy content before sending to LLM analysis.

Features:
- Weighted keyword scoring by category
- Required category combinations (e.g., data center + heat terms)
- Keyword density requirements
- Boost keywords for high-value phrases
- Penalty keywords for generic content
- Statistics tracking

Usage:
    from src.analysis.keywords import KeywordMatcher

    matcher = KeywordMatcher(keywords_config)
    result = matcher.match(text)

    if matcher.is_relevant(result, len(text)):
        # Send to LLM for analysis
        pass
"""

from dataclasses import dataclass, field
import re
from typing import Optional
from urllib.parse import urlparse

# Languages that use compound words where keywords may appear as substrings
# of larger words. For these languages, patterns skip \b word boundaries so
# that e.g. "Abwärme" matches inside "Rechenzentrumsabwärme".
COMPOUND_LANGUAGES: set[str] = {"de", "nl", "sv", "da"}

# URL-based scoring bonuses
_GOV_TLD_BONUS = 1.0
_BILL_PATH_BONUS = 1.5
_BILL_NUMBER_BONUS = 1.0

# Patterns for URL bonus scoring
_BILL_PATH_PATTERNS = [
    r"/bill[s]?[-/]", r"/legislation/", r"/act[s]?/",
    r"/statute[s]?/", r"/measure[s]?/", r"/resolution[s]?/",
    r"/legp\d+\.exe",  # Virginia CGI
]
_BILL_NUMBER_PATTERN = re.compile(
    r"[/=](H\.?B\.?|S\.?B\.?|H\.?R\.?|S\.?R\.?|H\.?J\.?R\.?|S\.?J\.?R\.?)\s*\d+",
    re.IGNORECASE,
)


@dataclass
class KeywordMatch:
    """A single keyword match."""

    keyword: str
    category: str
    weight: float
    count: int
    context: str


@dataclass
class KeywordMatchResult:
    """Result of keyword matching."""

    matches: list[KeywordMatch]
    score: float
    unique_matches: int
    boost_applied: float = 0.0
    penalty_applied: float = 0.0
    boost_keywords_found: list[str] = field(default_factory=list)
    penalty_keywords_found: list[str] = field(default_factory=list)

    @property
    def has_matches(self) -> bool:
        return len(self.matches) > 0

    @property
    def final_score(self) -> float:
        """Score after boost and penalty adjustments."""
        return max(0.0, self.score + self.boost_applied - self.penalty_applied)

    @property
    def categories_matched(self) -> set[str]:
        """Set of categories that had matches."""
        return {m.category for m in self.matches}

    def matches_by_category(self) -> dict[str, list[KeywordMatch]]:
        """Group matches by category."""
        result: dict[str, list[KeywordMatch]] = {}
        for match in self.matches:
            if match.category not in result:
                result[match.category] = []
            result[match.category].append(match)
        return result

    def category_match_count(self, category: str) -> int:
        """Get number of unique matches in a category."""
        return len([m for m in self.matches if m.category == category])


@dataclass
class StricterCheckResult:
    """Result of stricter requirements checks."""

    passed: bool
    reason: str = ""
    combination_satisfied: Optional[str] = None
    density: float = 0.0
    density_required: float = 0.0


class KeywordMatcher:
    """Keyword matcher with configurable strictness levels."""

    def __init__(self, keywords_config: dict):
        """Initialize the keyword matcher.

        Args:
            keywords_config: Configuration dict with keywords, thresholds,
                            exclusions, and stricter_requirements.
        """
        self.keywords = keywords_config.get("keywords", {})
        self.thresholds = keywords_config.get("thresholds", {})
        self.exclusions = keywords_config.get("exclusions", [])
        self.stricter = keywords_config.get("stricter_requirements", {})

        self._patterns: dict[str, re.Pattern] = {}
        self._boost_patterns: list[tuple[str, re.Pattern]] = []
        self._penalty_patterns: list[tuple[str, re.Pattern]] = []

        self._compile_patterns()
        self._compile_boost_penalty_patterns()

    def _compile_patterns(self) -> None:
        """Compile keyword patterns for matching.

        For compound-word languages (German, Dutch, Swedish, Danish),
        patterns use substring matching so that keywords match inside
        compound words. Other languages use word boundaries (\\b).
        """
        for category, config in self.keywords.items():
            terms = config.get("terms", {})
            for lang, keyword_list in terms.items():
                for keyword in keyword_list:
                    if lang in COMPOUND_LANGUAGES:
                        pattern = re.compile(
                            re.escape(keyword), re.IGNORECASE
                        )
                    else:
                        pattern = re.compile(
                            r"\b" + re.escape(keyword) + r"\b",
                            re.IGNORECASE,
                        )
                    self._patterns[f"{category}:{lang}:{keyword}"] = pattern

    def _compile_boost_penalty_patterns(self) -> None:
        """Compile boost and penalty keyword patterns."""
        # Boost keywords
        boost_config = self.stricter.get("boost_keywords", {})
        if boost_config.get("enabled", False):
            for term in boost_config.get("terms", []):
                pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
                self._boost_patterns.append((term, pattern))

        # Penalty keywords
        penalty_config = self.stricter.get("penalty_keywords", {})
        if penalty_config.get("enabled", False):
            for term in penalty_config.get("terms", []):
                pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
                self._penalty_patterns.append((term, pattern))

    def url_bonus(self, url: str) -> float:
        """Calculate bonus score from URL patterns.

        Args:
            url: The page URL

        Returns:
            Bonus points to add to keyword score
        """
        bonus = 0.0
        parsed = urlparse(url)
        hostname = parsed.netloc.lower()
        path = parsed.path.lower()
        full = f"{path}?{parsed.query}" if parsed.query else path

        # .gov TLD bonus
        if hostname.endswith(".gov") or hostname.endswith(".gov.uk"):
            bonus += _GOV_TLD_BONUS

        # Bill/legislation path patterns
        for pattern in _BILL_PATH_PATTERNS:
            if re.search(pattern, full, re.IGNORECASE):
                bonus += _BILL_PATH_BONUS
                break  # Only count once

        # Bill number in URL (HB323, SB192, etc.)
        if _BILL_NUMBER_PATTERN.search(full):
            bonus += _BILL_NUMBER_BONUS

        return bonus

    @property
    def total_keywords(self) -> int:
        """Total number of keyword patterns."""
        return len(self._patterns)

    def match(self, text: str) -> KeywordMatchResult:
        """Match keywords in text and return results.

        Args:
            text: Text content to search

        Returns:
            KeywordMatchResult with matches, scores, and adjustments
        """
        text_lower = text.lower()

        # Check exclusions first
        for exclusion in self.exclusions:
            if exclusion.lower() in text_lower:
                return KeywordMatchResult([], 0.0, 0)

        # Find all keyword matches
        matches = []
        for key, pattern in self._patterns.items():
            category, lang, keyword = key.split(":", 2)
            weight = self.keywords[category].get("weight", 1.0)

            found = pattern.findall(text)
            if found:
                match_obj = pattern.search(text)
                start = max(0, match_obj.start() - 50)
                end = min(len(text), match_obj.end() + 50)
                context = f"...{text[start:end]}..."

                matches.append(
                    KeywordMatch(
                        keyword=keyword,
                        category=category,
                        weight=weight,
                        count=len(found),
                        context=context,
                    )
                )

        # Calculate base score
        score = sum(m.weight * m.count for m in matches)
        unique = len(set(m.keyword for m in matches))

        # Apply boost keywords
        boost_applied = 0.0
        boost_found = []
        boost_config = self.stricter.get("boost_keywords", {})
        if boost_config.get("enabled", False):
            boost_amount = boost_config.get("boost_amount", 3.0)
            for term, pattern in self._boost_patterns:
                if pattern.search(text):
                    boost_applied += boost_amount
                    boost_found.append(term)

        # Apply penalty keywords
        penalty_applied = 0.0
        penalty_found = []
        penalty_config = self.stricter.get("penalty_keywords", {})
        if penalty_config.get("enabled", False):
            penalty_amount = penalty_config.get("penalty_amount", 2.0)
            for term, pattern in self._penalty_patterns:
                if pattern.search(text):
                    penalty_applied += penalty_amount
                    penalty_found.append(term)

        return KeywordMatchResult(
            matches=matches,
            score=score,
            unique_matches=unique,
            boost_applied=boost_applied,
            penalty_applied=penalty_applied,
            boost_keywords_found=boost_found,
            penalty_keywords_found=penalty_found,
        )

    def check_stricter_requirements(
        self, result: KeywordMatchResult, content_length: int
    ) -> StricterCheckResult:
        """Check if result passes stricter requirements.

        Args:
            result: KeywordMatchResult from match()
            content_length: Length of the content in characters

        Returns:
            StricterCheckResult with pass/fail status and reason
        """
        # Check required combinations
        combo_config = self.stricter.get("required_combinations", {})
        if combo_config.get("enabled", False):
            combinations = combo_config.get("combinations", [])
            min_per_cat = combo_config.get("min_matches_per_category", 1)

            combination_satisfied = None
            for combo in combinations:
                primary = combo.get("primary", "")
                secondary = combo.get("secondary", "")

                primary_count = result.category_match_count(primary)
                secondary_count = result.category_match_count(secondary)

                if primary_count >= min_per_cat and secondary_count >= min_per_cat:
                    combination_satisfied = f"{primary}+{secondary}"
                    break

            if combination_satisfied is None:
                return StricterCheckResult(
                    passed=False,
                    reason="No required keyword combination satisfied",
                )

        # Check keyword density
        density_config = self.stricter.get("density", {})
        if density_config.get("enabled", False):
            min_density = density_config.get("min_density", 0.0)

            if min_density > 0 and content_length > 0:
                # Calculate density from specified categories
                categories_to_count = density_config.get("categories_to_count", [])

                if categories_to_count:
                    # Count matches from specified categories
                    match_count = sum(
                        m.count
                        for m in result.matches
                        if m.category in categories_to_count
                    )
                else:
                    # Count all matches
                    match_count = sum(m.count for m in result.matches)

                # Density = matches per 1000 characters
                density = (match_count / content_length) * 1000

                if density < min_density:
                    return StricterCheckResult(
                        passed=False,
                        reason=f"Keyword density {density:.2f} below minimum {min_density}",
                        density=density,
                        density_required=min_density,
                    )

        # Check category requirements
        cat_config = self.stricter.get("category_requirements", {})
        if cat_config.get("enabled", False):
            require_all = cat_config.get("require_all", [])
            require_any = cat_config.get("require_any", [])

            categories_matched = result.categories_matched

            if require_all:
                missing = [cat for cat in require_all if cat not in categories_matched]
                if missing:
                    return StricterCheckResult(
                        passed=False,
                        reason=f"Missing required categories: {', '.join(missing)}",
                    )

            if require_any:
                if not any(cat in categories_matched for cat in require_any):
                    return StricterCheckResult(
                        passed=False,
                        reason=f"Need at least one of: {', '.join(require_any)}",
                    )

        # All checks passed
        return StricterCheckResult(passed=True)

    def is_relevant(
        self, result: KeywordMatchResult, content_length: int = 0,
        url: str = "", min_score_override: Optional[float] = None,
    ) -> bool:
        """Check if a match result indicates relevant content.

        Args:
            result: KeywordMatchResult from match()
            content_length: Length of content for density calculation
            url: Page URL for URL-based bonus scoring
            min_score_override: Per-domain override for minimum keyword score

        Returns:
            True if content should be analyzed by LLM
        """
        # Check basic thresholds
        min_score = min_score_override if min_score_override is not None else self.thresholds.get("minimum_keyword_score", 5.0)
        min_matches = self.thresholds.get("minimum_matches", 2)

        # Apply URL bonus to final score
        effective_score = result.final_score
        if url:
            effective_score += self.url_bonus(url)

        if effective_score < min_score:
            return False

        if result.unique_matches < min_matches:
            return False

        # Check stricter requirements
        stricter_result = self.check_stricter_requirements(result, content_length)
        if not stricter_result.passed:
            return False

        return True

    def get_failure_reason(
        self, result: KeywordMatchResult, content_length: int = 0,
        url: str = "", min_score_override: Optional[float] = None,
    ) -> str:
        """Return the first reason a match result would fail is_relevant().

        Mirrors the check order in is_relevant() so the reason matches
        the actual gate that rejected the page.

        Args:
            result: KeywordMatchResult from match()
            content_length: Length of content for density calculation
            url: Page URL for URL-based bonus scoring
            min_score_override: Per-domain override for minimum keyword score

        Returns:
            Reason string (e.g. "Below min score (5.0)"), or "" if it passes
        """
        min_score = min_score_override if min_score_override is not None else self.thresholds.get("minimum_keyword_score", 5.0)
        min_matches = self.thresholds.get("minimum_matches", 2)

        effective_score = result.final_score
        if url:
            effective_score += self.url_bonus(url)

        if effective_score < min_score:
            url_bonus_str = f" (url_bonus=+{self.url_bonus(url):.1f})" if url else ""
            return f"Below min score ({min_score}){url_bonus_str}"

        if result.unique_matches < min_matches:
            return f"Below min matches ({min_matches})"

        stricter_result = self.check_stricter_requirements(result, content_length)
        if not stricter_result.passed:
            return stricter_result.reason

        return ""

    def get_filter_stats(
        self, result: KeywordMatchResult, content_length: int,
        url: str = "",
    ) -> dict:
        """Get detailed statistics about filtering decision.

        Useful for debugging and understanding why content was filtered.

        Args:
            result: KeywordMatchResult from match()
            content_length: Length of content
            url: Page URL for URL-based bonus scoring

        Returns:
            Dict with detailed filtering statistics
        """
        min_score = self.thresholds.get("minimum_keyword_score", 5.0)
        min_matches = self.thresholds.get("minimum_matches", 2)
        stricter_result = self.check_stricter_requirements(result, content_length)

        # Calculate density
        density_config = self.stricter.get("density", {})
        density = 0.0
        if content_length > 0:
            categories_to_count = density_config.get("categories_to_count", [])
            if categories_to_count:
                match_count = sum(
                    m.count
                    for m in result.matches
                    if m.category in categories_to_count
                )
            else:
                match_count = sum(m.count for m in result.matches)
            density = (match_count / content_length) * 1000

        url_bonus_val = self.url_bonus(url) if url else 0.0

        return {
            "passed": self.is_relevant(result, content_length, url=url),
            "base_score": result.score,
            "boost_applied": result.boost_applied,
            "penalty_applied": result.penalty_applied,
            "final_score": result.final_score,
            "url_bonus": url_bonus_val,
            "effective_score": result.final_score + url_bonus_val,
            "score_threshold": min_score,
            "unique_matches": result.unique_matches,
            "matches_threshold": min_matches,
            "categories_matched": list(result.categories_matched),
            "boost_keywords_found": result.boost_keywords_found,
            "penalty_keywords_found": result.penalty_keywords_found,
            "stricter_passed": stricter_result.passed,
            "stricter_reason": stricter_result.reason,
            "density": density,
            "density_required": density_config.get("min_density", 0.0),
            "content_length": content_length,
        }
