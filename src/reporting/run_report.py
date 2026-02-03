"""Run report generator.

Parses JSON event stream from run logs and generates a formatted
terminal report with per-domain breakdowns, pipeline funnel,
filter details, and actionable suggestions.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Box-drawing helpers ──────────────────────────────────────────────

BOX_W = 70  # outer width
INNER_W = 68  # content area width


def _box_top() -> str:
    return "\u250c" + "\u2500" * INNER_W + "\u2510"


def _box_bottom() -> str:
    return "\u2514" + "\u2500" * INNER_W + "\u2518"


def _box_sep() -> str:
    return "\u251c" + "\u2500" * INNER_W + "\u2524"


def _box_title(title: str) -> str:
    return "\u2502" + f" {title} ".center(INNER_W) + "\u2502"


def _box_line(text: str) -> str:
    """Left-align text inside box, pad to width."""
    content = f"  {text}"
    if len(content) > INNER_W:
        content = content[: INNER_W - 2] + ".."
    return "\u2502" + content.ljust(INNER_W) + "\u2502"


def _box_empty() -> str:
    return "\u2502" + " " * INNER_W + "\u2502"


# ── Data model ───────────────────────────────────────────────────────


@dataclass
class DomainStats:
    """Per-domain stats reconstructed from event stream."""

    domain_id: str
    pages_total: int = 0
    pages_ok: int = 0
    pages_blocked: int = 0
    pages_error: int = 0
    fetched_paths: list[str] = field(default_factory=list)
    fetch_times_ms: list[int] = field(default_factory=list)
    blocked_pages: list[tuple[str, str]] = field(default_factory=list)
    error_pages: list[tuple[str, str]] = field(default_factory=list)

    @property
    def avg_fetch_time(self) -> Optional[int]:
        if not self.fetch_times_ms:
            return None
        return sum(self.fetch_times_ms) // len(self.fetch_times_ms)

    @property
    def has_issues(self) -> bool:
        return self.pages_blocked > 0 or self.pages_error > 0


@dataclass
class FilterStats:
    """URL pre-filter and keyword stats from detail events."""

    urls_filtered: int = 0
    filter_reasons: dict[str, int] = field(default_factory=dict)
    keywords_checked: int = 0
    keywords_passed: int = 0
    keyword_thresholds: str = ""
    keyword_fail_reasons: dict[str, int] = field(default_factory=dict)
    near_misses: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    """Complete parsed run data for report generation."""

    run_id: str
    timestamp: str = ""
    duration_seconds: float = 0.0

    # Aggregates from run_completed
    domains_scanned: int = 0
    pages_crawled: int = 0
    pages_success: int = 0
    pages_blocked: int = 0
    pages_error: int = 0
    policies_found: int = 0
    policies_new: int = 0
    policies_duplicate: int = 0
    urls_filtered: int = 0
    keywords_passed: int = 0
    estimated_cost_usd: float = 0.0
    success_rate: float = 0.0

    # LLM stats
    screening_calls: int = 0
    llm_calls: int = 0

    # Config (from run_completed.config)
    config: dict = field(default_factory=dict)

    # Per-domain breakdown
    domains: list[DomainStats] = field(default_factory=list)

    # Filter detail
    filter_stats: FilterStats = field(default_factory=FilterStats)

    # Whether the run completed normally
    completed: bool = False

    @property
    def pages_after_filter(self) -> int:
        return self.pages_success - self.urls_filtered

    @property
    def domain_group(self) -> str:
        return self.config.get("domain_group", "unknown")


# ── Regex patterns for event parsing ─────────────────────────────────

_RE_STARTING = re.compile(r"^Starting: (.+)$")
_RE_COMPLETE = re.compile(r"^Complete: (\d+) pages?, (\d+) ok, (\d+) blocked$")
_RE_FETCHED = re.compile(r"^Fetched: (.+) \((\d+)ms\)$")
_RE_WARNING_STATUS = re.compile(
    r"^(access_denied|captcha|paywall|login_required|rate_limited): (.+?)(?:\s+\((.+)\))?$"
)
_RE_WARNING_ERROR = re.compile(r"^Error: (.+?) - (.+)")
_RE_URL_FILTER = re.compile(r"^URL pre-filter: skipped (\d+) URLs")
_RE_KEYWORDS = re.compile(r"^Keywords: (\d+)/(\d+) pages passed")
_RE_FILTER_REASON = re.compile(r"^(.+?)\s{2,}->\s+(.+)$")
_RE_KW_FAIL = re.compile(r"^\s\s(.+?)\s{2,}(\d+) pages?$")


# ── Parsing ──────────────────────────────────────────────────────────


def load_run_events(log_file: Path) -> list[dict]:
    """Load all events from a run log JSON file."""
    with open(log_file, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_run_events(events: list[dict], run_id: str) -> RunReport:
    """Parse a JSON event list into a RunReport."""
    report = RunReport(run_id=run_id)

    current_domain: Optional[DomainStats] = None
    in_filter_detail = False
    in_keyword_detail = False

    for event in events:
        etype = event.get("event", "")
        msg = event.get("message", "")

        if etype == "run_started":
            report.timestamp = event.get("timestamp", "")

        elif etype == "info":
            # Domain start
            m = _RE_STARTING.match(msg)
            if m:
                if current_domain:
                    report.domains.append(current_domain)
                current_domain = DomainStats(domain_id=m.group(1))
                in_filter_detail = False
                in_keyword_detail = False
                continue

            # Domain complete
            m = _RE_COMPLETE.match(msg)
            if m and current_domain:
                current_domain.pages_total = int(m.group(1))
                current_domain.pages_ok = int(m.group(2))
                current_domain.pages_blocked = int(m.group(3))
                current_domain.pages_error = (
                    current_domain.pages_total
                    - current_domain.pages_ok
                    - current_domain.pages_blocked
                )
                report.domains.append(current_domain)
                current_domain = None
                continue

            # URL pre-filter aggregate
            m = _RE_URL_FILTER.match(msg)
            if m:
                report.filter_stats.urls_filtered = int(m.group(1))
                if "(details)" in msg:
                    in_filter_detail = True
                    in_keyword_detail = False
                continue

            # Keyword aggregate
            m = _RE_KEYWORDS.match(msg)
            if m:
                report.filter_stats.keywords_passed = int(m.group(1))
                report.filter_stats.keywords_checked = int(m.group(2))
                if "(details)" in msg:
                    in_keyword_detail = True
                    in_filter_detail = False
                continue

        elif etype == "success" and current_domain:
            m = _RE_FETCHED.match(msg)
            if m:
                current_domain.fetched_paths.append(m.group(1))
                current_domain.fetch_times_ms.append(int(m.group(2)))

        elif etype == "warning" and current_domain:
            # Status-based warning (access_denied, captcha, etc.)
            m = _RE_WARNING_STATUS.match(msg)
            if m:
                status = m.group(1)
                path = m.group(2)
                reason = m.group(3) or ""
                label = f"{status}" + (f" ({reason})" if reason else "")
                current_domain.blocked_pages.append((path, label))
                continue

            # Error warning
            m = _RE_WARNING_ERROR.match(msg)
            if m:
                path = m.group(1)
                error = m.group(2).split("\n")[0]  # first line only
                current_domain.error_pages.append((path, error))

        elif etype == "detail":
            # Filter reason detail
            if in_filter_detail:
                m = _RE_FILTER_REASON.match(msg)
                if m:
                    reason = m.group(2).strip()
                    report.filter_stats.filter_reasons[reason] = (
                        report.filter_stats.filter_reasons.get(reason, 0) + 1
                    )
                    continue
                # Empty line or non-matching detail ends filter section
                if not msg.strip():
                    in_filter_detail = False

            # Keyword detail
            if in_keyword_detail:
                if msg.startswith("Thresholds:"):
                    report.filter_stats.keyword_thresholds = msg.strip()
                    continue
                m = _RE_KW_FAIL.match(msg)
                if m:
                    reason = m.group(1).strip()
                    count = int(m.group(2))
                    report.filter_stats.keyword_fail_reasons[reason] = count
                    continue
                if msg.startswith("Near misses"):
                    pass  # header line
                elif msg.strip() and "FAILED" not in msg:
                    report.filter_stats.near_misses.append(msg.strip())

        elif etype == "section":
            in_filter_detail = False
            in_keyword_detail = False

        elif etype == "run_completed":
            report.completed = True
            report.pages_crawled = event.get("pages_crawled", 0)
            report.pages_success = event.get("pages_success", 0)
            report.pages_blocked = event.get("pages_blocked", 0)
            report.pages_error = event.get("pages_error", 0)
            report.policies_found = event.get("policies_found", 0)
            report.policies_new = event.get("policies_new", 0)
            report.policies_duplicate = event.get("policies_duplicate", 0)
            report.domains_scanned = event.get("domains_scanned", 0)
            report.urls_filtered = event.get("urls_filtered", 0)
            report.keywords_passed = event.get("keywords_passed", 0)
            report.estimated_cost_usd = event.get("estimated_cost_usd", 0.0)
            report.success_rate = event.get("success_rate", 0.0)
            report.duration_seconds = event.get("duration_seconds", 0.0)
            report.screening_calls = event.get("screening_calls", 0)
            report.llm_calls = event.get("llm_calls", 0)
            report.config = event.get("config") or {}
            if not report.timestamp:
                report.timestamp = event.get("timestamp", "")

    # Push any remaining domain
    if current_domain:
        report.domains.append(current_domain)

    # If no run_completed event, compute from domains
    if not report.completed and report.domains:
        report.domains_scanned = len(report.domains)
        report.pages_crawled = sum(d.pages_total for d in report.domains)
        report.pages_success = sum(d.pages_ok for d in report.domains)
        report.pages_blocked = sum(d.pages_blocked for d in report.domains)
        report.pages_error = sum(d.pages_error for d in report.domains)
        if report.pages_crawled > 0:
            report.success_rate = (
                report.pages_success / report.pages_crawled
            ) * 100

    return report


# ── Formatting ───────────────────────────────────────────────────────


def _format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}m {secs}s"


def _format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display."""
    if not ts:
        return "unknown"
    # "2026-02-03T16:44:01.947509+00:00" -> "2026-02-03 16:44 UTC"
    try:
        date_part = ts[:10]
        time_part = ts[11:16]
        return f"{date_part} {time_part} UTC"
    except (IndexError, ValueError):
        return ts[:19]


