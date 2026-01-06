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
    llm_calls: int = 0
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0
    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.pages_crawled == 0:
            return 0.0
        return (self.pages_success / self.pages_crawled) * 100

    @property
    def estimated_cost_usd(self) -> float:
        # Claude Sonnet pricing (approximate): $3/1M input, $15/1M output
        input_cost = (self.llm_tokens_input / 1_000_000) * 3.0
        output_cost = (self.llm_tokens_output / 1_000_000) * 15.0
        return input_cost + output_cost


class RunLogger:
    def __init__(self, run_id: str, log_dir: str = "logs"):
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.start_time = datetime.now(timezone.utc)
        self._log_file = self.log_dir / f"{run_id}.log"
        self._json_events: list[dict] = []

    def _write(self, msg: str) -> None:
        print(msg)
        with open(self._log_file, "a") as f:
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

        # Add LLM stats if used
        if stats.llm_calls > 0:
            summary_lines.extend([
                f"│  LLM API calls:      {stats.llm_calls:<44} │",
                f"│  Tokens (in/out):    {stats.llm_tokens_input:,} / {stats.llm_tokens_output:,}{' ' * (44 - len(f'{stats.llm_tokens_input:,} / {stats.llm_tokens_output:,}'))}│",
                f"│  Estimated cost:     ${stats.estimated_cost_usd:.4f}{' ' * (44 - len(f'${stats.estimated_cost_usd:.4f}'))}│",
                "├" + "─" * 68 + "┤",
            ])

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
