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

load_dotenv()


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
    """Optionally show brief result summaries."""
    # Keep it minimal — Claude will summarize results
    pass


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

        print()
        try:
            await agent.run(
                user_input,
                on_text=_on_text,
                on_tool_call=_on_tool_call,
                on_tool_result=_on_tool_result,
            )
        except Exception as e:
            print(f"\nError: {e}")
        print()


async def _run_single(agent, message: str):
    """Run a single command and exit."""
    try:
        await agent.run(
            message,
            on_text=_on_text,
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
        )
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is required.")
        print()
        print("Set it with:")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
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
