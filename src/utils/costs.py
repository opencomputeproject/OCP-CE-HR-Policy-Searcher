"""Cost tracking and monitoring for Claude API usage."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Claude model pricing (USD per 1M tokens) - Updated January 2026
MODEL_PRICING = {
    # Sonnet models
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    # Haiku models (cheaper)
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # Opus models (more expensive)
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    # Default fallback
    "default": {"input": 3.00, "output": 15.00},
}


@dataclass
class CostBreakdown:
    """Detailed cost breakdown for a run."""
    model: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    api_calls: int

    @classmethod
    def calculate(
        cls,
        model: str,
        input_tokens: int,
        output_tokens: int,
        api_calls: int,
    ) -> "CostBreakdown":
        """Calculate cost breakdown for given token usage."""
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return cls(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=input_cost + output_cost,
            api_calls=api_calls,
        )

    def format_summary(self) -> str:
        """Format a human-readable summary."""
        lines = [
            f"Model: {self.model}",
            f"API Calls: {self.api_calls}",
            f"Input Tokens: {self.input_tokens:,} (${self.input_cost_usd:.4f})",
            f"Output Tokens: {self.output_tokens:,} (${self.output_cost_usd:.4f})",
            f"Total Cost: ${self.total_cost_usd:.4f}",
        ]
        return "\n".join(lines)


@dataclass
class RunCostRecord:
    """Record of costs for a single run."""
    run_id: str
    timestamp: str
    model: str
    input_tokens: int
    output_tokens: int
    total_cost_usd: float
    api_calls: int
    domains_scanned: int
    policies_found: int


@dataclass
class CostHistory:
    """Cumulative cost history across all runs."""
    runs: list[RunCostRecord] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_api_calls: int = 0

    def add_run(self, record: RunCostRecord) -> None:
        """Add a run to the history."""
        self.runs.append(record)
        self.total_input_tokens += record.input_tokens
        self.total_output_tokens += record.output_tokens
        self.total_cost_usd += record.total_cost_usd
        self.total_api_calls += record.api_calls

    def get_runs_since(self, days: int) -> list[RunCostRecord]:
        """Get runs from the last N days."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        return [
            r for r in self.runs
            if datetime.fromisoformat(r.timestamp.replace("Z", "+00:00")).timestamp() > cutoff
        ]

    def get_cost_since(self, days: int) -> float:
        """Get total cost from the last N days."""
        return sum(r.total_cost_usd for r in self.get_runs_since(days))

    def format_summary(self, last_n_runs: int = 10) -> str:
        """Format a summary of recent cost history."""
        lines = [
            "=" * 70,
            "  COST HISTORY SUMMARY",
            "=" * 70,
            "",
            f"  All-time totals:",
            f"    Total runs:         {len(self.runs)}",
            f"    Total API calls:    {self.total_api_calls:,}",
            f"    Total input tokens: {self.total_input_tokens:,}",
            f"    Total output tokens:{self.total_output_tokens:,}",
            f"    Total cost:         ${self.total_cost_usd:.2f}",
            "",
            f"  Recent costs:",
            f"    Last 7 days:        ${self.get_cost_since(7):.2f}",
            f"    Last 30 days:       ${self.get_cost_since(30):.2f}",
            "",
        ]

        if self.runs:
            lines.extend([
                f"  Last {min(last_n_runs, len(self.runs))} runs:",
                f"  {'Run ID':<30} {'Cost':>10} {'Policies':>10}",
                f"  {'-'*30} {'-'*10} {'-'*10}",
            ])

            for run in reversed(self.runs[-last_n_runs:]):
                run_id_short = run.run_id[:28] + ".." if len(run.run_id) > 30 else run.run_id
                lines.append(
                    f"  {run_id_short:<30} ${run.total_cost_usd:>8.4f} {run.policies_found:>10}"
                )

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)


class CostTracker:
    """Tracks and persists cost history across runs."""

    def __init__(self, history_file: str = "logs/cost_history.json"):
        self.history_file = Path(history_file)
        self.history = self._load_history()

    def _load_history(self) -> CostHistory:
        """Load cost history from file."""
        if not self.history_file.exists():
            return CostHistory()

        try:
            with open(self.history_file, "r") as f:
                data = json.load(f)

            runs = [RunCostRecord(**r) for r in data.get("runs", [])]
            return CostHistory(
                runs=runs,
                total_input_tokens=data.get("total_input_tokens", 0),
                total_output_tokens=data.get("total_output_tokens", 0),
                total_cost_usd=data.get("total_cost_usd", 0.0),
                total_api_calls=data.get("total_api_calls", 0),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return CostHistory()

    def _save_history(self) -> None:
        """Save cost history to file."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "runs": [asdict(r) for r in self.history.runs],
            "total_input_tokens": self.history.total_input_tokens,
            "total_output_tokens": self.history.total_output_tokens,
            "total_cost_usd": self.history.total_cost_usd,
            "total_api_calls": self.history.total_api_calls,
        }

        with open(self.history_file, "w") as f:
            json.dump(data, f, indent=2)

    def record_run(
        self,
        run_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        api_calls: int,
        domains_scanned: int,
        policies_found: int,
    ) -> CostBreakdown:
        """Record a completed run and return cost breakdown."""
        breakdown = CostBreakdown.calculate(model, input_tokens, output_tokens, api_calls)

        record = RunCostRecord(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_cost_usd=breakdown.total_cost_usd,
            api_calls=api_calls,
            domains_scanned=domains_scanned,
            policies_found=policies_found,
        )

        self.history.add_run(record)
        self._save_history()

        return breakdown

    def get_history(self) -> CostHistory:
        """Get the full cost history."""
        return self.history

    def check_budget_warning(
        self,
        monthly_budget: Optional[float] = None,
        warn_threshold: float = 0.8,
    ) -> Optional[str]:
        """
        Check if approaching budget limit.

        Returns warning message if cost exceeds threshold, None otherwise.
        """
        if monthly_budget is None:
            return None

        cost_30d = self.history.get_cost_since(30)
        usage_ratio = cost_30d / monthly_budget

        if usage_ratio >= 1.0:
            return f"BUDGET EXCEEDED: ${cost_30d:.2f} spent (budget: ${monthly_budget:.2f})"
        elif usage_ratio >= warn_threshold:
            pct = usage_ratio * 100
            return f"Budget warning: ${cost_30d:.2f} of ${monthly_budget:.2f} used ({pct:.0f}%)"

        return None


def estimate_run_cost(
    domains: int,
    pages_per_domain: int = 50,
    relevance_rate: float = 0.1,
    avg_tokens_per_page: int = 4000,
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """
    Estimate cost for a planned run.

    Args:
        domains: Number of domains to scan
        pages_per_domain: Average pages per domain
        relevance_rate: Fraction of pages that pass keyword filter
        avg_tokens_per_page: Average input tokens per analyzed page
        model: Model to use for analysis

    Returns:
        Dict with estimated costs and token usage
    """
    total_pages = domains * pages_per_domain
    analyzed_pages = int(total_pages * relevance_rate)

    input_tokens = analyzed_pages * avg_tokens_per_page
    # Assume ~500 output tokens per analysis (JSON response)
    output_tokens = analyzed_pages * 500

    breakdown = CostBreakdown.calculate(model, input_tokens, output_tokens, analyzed_pages)

    return {
        "domains": domains,
        "estimated_pages": total_pages,
        "estimated_analyzed": analyzed_pages,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cost_usd": breakdown.total_cost_usd,
        "model": model,
    }
