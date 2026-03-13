"""CLI entry point for the standalone policy agent.

Usage:
    # Interactive mode (default)
    python -m src.agent

    # Single command
    python -m src.agent "Find heat reuse policies in Germany"

    # Discover new coverage for a country
    python -m src.agent --discover Poland

    # Deep scanning mode (more pages, wider keyword match)
    python -m src.agent --deep

    # View recent logs
    python -m src.agent --logs
    python -m src.agent --logs audit
    python -m src.agent --logs --level error
    python -m src.agent --logs --scan-id abc123

    # Help
    python -m src.agent --help
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Resolve .env from project root (2 levels up from src/agent/__main__.py)
# so credentials load regardless of the process working directory.
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env", override=True)

from ..core.log_setup import log_audit_event


def _print_help():
    """Print CLI usage help and exit."""
    print("""
OCP CE HR Policy Searcher — CLI Reference
=====================================

Usage:
  python -m src.agent                    Interactive mode (default)
  python -m src.agent "message"          Single command, then exit
  python -m src.agent --discover COUNTRY Discover websites for a country
  python -m src.agent --deep             Deep scanning (3-4x cost)
  python -m src.agent --logs             View recent log entries
  python -m src.agent --help             Show this help

Scanning Examples:
  "Scan virginia"                        Scan all Virginia domains
  "Scan us_states"                       Scan all US state domains
  "Scan eu"                              Scan all EU domains
  "Scan pending_legislation"             Scan active/pending bills
  "Scan nordic"                          Scan Nordic countries
  "What groups can I scan?"              List available scan targets

Scan Targets:
  Groups:  eu, nordic, us, us_states, us_federal, apac, uk,
           leaders, emerging, pending_legislation
  States:  virginia, california, texas, colorado, minnesota, ...
  Regions: eu_central, eu_west, eu_south, eu_east

Log Viewer:
  python -m src.agent --logs             Last 30 log entries
  python -m src.agent --logs audit       Last 30 audit events
  python -m src.agent --logs --level error   Only errors
  python -m src.agent --logs --level warning Warnings and above
  python -m src.agent --logs --lines 100     Show 100 entries
  python -m src.agent --logs --scan-id abc   Filter by scan ID
  python -m src.agent --logs --json          Raw JSON output

Flags can be combined:
  python -m src.agent --deep --discover Germany
  python -m src.agent --logs audit --scan-id abc123

Environment Variables:
  ANTHROPIC_API_KEY   Required. Your Anthropic API key.
  OCP_CONFIG_DIR      Config directory (default: config)
  OCP_DATA_DIR        Data/logs directory (default: data)

Log Files:
  data/logs/agent.log    Structured JSON logs (rotated, 10 MB x 5)
  data/logs/audit.jsonl  Critical events (scan start/complete, policies found)

API (for React frontend):
  GET /api/logs          Recent log entries (filterable)
  GET /api/logs/audit    Audit trail events
  GET /api/logs/info     Log file paths and session info
