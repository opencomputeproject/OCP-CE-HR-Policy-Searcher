"""Standalone agent loop using Anthropic API tool use.

No MCP required — just an API key. The agent uses the same 11 policy
hub tools as the MCP server, plus web search and add_domain for
discovering new government websites.
"""

import asyncio
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

# Rate limit retry configuration for the agent conversation loop.
# These are separate from the scanner's LLM retry settings (in ClaudeClient)
# because the agent loop makes different API calls (messages.create with tools)
# and needs its own backoff strategy.
MAX_API_RETRIES = 3
BASE_RETRY_DELAY = 10.0   # seconds — generous because 429 needs real wait time
MAX_RETRY_DELAY = 120.0   # cap at 2 minutes


def _get_retry_delay(error: anthropic.RateLimitError, attempt: int) -> float:
    """Extract retry-after from API response headers, or use exponential backoff.

    The Anthropic API returns a 'retry-after' header on 429 responses indicating
    how long to wait. If that header is missing or unparseable, we fall back to
    exponential backoff: 10s → 40s → 120s (capped).

    Args:
        error: The RateLimitError from the Anthropic SDK.
        attempt: Current retry attempt (1-indexed). Used for backoff calculation.

    Returns:
        Number of seconds to wait before retrying.
    """
    # Try to extract retry-after from response headers
    try:
        if hasattr(error, "response") and error.response:
            retry_after = error.response.headers.get("retry-after")
            if retry_after:
                return min(float(retry_after), MAX_RETRY_DELAY)
    except (ValueError, AttributeError):
        pass

    # Exponential backoff: 10s * (4^(attempt-1)) → 10s, 40s, 120s (capped)
    delay = BASE_RETRY_DELAY * (4 ** (attempt - 1))
    return min(delay, MAX_RETRY_DELAY)


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

When a scan is running, use get_scan_status to check progress. The response \
includes a recommended_wait_seconds field — ALWAYS wait at least that long \
between checks. Do NOT poll more than once per 30 seconds. Between checks, \
give the user a brief progress summary. When all domains are complete, show \
the final results. Results are saved automatically per-domain, so nothing is \
lost even if the session ends early.

## DISCOVER New Coverage

When asked to discover or expand coverage for a country or region:
1. web_search "[country] energy ministry data center waste heat"
2. web_search "[country] waste heat recovery regulation legislation"
3. web_search "[country] district heating policy law"
4. For each relevant government website found → add_domain to register it \
(it will be auto-assigned to the correct regional group)
5. analyze_url on the most promising pages to get immediate policy insights
6. Summarize findings: what was discovered, what domains were added, and \
what policies were found

Search tips for better results:
- Use the country's native language for search terms (e.g., "Abwärme" for \
German, "chaleur résiduelle" for French, "spillvarme" for Norwegian)
- Look for energy ministries, environmental agencies, and legislation databases
- Government sites (.gov, .gouv.fr, .gov.uk, etc.) are highest priority
- Official gazettes and law databases contain enacted legislation

Available domain groups: {group_list}
"""


class PolicyAgent:
    """Standalone agent that orchestrates policy scanning via Anthropic API tool use.

    The agent loop handles rate limiting automatically with exponential backoff,
    retrying up to MAX_API_RETRIES times before giving up. Background scans
    continue running even if the conversation hits rate limits.

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

        Handles rate limiting with automatic retry and exponential backoff.
        Each API call is retried up to MAX_API_RETRIES times on 429/529
        errors before returning a friendly error message.

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
            # Retry loop for rate limits on this single API call
            response = None
            for api_attempt in range(1, MAX_API_RETRIES + 1):
                try:
                    response = await self.client.messages.create(
                        model=self.model,
                        max_tokens=4096,
                        system=self.system_prompt,
                        tools=self.tools,
                        messages=messages,
                    )
                    break  # Success — exit retry loop

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

                except anthropic.RateLimitError as e:
                    delay = _get_retry_delay(e, api_attempt)
                    if api_attempt < MAX_API_RETRIES:
                        logger.warning(
                            f"Agent rate limited, retry {api_attempt}/{MAX_API_RETRIES} "
                            f"in {delay:.0f}s"
                        )
                        if on_text:
                            on_text(
                                f"\n  ⏳ Rate limited — waiting {delay:.0f}s "
                                f"before retry ({api_attempt}/{MAX_API_RETRIES})...\n"
                            )
                        await asyncio.sleep(delay)
                    else:
                        # Exhausted retries — tell user their scan data is safe
                        error_msg = (
                            "Rate limit exceeded after retries. "
                            "Any running scans will continue in the background "
                            "and results are saved automatically.\n"
                            "Wait a minute and try again, or check results with: "
                            "search_policies"
                        )
                        logger.error(f"Agent rate limit exhausted after {MAX_API_RETRIES} retries")
                        if on_text:
                            on_text(error_msg)
                        return error_msg

                except anthropic.APIStatusError as e:
                    # 529 overloaded — retry like rate limit
                    if e.status_code == 529 and api_attempt < MAX_API_RETRIES:
                        delay = _get_retry_delay(
                            anthropic.RateLimitError.__new__(anthropic.RateLimitError),
                            api_attempt,
                        )
                        logger.warning(
                            f"API overloaded (529), retry {api_attempt}/{MAX_API_RETRIES} "
                            f"in {delay:.0f}s"
                        )
                        if on_text:
                            on_text(
                                f"\n  ⏳ API overloaded — waiting {delay:.0f}s "
                                f"before retry...\n"
                            )
                        await asyncio.sleep(delay)
                    else:
                        error_msg = f"API error: {e}"
                        logger.error(error_msg)
                        if on_text:
                            on_text(error_msg)
                        return error_msg

                except anthropic.APIError as e:
                    error_msg = f"API error: {e}"
                    logger.error(error_msg)
                    if on_text:
                        on_text(error_msg)
                    return error_msg

            if response is None:
                # Should not happen, but defensive
                return "Failed to get API response after retries."

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