def _format_cost(cost: float) -> str:
    """Format cost for display."""
    if cost == 0:
        return "$0.00"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _format_header(report: RunReport) -> list[str]:
    """Format the report header box."""
    group = report.domain_group
    if report.domains_scanned > 0:
        group += f" ({report.domains_scanned} domains)"

    lines = [
        "",
        _box_top(),
        _box_title("RUN REPORT"),
        _box_sep(),
        _box_line(f"Run ID:       {report.run_id}"),
        _box_line(f"Date:         {_format_timestamp(report.timestamp)}"),
        _box_line(f"Duration:     {_format_duration(report.duration_seconds)}"),
        _box_line(f"Group:        {group}"),
        _box_line(f"Cost:         {_format_cost(report.estimated_cost_usd)}"),
    ]
    if not report.completed:
        lines.append(_box_line("Status:       DID NOT COMPLETE"))
    lines.append(_box_bottom())
    return lines


def _format_result_summary(report: RunReport) -> list[str]:
    """Format the result headline box."""
    # Build headline
    p = report.policies_found
    kw = report.keywords_passed
    if p > 0:
        headline = f"RESULT: {p} {'policy' if p == 1 else 'policies'} found!"
    elif kw > 0:
        headline = f"RESULT: {kw} pages passed keywords, 0 policies extracted."
    else:
        headline = f"RESULT: 0 policies found. {kw} pages passed keyword filtering."

    lines = [
        "",
        _box_top(),
        _box_line(headline),
        _box_sep(),
        _box_line(
            f"{report.pages_crawled} pages crawled across "
            f"{report.domains_scanned} {'domain' if report.domains_scanned == 1 else 'domains'}"
        ),
        _box_line(
            f"{report.pages_success} succeeded, "
            f"{report.pages_blocked} blocked, "
            f"{report.pages_error} errors"
        ),
        _box_line(f"{report.success_rate:.1f}% success rate"),
    ]
    if report.policies_found > 0:
        lines.append(
            _box_line(
                f"Policies: {report.policies_new} new, "
                f"{report.policies_duplicate} duplicate"
            )
        )
    lines.append(_box_bottom())
    return lines