""")


def _handle_logs_command(args: list[str], data_dir: str):
    """Handle the --logs CLI command.  Shows recent log entries.

    Supports subcommands and filters:
      --logs             → recent agent log entries
      --logs audit       → recent audit events
      --logs --level X   → filter by minimum level
      --logs --scan-id X → filter by scan ID
      --logs --lines N   → number of entries (default 30)
      --logs --json      → raw JSON output (for piping)
    """
    from ..core.log_setup import read_logs, read_audit_log, get_log_file_paths

    # Parse log sub-arguments
    log_type = "agent"  # default
    level = None
    scan_id = None
    num_lines = 30
    raw_json = False
    i = 0

    while i < len(args):
        arg = args[i]
        if arg == "audit":
            log_type = "audit"
        elif arg == "--level" and i + 1 < len(args):
            i += 1
            level = args[i]
        elif arg == "--scan-id" and i + 1 < len(args):
            i += 1
            scan_id = args[i]
        elif arg == "--lines" and i + 1 < len(args):
            i += 1
            try:
                num_lines = int(args[i])
            except ValueError:
                print(f"Error: --lines expects a number, got '{args[i]}'")
                sys.exit(1)
        elif arg == "--json":
            raw_json = True
        i += 1

    # Show log file locations
    paths = get_log_file_paths(data_dir)
    if not raw_json:
        print()
        print(f"  Log files: {paths['log_directory']}")
        if paths["agent_log"]:
            log_size = Path(paths["agent_log"]).stat().st_size
            print(f"  Agent log: {_format_size(log_size)}")
        if paths["audit_log"]:
            audit_size = Path(paths["audit_log"]).stat().st_size
            print(f"  Audit log: {_format_size(audit_size)}")
        print()

    # Read and display entries
    if log_type == "audit":
        entries = read_audit_log(
            data_dir, lines=num_lines, scan_id=scan_id,
            event_type=level,  # reuse --level for event type filter
        )
        if not entries:
            print("  No audit events found.")
            return
        if raw_json:
            for entry in reversed(entries):  # chronological order
                print(json.dumps(entry, default=str))
        else:
            print(f"  Last {len(entries)} audit events"
                  f"{f' (scan: {scan_id})' if scan_id else ''}:")
            print("  " + "-" * 60)
            for entry in reversed(entries):  # chronological order
                ts = entry.get("timestamp", "?")[:19]
                event = entry.get("event", "?")
                sid = entry.get("scan_id", "")
                extra = ""
                if event == "policy_found":
                    extra = f" — {entry.get('policy_name', '?')}"
                elif event == "scan_completed":
                    extra = (f" — {entry.get('policies_found', 0)} policies, "
                             f"${entry.get('cost_usd', 0):.2f}")
                elif event == "scan_started":
                    extra = f" — {entry.get('domain_count', '?')} domains"
                elif event == "session_ended":
                    extra = f" — {entry.get('reason', 'unknown')}"
                print(f"  {ts}  {event:<18} [{sid}]{extra}")
    else:
        entries = read_logs(
            data_dir, lines=num_lines, level=level, scan_id=scan_id,
        )
        if not entries:
            print("  No log entries found"
                  f"{f' at level {level}+' if level else ''}.")
            return
        if raw_json:
            for entry in reversed(entries):
                print(json.dumps(entry, default=str))
        else:
            label = f" (level: {level}+)" if level else ""
            label += f" (scan: {scan_id})" if scan_id else ""
            print(f"  Last {len(entries)} log entries{label}:")
            print("  " + "-" * 60)
            for entry in reversed(entries):
                ts = entry.get("timestamp", "?")[:19]
                lvl = entry.get("level", "?").upper()[:5]
                event = entry.get("event", "?")
                sid = entry.get("scan_id", "")
                sid_str = f" [{sid}]" if sid else ""
                # Color-code by level
                if lvl.startswith("ERROR"):
                    prefix = "❌"
                elif lvl.startswith("WARNI"):
                    prefix = "⚠️ "
                elif lvl.startswith("INFO"):
                    prefix = "  "
                else:
                    prefix = "  "
                print(f"  {prefix}{ts} {lvl:5} {event}{sid_str}")


def _format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string (e.g. '2.3 MB')."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _print_banner(log_file: Path):
    """Print the welcome banner for interactive mode.

    Shows usage tips, log file location, and log viewer hint so users
    know that all activity is being recorded and can be reviewed later.
    """
    print()
    print("OCP CE HR Policy Searcher")
    print("=" * 40)
    print("I help you find data center heat reuse")
    print("policies worldwide.")
    print()
    print("Try asking:")
    print('  "What countries are covered?"')
    print('  "Find heat reuse policies in Germany"')
    print('  "Scan Nordic countries for new policies"')
    print('  "How much would it cost to scan all EU domains?"')
    print()
    print(f"  📋 Logs: {log_file}")
    print("  📋 View logs: python -m src.agent --logs")
    print()
    print("Type 'quit' or 'exit' to stop.")
    print("Press Ctrl+C to interrupt a running operation.")
    print()


def _on_text(text: str):
    """Print Claude's text output."""
    print(text)


def _on_tool_call(name: str, input_data: dict):
    """Show a brief status line when a tool is called."""
    descriptions = {
        "list_domains": "Browsing available domains...",
        "list_groups": "Looking up available groups and regions...",
        "get_domain_config": f"Looking up domain '{input_data.get('domain_id', '')}'...",
        "start_scan": f"Starting scan of '{input_data.get('domains', 'quick')}' domains...",
        "get_scan_status": "Checking scan progress...",
        "list_scans": "Checking all scans...",
        "stop_scan": "Cancelling scan...",
        "analyze_url": f"Analyzing {input_data.get('url', 'URL')}...",
        "match_keywords": "Testing keywords...",
        "search_policies": "Searching policies...",
        "get_policy_stats": "Getting policy statistics...",
        "get_audit_advisory": "Getting AI insights...",
        "estimate_cost": f"Estimating cost for '{input_data.get('domains', '')}' scan...",
        "add_domain": f"Adding {input_data.get('url', 'domain')} to database...",
        "web_search": "Searching the web...",
    }
    status = descriptions.get(name, f"Running {name}...")
    print(f"\n  [{status}]\n")


# Track which domains have already been celebrated, so we only show the
# 🎉 line once per domain instead of repeating it on every poll.
_celebrated_domains: set[str] = set()


