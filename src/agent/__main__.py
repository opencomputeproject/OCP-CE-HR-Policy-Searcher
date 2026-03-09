"""CLI entry point for the standalone policy agent.

Usage:
    # Interactive mode (default)
    python -m src.agent

    # Single command
    python -m src.agent "Find heat reuse policies in Germany"
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)  # .env wins over stale system env vars


def _print_banner():
    print()
    print("OCP Policy Hub Agent")
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
        "get_domain_config": f"Looking up domain '{input_data.get('domain_id', '')}'...",
        "start_scan": f"Starting scan of '{input_data.get('domains', 'quick')}' domains...",
        "get_scan_status": "Checking scan progress...",
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


def _on_tool_result(name: str, result: dict):
    """Show brief result summaries for key tools."""
    if not isinstance(result, dict):
        return

    # Show a one-line summary for tools where the user might be waiting
    if name == "list_domains" and "count" in result:
        print(f"  → Found {result['count']} domains")
    elif name == "start_scan" and "scan_id" in result:
        print(f"  → Scan {result['scan_id']} started ({result.get('domain_count', '?')} domains)")
    elif name == "get_scan_status" and "status" in result:
        progress = result.get("progress", {})
        done = progress.get("completed", "?")
        total = progress.get("total", "?")
        policies = result.get("policy_count", 0)
        print(f"  → {result['status']}: {done}/{total} domains, {policies} policies found")
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
            print(f"  → Found: {policy.get('policy_name', 'policy')} "
                  f"(relevance: {policy.get('relevance_score', '?')}/10)")
        elif "keyword_score" in result:
            print(f"  → Keyword score: {result['keyword_score']} "
                  f"(threshold not met)" if result["keyword_score"] == 0
                  else f"  → Keyword score: {result['keyword_score']}")
    elif name == "web_search":
        print("  → Search results received")
    elif name == "add_domain":
        if result.get("success"):
            print(f"  → Added domain '{result.get('domain_id', '?')}' "
                  f"(region: {', '.join(result.get('region', []))})")
        elif result.get("already_exists"):
            print(f"  → Domain '{result.get('domain_id', '?')}' already in database")


async def _run_interactive(agent):
    """Run the agent in interactive chat mode."""
    _print_banner()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
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
    """Run a single command and exit."""
    print("  Thinking...\n")
    try:
        await agent.run(
            message,
            on_text=_on_text,
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # Check for API key
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
    from .orchestrator import PolicyAgent

    config_dir = os.environ.get("OCP_CONFIG_DIR", "config")
    data_dir = os.environ.get("OCP_DATA_DIR", "data")

    agent = PolicyAgent(
        api_key=api_key,
        config_dir=config_dir,
        data_dir=data_dir,
    )

    # Single command or interactive mode
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        asyncio.run(_run_single(agent, message))
    else:
        asyncio.run(_run_interactive(agent))


if __name__ == "__main__":
    main()