def _format_pipeline_funnel(report: RunReport) -> list[str]:
    """Format the pipeline funnel with visual bars."""
    stages = [
        ("Pages crawled", report.pages_crawled),
        ("Fetch succeeded", report.pages_success),
        ("After URL filter", max(report.pages_after_filter, 0)),
        ("Keywords passed", report.keywords_passed),
        ("Policies found", report.policies_found),
    ]

    max_val = max((v for _, v in stages), default=1) or 1
    max_bar = 35
    label_w = 18

    lines = ["", _box_top(), _box_title("PIPELINE FUNNEL"), _box_sep(), _box_empty()]

    for label, value in stages:
        bar_len = round(value / max_val * max_bar) if value > 0 else 0
        bar = "\u2588" * bar_len
        num_str = str(value).rjust(4)
        text = f"{label:<{label_w}} {num_str}  {bar}"
        lines.append(_box_line(text))

    lines.append(_box_empty())

    # Drop-off line
    drops = []
    prev = report.pages_crawled
    stage_names = ["crawl", "url-filter", "keywords"]
    stage_values = [report.pages_success, max(report.pages_after_filter, 0), report.keywords_passed]
    for name, val in zip(stage_names, stage_values):
        if prev > 0:
            pct = ((prev - val) / prev) * 100
            drops.append(f"{name} -{pct:.0f}%")
        prev = val
    if drops:
        lines.append(_box_line(f"Drop-off:  {'  '.join(drops)}"))
        lines.append(_box_empty())

    lines.append(_box_bottom())
    return lines