def _on_tool_result(name: str, result):
    """Show brief result summaries for key tools.

    Uses emoji icons to make important events (policy finds, scan progress)
    visually distinct from routine status updates.
    """
    if not isinstance(result, dict):
        return

    # Show a one-line summary for tools where the user might be waiting
    if name == "list_domains" and "count" in result:
        print(f"  → Found {result['count']} domains")

    elif name == "list_groups":
        groups_count = len(result.get("groups", {}))
        states_count = len(result.get("us_states", {}))
        total = result.get("total_domains", "?")
        print(f"  → {groups_count} groups, {states_count} US states ({total} total domains)")

    elif name == "start_scan" and "scan_id" in result:
        msg = (f"  → Scan {result['scan_id']} started "
               f"({result.get('domain_count', '?')} domains)")
        msg += "\n  📋 Progress is being logged — view anytime with: python -m src.agent --logs"
        if result.get("warning"):
            msg += f"\n  ⚠️  {result['warning']}"
        print(msg)
        # Reset celebrations for the new scan
        _celebrated_domains.clear()

    elif name == "get_scan_status" and "status" in result:
        progress = result.get("progress", {})
        done = progress.get("completed", "?")
        total = progress.get("total", "?")
        policies = result.get("policy_count", 0)

        # Status icon: running vs completed
        if result["status"] == "running":
            icon = "⏳"
        elif result["status"] == "completed":
            icon = "✅"
        elif result["status"] == "failed":
            icon = "❌"
        else:
            icon = "→"

        status_line = (f"  {icon} {result['status']}: {done}/{total} domains, "
                       f"{policies} policies found so far (running total)")
        # When scan completes, remind user that results are saved
        if result["status"] == "completed":
            status_line += "\n  📋 Results saved to data/policies.json"
        print(status_line)

        # Celebrate domains that found policies — but only the FIRST time
        # we see them, so the celebration doesn't repeat on every poll.
        for dp in progress.get("domains", []):
            found = dp.get("policies_found", 0)
            domain_key = dp.get("domain_id", dp.get("domain_name", ""))
            if found > 0 and domain_key not in _celebrated_domains:
                _celebrated_domains.add(domain_key)
                name_str = dp.get("domain_name", domain_key)
                print(f"  🎉 NEW: {name_str} — {found} policy(ies) found!")

    elif name == "list_scans" and "scans" in result:
        scans = result["scans"]
        if not scans:
            print("  → No scans in this session")
        else:
            for s in scans:
                icon = {"running": "⏳", "completed": "✅", "failed": "❌"}.get(
                    s["status"], "→"
                )
                print(f"  {icon} {s['scan_id']}: {s['status']} "
                      f"({s['domain_group']}, {s['policy_count']} policies)")

    elif name == "estimate_cost" and "estimated_cost_usd" in result:
        print(f"  → Estimated cost: ${result['estimated_cost_usd']:.2f} "
              f"({result.get('domain_count', '?')} domains)")

    elif name == "search_policies" and "count" in result:
        print(f"  → {result['count']} policies match")

    elif name == "match_keywords" and "score" in result:
        matches = len(result.get("matches", []))
        print(f"  → Score: {result['score']}, {matches} keyword matches")

    elif name == "analyze_url":
        if "error" in result and len(result) == 1:
            print(f"  → Error: {result['error']}")
        elif "policy" in result:
            policy = result["policy"]
            pname = policy.get("policy_name", "policy")
            score = policy.get("relevance_score", "?")
            print(f"  🎉 ★ Found: {pname} (relevance: {score}/10) ★")
        elif "keyword_score" in result:
            ks = result["keyword_score"]
            if ks == 0:
                print(f"  → Keyword score: {ks} (threshold not met)")
            else:
                print(f"  → Keyword score: {ks}")

    elif name == "web_search":
        print("  → Search results received")

    elif name == "add_domain":
        if result.get("success"):
            regions = ", ".join(result.get("region", []))
            print(f"  → Added domain '{result.get('domain_id', '?')}' "
                  f"(region: {regions})")
        elif result.get("already_exists"):
            print(f"  → Domain '{result.get('domain_id', '?')}' "
                  f"already in database")


async def _run_interactive(agent, log_file: Path):
    """Run the agent in interactive chat mode.

    Logs session end events (quit, Ctrl+C, EOF) to both the standard log
    and the audit trail so there is always a record of how the session
    ended — even if a scan was still running.
    """
    interactive_logger = logging.getLogger(__name__)
    _print_banner(log_file)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            interactive_logger.info("Session ended by user (Ctrl+C / EOF)")
            log_audit_event(
                data_dir=agent.scan_manager.data_dir,
                event="session_ended",
                reason="interrupt",
            )
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            interactive_logger.info(
                "Session ended by user (quit command)",
                extra={"quit_command": user_input.lower()},
            )
            log_audit_event(
                data_dir=agent.scan_manager.data_dir,
                event="session_ended",
                reason="quit",
            )
            print("Goodbye!")
            break

        print("\n  Thinking...\n")
        try:
            await agent.run(
                user_input,
                on_text=_on_text,
                on_tool_call=_on_tool_call,
                on_tool_result=_on_tool_result,
            )
        except KeyboardInterrupt:
            print("\n\n  [Interrupted — ready for next question]\n")
        except Exception as e:
            print(f"\nError: {e}")
        print()


