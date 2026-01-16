"""URL pre-filtering to skip obviously irrelevant pages before LLM analysis.

This module provides URL-based filtering to reduce API costs by skipping
pages that are unlikely to contain relevant policy content based on their URL.

Features:
- Path-based filtering (substring match)
- Pattern-based filtering (regex)
- File extension filtering
- Domain-specific overrides
- Statistics tracking for filter effectiveness

Usage:
    from src.analysis.url_filter import URLFilter, load_url_filters

    # Load filter config
    config = load_url_filters()
    url_filter = URLFilter(config)

    # Check if URL should be skipped
    if url_filter.should_skip(url):
        print(f"Skipping {url}")
    else:
        # Proceed with LLM analysis
        pass

    # Get filter statistics
    stats = url_filter.get_stats()
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yaml


@dataclass
class URLFilterConfig:
    """Configuration for URL filtering."""

    skip_paths: list[str] = field(default_factory=list)
    skip_patterns: list[str] = field(default_factory=list)
    skip_extensions: list[str] = field(default_factory=list)
    domain_overrides: dict[str, dict] = field(default_factory=dict)

    # Compiled regex patterns (populated lazily)
    _compiled_patterns: list[re.Pattern] = field(
        default_factory=list, repr=False, compare=False
    )

    def __post_init__(self):
        """Compile regex patterns after initialization."""
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile skip_patterns into regex objects."""
        self._compiled_patterns = []
        for pattern in self.skip_patterns:
            try:
                self._compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                # Log warning but don't fail - skip invalid patterns
                print(f"Warning: Invalid URL filter pattern '{pattern}': {e}")


@dataclass
class FilterResult:
    """Result of URL filtering with reason."""

    should_skip: bool
    reason: Optional[str] = None
    rule_type: Optional[str] = None  # "path", "pattern", "extension", "domain"
    matched_rule: Optional[str] = None


@dataclass
class FilterStats:
    """Statistics about filter effectiveness."""

    total_checked: int = 0
    total_skipped: int = 0
    by_path: int = 0
    by_pattern: int = 0
    by_extension: int = 0
    by_domain: int = 0

    @property
    def skip_rate(self) -> float:
        """Percentage of URLs skipped."""
        if self.total_checked == 0:
            return 0.0
        return (self.total_skipped / self.total_checked) * 100

    @property
    def passed(self) -> int:
        """Number of URLs that passed filtering."""
        return self.total_checked - self.total_skipped


