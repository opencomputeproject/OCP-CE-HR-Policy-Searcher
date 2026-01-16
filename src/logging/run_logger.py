"""Human-readable run logging."""

from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json
from typing import Optional


class LogSection(Enum):
    CONFIG = "CONFIGURATION"
    CRAWL = "CRAWLING"
    ANALYSIS = "ANALYSIS"
    OUTPUT = "OUTPUT"
    SUMMARY = "SUMMARY"


@dataclass
class RunConfig:
    """Captured run configuration for verbose summary."""
    # Domain selection
    domain_group: str = "all"
    category_filter: Optional[str] = None
    tag_filters: Optional[list] = None
    policy_type_filters: Optional[list] = None
    domains_count: int = 0

    # Keyword settings
    min_keyword_score: float = 5.0
    min_keyword_matches: int = 2
    required_combinations_enabled: bool = True
    min_density: float = 1.0
    density_enabled: bool = True
    boost_keywords_enabled: bool = True
    penalty_keywords_enabled: bool = True

    # LLM settings
    enable_llm: bool = True
    enable_two_stage: bool = True
    screening_model: str = ""
    analysis_model: str = ""
    screening_min_confidence: int = 5
    min_relevance_score: int = 5

    # Cache settings
    cache_enabled: bool = True
    cache_cleared: bool = False

    # Other options
    dry_run: bool = False
    chunking: Optional[str] = None

    def format_verbose(self) -> list[str]:
        """Format as lines for verbose summary."""
        lines = []
        lines.append("│" + " RUN CONFIGURATION ".center(68) + "│")
        lines.append("├" + "─" * 68 + "┤")

        # Domain selection
        lines.append(f"│  Domain group:       {self.domain_group:<44} │")
        lines.append(f"│  Domains selected:   {self.domains_count:<44} │")
        if self.category_filter:
            lines.append(f"│  Category filter:    {self.category_filter:<44} │")
        if self.tag_filters:
            tags = ", ".join(self.tag_filters[:3])
            if len(self.tag_filters) > 3:
                tags += "..."
            lines.append(f"│  Tag filters:        {tags:<44} │")
        if self.policy_type_filters:
            types = ", ".join(self.policy_type_filters[:3])
            lines.append(f"│  Policy types:       {types:<44} │")

        lines.append("├" + "─" * 68 + "┤")

        # Keyword settings
        lines.append(f"│  min_keyword_score:  {self.min_keyword_score:<44} │")
        lines.append(f"│  min_keyword_matches:{self.min_keyword_matches:<44} │")
        combo_str = "enabled" if self.required_combinations_enabled else "DISABLED"
        lines.append(f"│  require_combinations:{combo_str:<43} │")
        density_str = f"{self.min_density} (enabled)" if self.density_enabled else "disabled"
        lines.append(f"│  min_density:        {density_str:<44} │")
        boost_str = "enabled" if self.boost_keywords_enabled else "disabled"
        penalty_str = "enabled" if self.penalty_keywords_enabled else "disabled"
        lines.append(f"│  boost/penalty:      {boost_str} / {penalty_str}{' ' * (44 - len(f'{boost_str} / {penalty_str}'))}│")

        lines.append("├" + "─" * 68 + "┤")

        # LLM settings
        if self.enable_llm:
            if self.enable_two_stage:
                lines.append(f"│  LLM mode:           two-stage (Haiku → Sonnet){' ' * 20}│")
                lines.append(f"│  Screening model:    {self.screening_model:<44} │")
                lines.append(f"│  screening_min_conf: {self.screening_min_confidence:<44} │")
            else:
                lines.append(f"│  LLM mode:           single-stage{' ' * 33}│")
            lines.append(f"│  Analysis model:     {self.analysis_model:<44} │")
            lines.append(f"│  min_relevance_score:{self.min_relevance_score:<44} │")
        else:
            lines.append(f"│  LLM:                disabled (keyword-only){' ' * 22}│")

        lines.append("├" + "─" * 68 + "┤")

        # Cache & other settings
        cache_str = "enabled" if self.cache_enabled else "disabled"
        if self.cache_cleared:
            cache_str += " (cleared)"
        lines.append(f"│  Cache:              {cache_str:<44} │")
        lines.append(f"│  Dry run:            {str(self.dry_run).lower():<44} │")
        if self.chunking:
            lines.append(f"│  Chunking:           {self.chunking:<44} │")

        return lines