async def _run_single(agent, message: str):
    """Run a single command and exit.

    Logs a session_ended audit event on Ctrl+C so the audit trail
    records the interruption even if a scan was running in the
    background.
    """
    single_logger = logging.getLogger(__name__)
    print("  Thinking...\n")
    try:
        await agent.run(
            message,
            on_text=_on_text,
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
        )
    except KeyboardInterrupt:
        single_logger.info("Single-command session interrupted (Ctrl+C)")
        log_audit_event(
            data_dir=agent.scan_manager.data_dir,
            event="session_ended",
            reason="interrupt",
        )
        print("\n\nInterrupted.")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Entry point for ``python -m src.agent``.

    Handles CLI flag routing:
    - ``--help`` and ``--logs`` work without an API key
    - ``--deep``, ``--discover``, and interactive mode require an API key
    """
    args = sys.argv[1:]

    # --help and --logs don't need an API key — handle them first
    if args and args[0] == "--help":
        _print_help()
        sys.exit(0)

    if args and args[0] == "--logs":
        data_dir = os.environ.get("OCP_DATA_DIR", "data")
        _handle_logs_command(args[1:], data_dir)
        sys.exit(0)

    # Check for API key (everything below needs it)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY is not set.")
        print()
        print("Quick fix — add your key to the .env file:")
        print("  cp config/example.env .env")
        print("  # then edit .env and paste your key")
        print()
        print("Or set it directly in your shell:")
        print("  Linux/macOS:  export ANTHROPIC_API_KEY=sk-ant-...")
        print("  PowerShell:   $env:ANTHROPIC_API_KEY='sk-ant-...'")
        print()
        print("Get your key at: https://console.anthropic.com/")
        sys.exit(1)

    # Catch the common mistake of running with the placeholder key
    if "your-key-here" in api_key or len(api_key) < 40:
        print("Error: ANTHROPIC_API_KEY looks like the placeholder value.")
        print()
        print("Open .env and replace the key with your real API key.")
        print("Real keys are 100+ characters starting with 'sk-ant-'.")
        print()
        print("Get your key at: https://console.anthropic.com/")
        sys.exit(1)

    # Import here to avoid import errors when just checking --help
    from ..core.log_setup import setup_logging
    from .orchestrator import PolicyAgent

    config_dir = os.environ.get("OCP_CONFIG_DIR", "config")
    data_dir = os.environ.get("OCP_DATA_DIR", "data")

    # Set up structured logging (JSON to file, human-readable to console)
    log_file = setup_logging(data_dir)
    logger = logging.getLogger(__name__)
    logger.info("OCP CE HR Policy Searcher starting")

    agent = PolicyAgent(
        api_key=api_key,
        config_dir=config_dir,
        data_dir=data_dir,
    )

    # --deep: override settings for wider/deeper crawling.
    # Increases max_depth (3→5), max_pages (200→500), lowers keyword
    # threshold (3.0→2.0) to cast a wider net. Costs ~3-4x more.
    if args and args[0] == "--deep":
        agent.scan_manager.config.settings.crawl.max_depth = 5
        agent.scan_manager.config.settings.crawl.max_pages_per_domain = 500
        agent.scan_manager.config.settings.analysis.min_keyword_score = 2.0
        print("  [Deep scanning mode: max_depth=5, max_pages=500, "
              "min_keyword_score=2.0]")
        print()
        args = args[1:]  # consume --deep, continue with remaining args

    if args and args[0] == "--discover":
        country = " ".join(args[1:]) if len(args) > 1 else ""
        if not country:
            print("Usage: python -m src.agent --discover <country>")
            print("Example: python -m src.agent --discover Poland")
            sys.exit(1)
        message = (
            f"Discover new coverage for {country}. "
            f"Search for government websites about data center waste heat, "
            f"energy efficiency, district heating, and heat recovery regulation "
            f"in {country}. Use the country's native language for search terms "
            f"when appropriate. Add any relevant government websites you find. "
            f"Then analyze the most promising pages for policy content. "
            f"Summarize what you discovered."
        )
        asyncio.run(_run_single(agent, message))
    elif args:
        # Single command
        message = " ".join(args)
        asyncio.run(_run_single(agent, message))
    else:
        asyncio.run(_run_interactive(agent, log_file))


if __name__ == "__main__":
    main()