class URLFilter:
    """URL filter to skip obviously irrelevant pages."""

    def __init__(self, config: Optional[URLFilterConfig] = None):
        """Initialize the URL filter.

        Args:
            config: URL filter configuration. If None, no filtering is applied.
        """
        self.config = config or URLFilterConfig()
        self.stats = FilterStats()

    def should_skip(self, url: str, domain: Optional[str] = None) -> bool:
        """Check if a URL should be skipped.

        Args:
            url: The URL to check
            domain: Optional domain override (if not provided, extracted from URL)

        Returns:
            True if the URL should be skipped, False otherwise
        """
        result = self.check_url(url, domain)
        return result.should_skip

    def check_url(self, url: str, domain: Optional[str] = None) -> FilterResult:
        """Check a URL and return detailed result.

        Args:
            url: The URL to check
            domain: Optional domain override (if not provided, extracted from URL)

        Returns:
            FilterResult with skip decision and reason
        """
        self.stats.total_checked += 1

        # Parse URL
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            # Full path with query string for pattern matching
            full_path = path
            if parsed.query:
                full_path = f"{path}?{parsed.query.lower()}"
            url_domain = domain or parsed.netloc.lower()

            # Remove www. prefix for matching
            if url_domain.startswith("www."):
                url_domain = url_domain[4:]
        except Exception:
            # If we can't parse, don't skip
            return FilterResult(should_skip=False)

        # Check file extension first (fastest check)
        result = self._check_extension(path)
        if result.should_skip:
            self.stats.total_skipped += 1
            self.stats.by_extension += 1
            return result

        # Check domain-specific rules
        result = self._check_domain_overrides(url_domain, path)
        if result.should_skip:
            self.stats.total_skipped += 1
            self.stats.by_domain += 1
            return result

        # Check global skip paths (substring match)
        result = self._check_paths(path)
        if result.should_skip:
            self.stats.total_skipped += 1
            self.stats.by_path += 1
            return result

        # Check regex patterns (slowest, do last)
        # Use full_path (with query string) for patterns to support ?page=N matching
        result = self._check_patterns(full_path)
        if result.should_skip:
            self.stats.total_skipped += 1
            self.stats.by_pattern += 1
            return result

        return FilterResult(should_skip=False)

    def _check_extension(self, path: str) -> FilterResult:
        """Check if path has a skipped file extension."""
        for ext in self.config.skip_extensions:
            ext_lower = ext.lower()
            if path.endswith(ext_lower):
                return FilterResult(
                    should_skip=True,
                    reason=f"Skipped extension: {ext}",
                    rule_type="extension",
                    matched_rule=ext,
                )
        return FilterResult(should_skip=False)

    def _check_paths(self, path: str) -> FilterResult:
        """Check if path matches any skip_paths (substring match)."""
        for skip_path in self.config.skip_paths:
            skip_lower = skip_path.lower()
            if skip_lower in path:
                return FilterResult(
                    should_skip=True,
                    reason=f"Matched skip path: {skip_path}",
                    rule_type="path",
                    matched_rule=skip_path,
                )
        return FilterResult(should_skip=False)

    def _check_patterns(self, path: str) -> FilterResult:
        """Check if path matches any skip_patterns (regex match)."""
        for i, pattern in enumerate(self.config._compiled_patterns):
            if pattern.search(path):
                original_pattern = self.config.skip_patterns[i]
                return FilterResult(
                    should_skip=True,
                    reason=f"Matched pattern: {original_pattern}",
                    rule_type="pattern",
                    matched_rule=original_pattern,
                )
        return FilterResult(should_skip=False)

    def _check_domain_overrides(self, domain: str, path: str) -> FilterResult:
        """Check domain-specific rules."""
        if domain not in self.config.domain_overrides:
            return FilterResult(should_skip=False)

        domain_config = self.config.domain_overrides[domain]
        domain_skip_paths = domain_config.get("skip_paths", [])

        for skip_path in domain_skip_paths:
            skip_lower = skip_path.lower()
            if skip_lower in path:
                return FilterResult(
                    should_skip=True,
                    reason=f"Domain override ({domain}): {skip_path}",
                    rule_type="domain",
                    matched_rule=f"{domain}:{skip_path}",
                )

        return FilterResult(should_skip=False)

    def get_stats(self) -> FilterStats:
        """Get current filter statistics."""
        return self.stats

    def reset_stats(self):
        """Reset statistics counters."""
        self.stats = FilterStats()

    def format_stats(self) -> str:
        """Format statistics as a human-readable string."""
        s = self.stats
        lines = [
            "URL Filter Statistics:",
            f"  Total checked:  {s.total_checked}",
            f"  Total skipped:  {s.total_skipped} ({s.skip_rate:.1f}%)",
            f"  Passed:         {s.passed}",
            "",
            "  Breakdown by rule type:",
            f"    By extension: {s.by_extension}",
            f"    By path:      {s.by_path}",
            f"    By pattern:   {s.by_pattern}",
            f"    By domain:    {s.by_domain}",
        ]
        return "\n".join(lines)


def load_url_filters(config_path: Optional[Path] = None) -> URLFilterConfig:
    """Load URL filter configuration from YAML file.

    Args:
        config_path: Path to config file. Defaults to config/url_filters.yaml

    Returns:
        URLFilterConfig object (empty config if file doesn't exist)
    """
    if config_path is None:
        config_path = Path("config/url_filters.yaml")

    if not config_path.exists():
        return URLFilterConfig()

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        filters = data.get("url_filters", {})

        return URLFilterConfig(
            skip_paths=filters.get("skip_paths", []),
            skip_patterns=filters.get("skip_patterns", []),
            skip_extensions=filters.get("skip_extensions", []),
            domain_overrides=filters.get("domain_overrides", {}),
        )
    except Exception as e:
        print(f"Warning: Failed to load URL filters from {config_path}: {e}")
        return URLFilterConfig()


def create_url_filter(config_path: Optional[Path] = None) -> URLFilter:
    """Create a URLFilter with configuration loaded from file.

    Convenience function combining load and instantiation.

    Args:
        config_path: Optional path to config file

    Returns:
        Configured URLFilter instance
    """
    config = load_url_filters(config_path)
    return URLFilter(config)
