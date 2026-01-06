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
    duration_seconds: float = 0.0


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

        summary = f"""
  Duration: {mins}m {secs}s
  Pages crawled: {stats.pages_crawled}
  Successful: {stats.pages_success}
  Blocked: {stats.pages_blocked}
  Errors: {stats.pages_error}
  Policies found: {stats.policies_found}

  Status: COMPLETED
{'='*70}"""
        self._write(summary)

        # Save JSON log
        self._log_json("run_completed", **stats.__dict__)
        json_file = self.log_dir / f"{self.run_id}.json"
        with open(json_file, "w") as f:
            json.dump(self._json_events, f, indent=2)