def _format_domain_breakdown(report: RunReport) -> list[str]:
    """Format per-domain breakdown."""
    if not report.domains:
        return []

    # Sort: domains with issues first, then by page count descending
    sorted_domains = sorted(
        report.domains,
        key=lambda d: (not d.has_issues, -d.pages_total),
    )

    lines = [
        "",
        _box_top(),
        _box_title("DOMAIN BREAKDOWN"),
        _box_sep(),
    ]

    for i, domain in enumerate(sorted_domains):
        if i > 0:
            lines.append(_box_sep())

        lines.append(_box_empty())

        # Domain header: name left, page count right
        page_label = f"{domain.pages_total} {'page' if domain.pages_total == 1 else 'pages'}"
        header = f"{domain.domain_id}"
        pad = INNER_W - 2 - len(header) - len(page_label)
        if pad < 1:
            pad = 1
        lines.append(_box_line(f"{header}{' ' * pad}{page_label}"))

        # Counts line
        lines.append(
            _box_line(
                f"  Success: {domain.pages_ok:<5}"
                f"Blocked: {domain.pages_blocked:<5}"
                f"Errors: {domain.pages_error}"
            )
        )

        # Blocked pages (up to 5)
        if domain.blocked_pages:
            max_show = 5
            for j, (path, reason) in enumerate(domain.blocked_pages[:max_show]):
                prefix = "  Blocked: " if j == 0 else "           "
                entry = f"{path} ({reason})"
                if len(prefix) + len(entry) > INNER_W - 2:
                    entry = entry[: INNER_W - 2 - len(prefix) - 2] + ".."
                lines.append(_box_line(f"{prefix}{entry}"))
            remaining = len(domain.blocked_pages) - max_show
            if remaining > 0:
                lines.append(_box_line(f"           ... and {remaining} more"))

        # Error pages (up to 5)
        if domain.error_pages:
            max_show = 5
            for j, (path, error) in enumerate(domain.error_pages[:max_show]):
                prefix = "  Errors:  " if j == 0 else "           "
                entry = f"{path} ({error})"
                if len(prefix) + len(entry) > INNER_W - 2:
                    entry = entry[: INNER_W - 2 - len(prefix) - 2] + ".."
                lines.append(_box_line(f"{prefix}{entry}"))
            remaining = len(domain.error_pages) - max_show
            if remaining > 0:
                lines.append(_box_line(f"           ... and {remaining} more"))

        # Average fetch time
        avg = domain.avg_fetch_time
        if avg is not None:
            lines.append(_box_line(f"  Avg fetch time: {avg}ms"))

        lines.append(_box_empty())

    lines.append(_box_bottom())
    return lines