@dataclass
class RunStats:
    pages_crawled: int = 0
    pages_success: int = 0
    pages_blocked: int = 0
    pages_error: int = 0
    policies_found: int = 0
    policies_new: int = 0
    policies_duplicate: int = 0
    domains_scanned: int = 0
    keywords_matched: int = 0

    # Full analysis (Sonnet) stats
    llm_calls: int = 0
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0

    # Screening (Haiku) stats
    screening_calls: int = 0
    screening_tokens_input: int = 0
    screening_tokens_output: int = 0

    # Filter stats
    urls_filtered: int = 0
    keywords_passed: int = 0
    cache_hits: int = 0
    cache_skipped: int = 0

    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.pages_crawled == 0:
            return 0.0
        return (self.pages_success / self.pages_crawled) * 100

    @property
    def screening_cost_usd(self) -> float:
        """Cost for Haiku screening (~$0.25/MTok input, ~$1.25/MTok output)."""
        input_cost = (self.screening_tokens_input / 1_000_000) * 0.25
        output_cost = (self.screening_tokens_output / 1_000_000) * 1.25
        return input_cost + output_cost

    @property
    def analysis_cost_usd(self) -> float:
        """Cost for Sonnet analysis (~$3/MTok input, ~$15/MTok output)."""
        input_cost = (self.llm_tokens_input / 1_000_000) * 3.0
        output_cost = (self.llm_tokens_output / 1_000_000) * 15.0
        return input_cost + output_cost

    @property
    def estimated_cost_usd(self) -> float:
        """Total estimated cost (screening + analysis)."""
        return self.screening_cost_usd + self.analysis_cost_usd


