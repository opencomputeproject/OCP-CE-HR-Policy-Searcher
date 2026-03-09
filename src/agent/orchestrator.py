"""Standalone agent loop using Anthropic API tool use.

No MCP required — just an API key. The agent uses the same 11 policy
hub tools as the MCP server, plus web search and add_domain for
discovering new government websites.
"""

import json
import logging
from typing import Any, Callable, Optional

import anthropic

from ..core.config import ConfigLoader
from ..orchestration.events import EventBroadcaster
from ..orchestration.scan_manager import ScanManager
from .tools import execute_tool, get_all_tools

logger = logging.getLogger(__name__)

# Default model for the agent
DEFAULT_MODEL = "claude-sonnet-4-20250514"


def _build_system_prompt(config: ConfigLoader) -> str:
    """Build the system prompt with dynamic config info."""
    # Count domains and regions
    try:
        all_domains = config.get_enabled_domains("all")
        domain_count = len(all_domains)
        regions = set()
        for d in all_domains:
            for r in d.get("region", []):
                regions.add(r)
        region_count = len(regions)
        region_list = ", ".join(sorted(regions)) if regions else "none configured"
    except Exception:
        domain_count = 0
        region_count = 0
        region_list = "none configured"

    # Get available groups
    try:
        groups = config.list_groups()
        group_list = ", ".join(sorted(groups)) if groups else "quick, all"
    except Exception:
        group_list = "quick, eu, nordic, dach, north_america, asia_pacific, all"

    return f"""You are the OCP Policy Hub assistant. You help people discover government \
policies related to data center waste heat reuse around the world.

Your users are engineers, policy researchers, and OCP members who want to find \
relevant laws, regulations, incentives, and requirements. They are not programmers \
— explain everything in plain, clear language.

## What You Can Do

DISCOVER new government websites:
- Use web_search to find government websites about heat reuse policies in any \
country, even ones not in the database yet
- Use add_domain to permanently add discovered websites to the database
- Use analyze_url to check any individual webpage for policy content

SCAN known government websites:
- The database currently has {domain_count} government websites across \
{region_count} regions ({region_list})
- Use list_domains to see what's available by country or region
- Use estimate_cost to check scanning costs before starting
- Use start_scan to crawl websites and discover policies automatically
- Use get_scan_status to monitor progress (scans run in the background)

EXPLORE results:
- Use search_policies to find policies by country, type, or keywords
- Use get_policy_stats for an overview of everything discovered
- Use get_audit_advisory for AI-generated insights after a scan

## How to Help Users

When someone asks to find policies in a specific country:
1. Check list_domains for existing coverage in that country/region
2. If no coverage exists, use web_search to find relevant government websites, \
then add_domain to add them to the database
3. Use estimate_cost to show the expected scanning cost
4. Start the scan and monitor progress with get_scan_status
5. Once complete, summarize results clearly: policy name, country, what it \
requires, and how relevant it is (1-10 scale)
6. Check get_audit_advisory for additional insights

Present results organized by country. Highlight the most important findings \
first. Explain what each policy means in practical terms. Flag anything that \
may need manual verification.

When a scan is running, poll get_scan_status every few seconds until it completes. \
Show the user brief progress updates.

Available domain groups: {group_list}
"""


class PolicyAgent:
    """Standalone agent that orchestrates policy scanning via Anthropic API tool use.

    Usage:
        agent = PolicyAgent(api_key="sk-ant-...")
        result = await agent.run("Find heat reuse policies in Germany")
        print(result)
    """

    def __init__(
        self,
        api_key: str,
        config_dir: str = "config",
        data_dir: str = "data",
        model: str = DEFAULT_MODEL,
    ):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

        # Initialize shared resources (same as MCP server singletons)
        self.config = ConfigLoader(config_dir=config_dir)
        self.config.load()

        self.broadcaster = EventBroadcaster()
        self.scan_manager = ScanManager(
            config=self.config,
            broadcaster=self.broadcaster,
            api_key=api_key,
            data_dir=data_dir,
        )

        self.tools = get_all_tools()
        self.system_prompt = _build_system_prompt(self.config)

    async def run(
        self,
        user_message: str,
        on_text: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
        on_tool_result: Optional[Callable[[str, dict], None]] = None,
        max_iterations: int = 50,
    ) -> str:
        """Run the agent loop with a user message.

        Args:
            user_message: Natural language instruction from the user.
            on_text: Callback for Claude's text output (streaming to CLI/WebSocket).
            on_tool_call: Callback when a tool is called (name, input).
            on_tool_result: Callback when a tool returns (name, result).
            max_iterations: Safety limit on agent loop iterations.

        Returns:
            Claude's final text response.
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]

        all_text_parts: list[str] = []
        tools_called: list[str] = []

        for iteration in range(max_iterations):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=self.system_prompt,
                    tools=self.tools,
                    messages=messages,
                )
            except anthropic.AuthenticationError:
                error_msg = (
                    "Authentication failed — your API key is invalid.\n"
                    "\n"
                    "Quick fix:\n"
                    "  1. Open your .env file\n"
                    "  2. Replace the ANTHROPIC_API_KEY value with a real key\n"
                    "     (it should be ~100+ characters starting with sk-ant-)\n"
                    "  3. Get a key at: https://console.anthropic.com/\n"
                    "  4. Restart the agent"
                )
                logger.error("Anthropic API authentication failed")
                if on_text:
                    on_text(error_msg)
                return error_msg
            except anthropic.APIError as e:
                error_msg = f"API error: {e}"
                logger.error(error_msg)
                if on_text:
                    on_text(error_msg)
                return error_msg

            # Process response content blocks
            text_parts: list[str] = []
            tool_uses: list[Any] = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                    if on_text:
                        on_text(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)
                # web_search results come as server_tool_use — no dispatch needed
                # The results are automatically included in the response

            all_text_parts.extend(text_parts)

            # If no tool calls or stop_reason is end_turn, we're done
            if response.stop_reason == "end_turn" or not tool_uses:
                break

            # Add assistant response to message history
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool and collect results
            tool_results: list[dict[str, Any]] = []
            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_input = tool_use.input
                tools_called.append(tool_name)

                if on_tool_call:
                    on_tool_call(tool_name, tool_input)

                logger.info(f"Executing tool: {tool_name}")

                try:
                    result = await execute_tool(
                        name=tool_name,
                        arguments=tool_input,
                        config=self.config,
                        scan_manager=self.scan_manager,
                    )
                    # Mark as tool failure only when error is the sole content.
                    # Partial results (e.g. analyze_url returning url+status+error)
                    # are NOT tool failures — they contain useful context.
                    is_error = (
                        isinstance(result, dict)
                        and "error" in result
                        and len(result) == 1
                    )
                    result_content = json.dumps(result, indent=2, default=str)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_content,
                        **({"is_error": True} if is_error else {}),
                    })
                except Exception as e:
                    logger.error(f"Tool {tool_name} failed: {e}")
                    result = {"error": str(e)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result),
                        "is_error": True,
                    })

                if on_tool_result:
                    on_tool_result(tool_name, result)

            # Send tool results back to Claude
            messages.append({"role": "user", "content": tool_results})
        else:
            # Hit max_iterations
            limit_msg = f"(Reached {max_iterations} iteration limit)"
            all_text_parts.append(limit_msg)
            if on_text:
                on_text(limit_msg)

        return "\n".join(all_text_parts)

    async def close(self):
        """Clean up resources."""
        await self.client.close()