def _format_filter_detail(report: RunReport) -> list[str]:
    """Format filter details (only shown if detail data exists)."""
    fs = report.filter_stats
    has_filter = fs.filter_reasons or fs.urls_filtered > 0
    has_keywords = fs.keyword_fail_reasons or fs.keyword_thresholds

    if not has_filter and not has_keywords:
        return []

    lines = ["", _box_top(), _box_title("FILTER DETAILS"), _box_sep(), _box_empty()]

    if has_filter:
        lines.append(_box_line(f"URL Pre-Filter: {fs.urls_filtered} URLs skipped"))
        for reason, count in sorted(
            fs.filter_reasons.items(), key=lambda x: -x[1]
        ):
            count_str = str(count).rjust(4)
            lines.append(_box_line(f"  {reason:<50}{count_str}"))
        lines.append(_box_empty())

    if has_keywords:
        checked = fs.keywords_checked
        passed = fs.keywords_passed
        lines.append(
            _box_line(f"Keyword Filter: {passed}/{checked} pages passed")
        )
        if fs.keyword_thresholds:
            lines.append(_box_line(f"  {fs.keyword_thresholds}"))
        for reason, count in sorted(
            fs.keyword_fail_reasons.items(), key=lambda x: -x[1]
        ):
            count_str = f"{count} {'page' if count == 1 else 'pages'}"
            lines.append(_box_line(f"  {reason:<46}{count_str}"))
        lines.append(_box_empty())

    if fs.near_misses:
        lines.append(_box_line("Near misses (close to passing):"))
        for nm in fs.near_misses[:5]:
            lines.append(_box_line(f"  {nm}"))
        if len(fs.near_misses) > 5:
            lines.append(
                _box_line(f"  ... and {len(fs.near_misses) - 5} more")
            )
        lines.append(_box_empty())

    lines.append(_box_bottom())
    return lines


def _generate_suggestions(report: RunReport) -> list[tuple[str, list[str]]]:
    """Generate suggestion tuples: (icon, [lines])."""
    suggestions: list[tuple[str, list[str]]] = []

    # Rule 1: Zero policies - diagnose bottleneck
    if report.policies_found == 0 and report.pages_crawled > 0:
        bottleneck_lines = ["No policies found -- pipeline bottleneck:"]
        if report.pages_success == 0:
            bottleneck_lines.append(
                "All pages failed to fetch. Check network and domain configs."
            )
        elif report.urls_filtered > 0 and report.pages_after_filter <= 0:
            bottleneck_lines.append(
                f"{report.urls_filtered} of {report.pages_success} successful "
                f"pages removed by URL pre-filter."
            )
            bottleneck_lines.append(
                "No pages remained for keyword analysis."
            )
            bottleneck_lines.append(
                "Review URL filter rules or domain start_paths."
            )
        elif report.keywords_passed == 0 and report.pages_after_filter > 0:
            af = report.pages_after_filter
            bottleneck_lines.append(
                f"{af} {'page' if af == 1 else 'pages'} reached keyword "
                f"check, all failed."
            )
            min_score = report.config.get("min_keyword_score", "?")
            bottleneck_lines.append(
                f"Content may not contain relevant terms (min score: {min_score})."
            )
        elif report.keywords_passed > 0 and report.llm_calls == 0:
            bottleneck_lines.append(
                f"{report.keywords_passed} pages passed keywords but "
                f"LLM analysis was skipped (--skip-llm or --dry-run)."
            )
        else:
            bottleneck_lines.append(
                f"{report.keywords_passed} pages sent to LLM, "
                f"none contained relevant policies."
            )
        suggestions.append(("[!]", bottleneck_lines))

    # Rule 2: High block rate per domain
    for d in report.domains:
        if d.pages_total > 0 and d.pages_blocked > 0:
            block_rate = d.pages_blocked / d.pages_total
            if block_rate >= 0.5:
                pct = int(block_rate * 100)
                lines = [
                    f"{d.domain_id}: {pct}% blocked "
                    f"({d.pages_blocked}/{d.pages_total} pages)",
                ]
                # Check what type of blocking
                block_types = set()
                for _, reason in d.blocked_pages:
                    if "access_denied" in reason:
                        block_types.add("access_denied")
                    elif "captcha" in reason:
                        block_types.add("captcha")
                    elif "rate_limited" in reason:
                        block_types.add("rate_limited")

                if "access_denied" in block_types:
                    lines.append(
                        "Consider adding requires_playwright: true "
                        "to domain config."
                    )
                if "captcha" in block_types:
                    lines.append(
                        "CAPTCHA detected -- may require human review."
                    )
                if "rate_limited" in block_types:
                    lines.append("Try increasing rate_limit_seconds.")
                suggestions.append(("[!]", lines))

    # Rule 3: Download errors
    for d in report.domains:
        download_errors = [
            p for p, m in d.error_pages if "Download" in m
        ]
        if download_errors:
            lines = [
                f"{d.domain_id}: {len(download_errors)} download trigger "
                f"{'error' if len(download_errors) == 1 else 'errors'}",
                "URLs triggered file downloads instead of HTML pages.",
            ]
            suggestions.append(("[i]", lines))

    # Rule 4: HTTP 404 errors (stale URLs)
    for d in report.domains:
        not_found = [p for p, m in d.error_pages if "404" in m or "not_found" in m]
        if len(not_found) >= 2:
            lines = [
                f"{d.domain_id}: {len(not_found)} pages returned 404",
                "Start paths may be stale -- verify URLs are still valid.",
            ]
            suggestions.append(("[i]", lines))

    # Rule 5: Timeout errors
    for d in report.domains:
        timeouts = [p for p, m in d.error_pages if "Timeout" in m or "timeout" in m]
        if timeouts:
            lines = [
                f"{d.domain_id}: {len(timeouts)} timeout "
                f"{'error' if len(timeouts) == 1 else 'errors'}",
                "Consider increasing timeout_seconds or adding "
                "requires_playwright: true.",
            ]
            suggestions.append(("[i]", lines))

    return suggestions


