"""Human-readable run logging."""

from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json


class LogSection(Enum):
    CONFIG = "CONFIGURATION"
    CRAWL = "CRAWLING"
    ANALYSIS = "ANALYSIS"
    OUTPUT = "OUTPUT"
    SUMMARY = "SUMMARY"


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

    def end_run(self, stats: RunStats) -> None:
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
            "├" + "─" * 68 + "┤",
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

        # Save JSON log
        self._log_json("run_completed", **{
            **stats.__dict__,
            "success_rate": stats.success_rate,
            "estimated_cost_usd": stats.estimated_cost_usd,
        })
        json_file = self.log_dir / f"{self.run_id}.json"
        with open(json_file, "w") as f:
            json.dump(self._json_events, f, indent=2)