class RunLogger:
    def __init__(self, run_id: str, log_dir: str = "logs"):
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.start_time = datetime.now(timezone.utc)
        self._log_file = self.log_dir / f"{run_id}.log"
        self._json_events: list[dict] = []

    def _write(self, msg: str) -> None:
        # Handle Windows console encoding issues
        try:
            print(msg)
        except UnicodeEncodeError:
            # Replace unencodable characters with '?' for console display
            print(msg.encode('ascii', errors='replace').decode('ascii'))

        # Always write UTF-8 to log file
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    def _log_json(self, event: str, **kwargs) -> None:
        self._json_events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event, **kwargs
        })

    def start_run(self) -> None:
        banner = f"""
{'='*70}
  OCP HEAT REUSE POLICY SEARCHER
  Run: {self.run_id}
  Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}
{'='*70}"""
        self._write(banner)
        self._log_json("run_started")

    def section(self, section: LogSection) -> None:
        self._write(f"\n{'-'*70}\n  {section.value}\n{'-'*70}")
        self._log_json("section", name=section.value)

    def info(self, msg: str, **kwargs) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._write(f"  [{ts}] {msg}")
        self._log_json("info", message=msg, **kwargs)

    def success(self, msg: str, **kwargs) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._write(f"  [{ts}] [OK] {msg}")
        self._log_json("success", message=msg, **kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._write(f"  [{ts}] [WARN] {msg}")
        self._log_json("warning", message=msg, **kwargs)

    def error(self, msg: str, **kwargs) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._write(f"  [{ts}] [ERROR] {msg}")
        self._log_json("error", message=msg, **kwargs)

    def end_run(
        self,
        stats: RunStats,
        run_config: Optional[RunConfig] = None,
        save_config: Optional[RunConfig] = None,
    ) -> None:
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        stats.duration_seconds = duration
        mins, secs = int(duration // 60), int(duration % 60)

        # Build summary box
        summary_lines = [
            "",
            "┌" + "─" * 68 + "┐",
            "│" + " RUN SUMMARY ".center(68) + "│",
            "├" + "─" * 68 + "┤",
            f"│  Domains scanned:    {stats.domains_scanned:<44} │",
            f"│  Pages crawled:      {stats.pages_crawled:<44} │",
            f"│  Pages successful:   {stats.pages_success:<44} │",
            f"│  Pages blocked:      {stats.pages_blocked:<44} │",
            f"│  Pages with errors:  {stats.pages_error:<44} │",
            f"│  Success rate:       {stats.success_rate:.1f}%{' ' * 42}│",
            "├" + "─" * 68 + "┤",
            f"│  Keywords matched:   {stats.keywords_matched:<44} │",
            f"│  Policies found:     {stats.policies_found:<44} │",
            f"│  New policies:       {stats.policies_new:<44} │",
            f"│  Duplicates skipped: {stats.policies_duplicate:<44} │",
        ]

        # Add filtering stats if any filtering occurred
        if stats.urls_filtered > 0 or stats.keywords_passed > 0 or stats.cache_hits > 0:
            summary_lines.append("├" + "─" * 68 + "┤")
            if stats.urls_filtered > 0:
                summary_lines.append(f"│  URLs pre-filtered:  {stats.urls_filtered:<44} │")
            if stats.keywords_passed > 0:
                summary_lines.append(f"│  Keywords passed:    {stats.keywords_passed:<44} │")
            if stats.cache_hits > 0:
                cache_str = f"{stats.cache_hits} hits, {stats.cache_skipped} skipped"
                summary_lines.append(f"│  Cache:              {cache_str:<44} │")

        # Add LLM stats if used - show screening and analysis separately
        if stats.screening_calls > 0 or stats.llm_calls > 0:
            summary_lines.append("├" + "─" * 68 + "┤")

            if stats.screening_calls > 0:
                screening_tokens = f"{stats.screening_tokens_input:,} in / {stats.screening_tokens_output:,} out"
                summary_lines.append(f"│  Screening (Haiku):  {stats.screening_calls} calls, {screening_tokens}{' ' * max(0, 44 - len(f'{stats.screening_calls} calls, {screening_tokens}'))}│")
                summary_lines.append(f"│    Cost:             ${stats.screening_cost_usd:.4f}{' ' * (44 - len(f'${stats.screening_cost_usd:.4f}'))}│")

            if stats.llm_calls > 0:
                analysis_tokens = f"{stats.llm_tokens_input:,} in / {stats.llm_tokens_output:,} out"
                summary_lines.append(f"│  Analysis (Sonnet):  {stats.llm_calls} calls, {analysis_tokens}{' ' * max(0, 44 - len(f'{stats.llm_calls} calls, {analysis_tokens}'))}│")
                summary_lines.append(f"│    Cost:             ${stats.analysis_cost_usd:.4f}{' ' * (44 - len(f'${stats.analysis_cost_usd:.4f}'))}│")

            summary_lines.append(f"│  TOTAL COST:         ${stats.estimated_cost_usd:.4f}{' ' * (44 - len(f'${stats.estimated_cost_usd:.4f}'))}│")

        summary_lines.extend([
            f"│  Duration:           {mins}m {secs}s{' ' * (44 - len(f'{mins}m {secs}s'))}│",
            f"│  Status:             COMPLETED{' ' * 35}│",
            "└" + "─" * 68 + "┘",
            "",
        ])

        self._write("\n".join(summary_lines))

        # Output verbose configuration after summary if requested
        if run_config:
            config_lines = [
                "",
                "┌" + "─" * 68 + "┐",
            ]
            config_lines.extend(run_config.format_verbose())
            config_lines.append("└" + "─" * 68 + "┘")
            config_lines.append("")
            self._write("\n".join(config_lines))

        # Save JSON log
        run_completed_data = {
            **stats.__dict__,
            "success_rate": stats.success_rate,
            "estimated_cost_usd": stats.estimated_cost_usd,
        }
        # Include run config if available (use save_config for JSON, run_config for display)
        config_to_save = save_config or run_config
        if config_to_save:
            run_completed_data["config"] = {
                "domain_group": config_to_save.domain_group,
                "category_filter": config_to_save.category_filter,
                "tag_filters": config_to_save.tag_filters,
                "policy_type_filters": config_to_save.policy_type_filters,
                "domains_count": config_to_save.domains_count,
                "min_keyword_score": config_to_save.min_keyword_score,
                "min_keyword_matches": config_to_save.min_keyword_matches,
                "required_combinations_enabled": config_to_save.required_combinations_enabled,
                "min_density": config_to_save.min_density,
                "density_enabled": config_to_save.density_enabled,
                "boost_keywords_enabled": config_to_save.boost_keywords_enabled,
                "penalty_keywords_enabled": config_to_save.penalty_keywords_enabled,
                "enable_llm": config_to_save.enable_llm,
                "enable_two_stage": config_to_save.enable_two_stage,
                "screening_model": config_to_save.screening_model,
                "analysis_model": config_to_save.analysis_model,
                "screening_min_confidence": config_to_save.screening_min_confidence,
                "min_relevance_score": config_to_save.min_relevance_score,
                "cache_enabled": config_to_save.cache_enabled,
                "cache_cleared": config_to_save.cache_cleared,
                "dry_run": config_to_save.dry_run,
                "chunking": config_to_save.chunking,
            }
        self._log_json("run_completed", **run_completed_data)
        json_file = self.log_dir / f"{self.run_id}.json"
        with open(json_file, "w") as f:
            json.dump(self._json_events, f, indent=2)


def get_last_run_log(log_dir: str = "logs") -> Optional[Path]:
    """Find the most recent run log file.

    Args:
        log_dir: Directory containing log files

    Returns:
        Path to most recent run_*.json file, or None if not found
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return None

    # Find all run_*.json files (exclude other JSON files like cost_history.json)
    run_files = list(log_path.glob("run_*.json"))
    if not run_files:
        return None

    # Sort by modification time, most recent first
    run_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return run_files[0]


def find_run_log(pattern: str, log_dir: str = "logs") -> Optional[Path]:
    """Find a run log file by pattern (partial match).

    Supports multiple input formats:
    - Full run ID: "run_20260115_143022"
    - Partial run ID: "20260115_143022" or "20260115"
    - Just date: "20260115" (returns most recent run from that date)
    - Recent index: "1", "2", "3" (1=most recent, 2=second most recent, etc.)

    Args:
        pattern: Pattern to match against run log filenames
        log_dir: Directory containing log files

    Returns:
        Path to matching run log file, or None if not found
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return None

    # Find all run_*.json files
    run_files = list(log_path.glob("run_*.json"))
    if not run_files:
        return None

    # Sort by modification time, most recent first
    run_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    # Check if pattern is a numeric index (1=most recent, 2=second, etc.)
    # Only treat as index if it's a small number (1-999), not date-like strings
    if pattern.isdigit() and len(pattern) <= 3:
        index = int(pattern) - 1  # Convert to 0-based
        if 0 <= index < len(run_files):
            return run_files[index]
        return None

    # Normalize pattern - remove .json extension if present
    pattern = pattern.replace(".json", "")

    # Try exact match first (with or without "run_" prefix)
    for log_file in run_files:
        stem = log_file.stem  # e.g., "run_20260115_143022"
        if stem == pattern or stem == f"run_{pattern}":
            return log_file

    # Try partial match (date-based or substring)
    for log_file in run_files:
        stem = log_file.stem
        # Match if pattern appears anywhere in the filename
        if pattern in stem:
            return log_file

    return None


def list_run_logs(log_dir: str = "logs", limit: int = 10) -> list[tuple[int, Path, dict]]:
    """List available run log files with basic info.

    Args:
        log_dir: Directory containing log files
        limit: Maximum number of logs to return (0 for all)

    Returns:
        List of (index, path, summary_dict) tuples, most recent first.
        Index is 1-based (1=most recent).
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return []

    # Find all run_*.json files
    run_files = list(log_path.glob("run_*.json"))
    if not run_files:
        return []

    # Sort by modification time, most recent first
    run_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    # Apply limit
    if limit > 0:
        run_files = run_files[:limit]

    results = []
    for idx, log_file in enumerate(run_files, start=1):
        # Load basic info from log
        run_data = load_run_log(log_file)
        summary = {}
        if run_data:
            summary = {
                "timestamp": run_data.get("timestamp", ""),
                "domains_scanned": run_data.get("domains_scanned", 0),
                "policies_found": run_data.get("policies_found", 0),
                "estimated_cost_usd": run_data.get("estimated_cost_usd", 0),
                "domain_group": run_data.get("config", {}).get("domain_group", ""),
            }
        results.append((idx, log_file, summary))

    return results


def load_run_log(log_file: Path) -> Optional[dict]:
    """Load a run log JSON file and extract the run_completed event.

    Args:
        log_file: Path to the run log JSON file

    Returns:
        Dictionary with run data, or None if not found
    """
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            events = json.load(f)

        # Find the run_completed event
        for event in reversed(events):  # Check from end, it's usually last
            if event.get("event") == "run_completed":
                return event

        return None
    except (json.JSONDecodeError, IOError, KeyError):
        return None


def format_last_run_summary(run_data: dict, run_id: str) -> str:
    """Format a run's data as a summary string.

    Args:
        run_data: Dictionary with run_completed event data
        run_id: The run ID (extracted from filename)

    Returns:
        Formatted summary string
    """
    lines = []

    # Header
    timestamp = run_data.get("timestamp", "")
    if timestamp:
        # Parse ISO timestamp and format nicely
        try:
            dt = datetime.fromisoformat(timestamp)
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, TypeError):
            formatted_time = timestamp[:19] if len(timestamp) > 19 else timestamp
    else:
        formatted_time = "Unknown"

    lines.append("")
    lines.append("┌" + "─" * 68 + "┐")
    lines.append("│" + " LAST RUN SUMMARY ".center(68) + "│")
    lines.append("├" + "─" * 68 + "┤")
    lines.append(f"│  Run ID:            {run_id:<44} │")
    lines.append(f"│  Completed:         {formatted_time:<44} │")
    lines.append("├" + "─" * 68 + "┤")

    # Stats
    domains = run_data.get("domains_scanned", 0)
    pages = run_data.get("pages_crawled", 0)
    success = run_data.get("pages_success", 0)
    blocked = run_data.get("pages_blocked", 0)
    errors = run_data.get("pages_error", 0)
    success_rate = run_data.get("success_rate", 0)

    lines.append(f"│  Domains scanned:    {domains:<44} │")
    lines.append(f"│  Pages crawled:      {pages:<44} │")
    lines.append(f"│  Pages successful:   {success:<44} │")
    lines.append(f"│  Pages blocked:      {blocked:<44} │")
    lines.append(f"│  Pages with errors:  {errors:<44} │")
    lines.append(f"│  Success rate:       {success_rate:.1f}%{' ' * 42}│")
    lines.append("├" + "─" * 68 + "┤")

    # Policies
    policies = run_data.get("policies_found", 0)
    new_policies = run_data.get("policies_new", 0)
    duplicates = run_data.get("policies_duplicate", 0)

    lines.append(f"│  Policies found:     {policies:<44} │")
    lines.append(f"│  New policies:       {new_policies:<44} │")
    lines.append(f"│  Duplicates skipped: {duplicates:<44} │")

    # LLM stats if available
    screening_calls = run_data.get("screening_calls", 0)
    llm_calls = run_data.get("llm_calls", 0)

    if screening_calls > 0 or llm_calls > 0:
        lines.append("├" + "─" * 68 + "┤")

        if screening_calls > 0:
            s_in = run_data.get("screening_tokens_input", 0)
            s_out = run_data.get("screening_tokens_output", 0)
            s_cost = (s_in / 1_000_000) * 0.25 + (s_out / 1_000_000) * 1.25
            screening_str = f"{screening_calls} calls, {s_in:,} in / {s_out:,} out"
            lines.append(f"│  Screening (Haiku):  {screening_str}{' ' * max(0, 44 - len(screening_str))}│")
            lines.append(f"│    Cost:             ${s_cost:.4f}{' ' * (44 - len(f'${s_cost:.4f}'))}│")

        if llm_calls > 0:
            a_in = run_data.get("llm_tokens_input", 0)
            a_out = run_data.get("llm_tokens_output", 0)
            a_cost = (a_in / 1_000_000) * 3.0 + (a_out / 1_000_000) * 15.0
            analysis_str = f"{llm_calls} calls, {a_in:,} in / {a_out:,} out"
            lines.append(f"│  Analysis (Sonnet):  {analysis_str}{' ' * max(0, 44 - len(analysis_str))}│")
            lines.append(f"│    Cost:             ${a_cost:.4f}{' ' * (44 - len(f'${a_cost:.4f}'))}│")

        total_cost = run_data.get("estimated_cost_usd", 0)
        lines.append(f"│  TOTAL COST:         ${total_cost:.4f}{' ' * (44 - len(f'${total_cost:.4f}'))}│")

    # Duration
    duration = run_data.get("duration_seconds", 0)
    mins, secs = int(duration // 60), int(duration % 60)
    lines.append("├" + "─" * 68 + "┤")
    lines.append(f"│  Duration:           {mins}m {secs}s{' ' * (44 - len(f'{mins}m {secs}s'))}│")
    lines.append("└" + "─" * 68 + "┘")

    return "\n".join(lines)


def format_last_run_config(config: dict) -> str:
    """Format a run's configuration as a verbose string.

    Args:
        config: Dictionary with configuration data

    Returns:
        Formatted configuration string
    """
    lines = []
    lines.append("")
    lines.append("┌" + "─" * 68 + "┐")
    lines.append("│" + " RUN CONFIGURATION ".center(68) + "│")
    lines.append("├" + "─" * 68 + "┤")

    # Domain selection
    domain_group = config.get("domain_group", "all")
    domains_count = config.get("domains_count", 0)
    lines.append(f"│  Domain group:       {domain_group:<44} │")
    lines.append(f"│  Domains selected:   {domains_count:<44} │")

    category = config.get("category_filter")
    if category:
        lines.append(f"│  Category filter:    {category:<44} │")

    tags = config.get("tag_filters")
    if tags:
        tags_str = ", ".join(tags[:3])
        if len(tags) > 3:
            tags_str += "..."
        lines.append(f"│  Tag filters:        {tags_str:<44} │")

    policy_types = config.get("policy_type_filters")
    if policy_types:
        types_str = ", ".join(policy_types[:3])
        lines.append(f"│  Policy types:       {types_str:<44} │")

    lines.append("├" + "─" * 68 + "┤")

    # Keyword settings
    min_score = config.get("min_keyword_score", 5.0)
    min_matches = config.get("min_keyword_matches", 2)
    req_combos = config.get("required_combinations_enabled", True)
    min_density = config.get("min_density", 1.0)
    density_enabled = config.get("density_enabled", True)
    boost_enabled = config.get("boost_keywords_enabled", True)
    penalty_enabled = config.get("penalty_keywords_enabled", True)

    lines.append(f"│  min_keyword_score:  {min_score:<44} │")
    lines.append(f"│  min_keyword_matches:{min_matches:<44} │")
    combo_str = "enabled" if req_combos else "DISABLED"
    lines.append(f"│  require_combinations:{combo_str:<43} │")
    density_str = f"{min_density} (enabled)" if density_enabled else "disabled"
    lines.append(f"│  min_density:        {density_str:<44} │")
    boost_str = "enabled" if boost_enabled else "disabled"
    penalty_str = "enabled" if penalty_enabled else "disabled"
    lines.append(f"│  boost/penalty:      {boost_str} / {penalty_str}{' ' * (44 - len(f'{boost_str} / {penalty_str}'))}│")

    lines.append("├" + "─" * 68 + "┤")

    # LLM settings
    enable_llm = config.get("enable_llm", True)
    enable_two_stage = config.get("enable_two_stage", True)
    screening_model = config.get("screening_model", "")
    analysis_model = config.get("analysis_model", "")
    screening_conf = config.get("screening_min_confidence", 5)
    min_relevance = config.get("min_relevance_score", 5)

    if enable_llm:
        if enable_two_stage:
            lines.append(f"│  LLM mode:           two-stage (Haiku -> Sonnet){' ' * 19}│")
            lines.append(f"│  Screening model:    {screening_model:<44} │")
            lines.append(f"│  screening_min_conf: {screening_conf:<44} │")
        else:
            lines.append(f"│  LLM mode:           single-stage{' ' * 33}│")
        lines.append(f"│  Analysis model:     {analysis_model:<44} │")
        lines.append(f"│  min_relevance_score:{min_relevance:<44} │")
    else:
        lines.append(f"│  LLM:                disabled (keyword-only){' ' * 22}│")

    lines.append("├" + "─" * 68 + "┤")

    # Cache & other settings
    cache_enabled = config.get("cache_enabled", True)
    cache_cleared = config.get("cache_cleared", False)
    dry_run = config.get("dry_run", False)
    chunking = config.get("chunking")

    cache_str = "enabled" if cache_enabled else "disabled"
    if cache_cleared:
        cache_str += " (cleared)"
    lines.append(f"│  Cache:              {cache_str:<44} │")
    lines.append(f"│  Dry run:            {str(dry_run).lower():<44} │")
    if chunking:
        lines.append(f"│  Chunking:           {chunking:<44} │")

    lines.append("└" + "─" * 68 + "┘")
    lines.append("")

    return "\n".join(lines)