def _format_suggestions(report: RunReport) -> list[str]:
    """Format the suggestions section."""
    suggestions = _generate_suggestions(report)
    if not suggestions:
        return []

    lines = ["", _box_top(), _box_title("SUGGESTIONS"), _box_sep(), _box_empty()]

    for icon, suggestion_lines in suggestions:
        for j, line in enumerate(suggestion_lines):
            if j == 0:
                lines.append(_box_line(f"{icon} {line}"))
            else:
                lines.append(_box_line(f"    {line}"))
        lines.append(_box_empty())

    lines.append(_box_bottom())
    return lines


def _format_config_summary(report: RunReport) -> list[str]:
    """Format a compact config summary if available."""
    cfg = report.config
    if not cfg:
        return []

    lines = ["", _box_top(), _box_title("CONFIGURATION"), _box_sep()]

    kw_score = cfg.get("min_keyword_score", "?")
    kw_matches = cfg.get("min_keyword_matches", "?")
    combos = "yes" if cfg.get("required_combinations_enabled") else "no"
    lines.append(_box_line(f"Keywords:     score>={kw_score}  matches>={kw_matches}  combinations={combos}"))

    if cfg.get("enable_llm"):
        if cfg.get("enable_two_stage"):
            screening = cfg.get("screening_model", "?").split("-")[1] if "-" in cfg.get("screening_model", "") else cfg.get("screening_model", "?")
            analysis = cfg.get("analysis_model", "?").split("-")[1] if "-" in cfg.get("analysis_model", "") else cfg.get("analysis_model", "?")
            lines.append(_box_line(f"LLM:          two-stage ({screening} -> {analysis})"))
        else:
            model = cfg.get("analysis_model", "?")
            lines.append(_box_line(f"LLM:          {model}"))
    else:
        lines.append(_box_line("LLM:          disabled"))

    cache = "enabled" if cfg.get("cache_enabled") else "disabled"
    if cfg.get("cache_cleared"):
        cache += " (cleared)"
    lines.append(_box_line(f"Cache:        {cache}"))

    if cfg.get("dry_run"):
        lines.append(_box_line("Mode:         DRY RUN"))

    lines.append(_box_bottom())
    return lines


def format_report(report: RunReport) -> str:
    """Generate the complete terminal report."""
    lines: list[str] = []
    lines.extend(_format_header(report))
    lines.extend(_format_result_summary(report))
    lines.extend(_format_pipeline_funnel(report))
    lines.extend(_format_domain_breakdown(report))
    lines.extend(_format_filter_detail(report))
    lines.extend(_format_suggestions(report))
    lines.extend(_format_config_summary(report))
    lines.append("")
    return "\n".join(lines)
