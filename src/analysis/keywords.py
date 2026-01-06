"""Keyword matching."""

from dataclasses import dataclass
import re


@dataclass
class KeywordMatch:
    keyword: str
    category: str
    weight: float
    count: int
    context: str


@dataclass
class KeywordMatchResult:
    matches: list[KeywordMatch]
    score: float
    unique_matches: int

    @property
    def has_matches(self) -> bool:
        return len(self.matches) > 0


class KeywordMatcher:
    def __init__(self, keywords_config: dict):
        self.keywords = keywords_config.get("keywords", {})
        self.thresholds = keywords_config.get("thresholds", {})
        self.exclusions = keywords_config.get("exclusions", [])
        self._patterns: dict[str, re.Pattern] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        for category, config in self.keywords.items():
            terms = config.get("terms", {})
            for lang, keyword_list in terms.items():
                for keyword in keyword_list:
                    pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
                    self._patterns[f"{category}:{lang}:{keyword}"] = pattern

    @property
    def total_keywords(self) -> int:
        return len(self._patterns)

    def match(self, text: str) -> KeywordMatchResult:
        text_lower = text.lower()

        # Check exclusions
        for exclusion in self.exclusions:
            if exclusion.lower() in text_lower:
                return KeywordMatchResult([], 0.0, 0)

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

                matches.append(KeywordMatch(
                    keyword=keyword,
                    category=category,
                    weight=weight,
                    count=len(found),
                    context=context,
                ))

        score = sum(m.weight * m.count for m in matches)
        unique = len(set(m.keyword for m in matches))

        return KeywordMatchResult(matches, score, unique)

    def is_relevant(self, result: KeywordMatchResult) -> bool:
        min_score = self.thresholds.get("minimum_keyword_score", 5.0)
        min_matches = self.thresholds.get("minimum_matches", 2)
        return result.score >= min_score and result.unique_matches >= min_matches
