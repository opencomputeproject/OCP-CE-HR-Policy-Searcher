"""Tests for the agent tools and orchestrator."""

from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from src.agent.tools import get_all_tools, execute_tool, POLICY_TOOLS, WEB_SEARCH_TOOL
from src.agent.orchestrator import (
    PolicyAgent, _build_system_prompt, _get_retry_delay,
    MAX_API_RETRIES, BASE_RETRY_DELAY, MAX_RETRY_DELAY,
)
from src.core.config import ConfigLoader
from src.orchestration.events import EventBroadcaster
from src.orchestration.scan_manager import ScanManager


@pytest.fixture
def config():
    c = ConfigLoader(config_dir="config")
    c.load()
    return c


@pytest.fixture
def scan_manager(config):
    broadcaster = EventBroadcaster()
    return ScanManager(config=config, broadcaster=broadcaster, data_dir="data")


class TestToolDefinitions:
    """Verify tool definitions match Anthropic API format."""

    def test_total_tool_count(self):
        tools = get_all_tools()
        assert len(tools) == 13

    def test_policy_tools_have_required_fields(self):
        for tool in POLICY_TOOLS:
            assert "name" in tool, "Missing name in tool"
            assert "description" in tool, f"Missing description in {tool['name']}"
            assert "input_schema" in tool, f"Missing input_schema in {tool['name']}"
            schema = tool["input_schema"]
            assert schema["type"] == "object", f"Schema type not 'object' in {tool['name']}"
            assert "properties" in schema, f"Missing properties in {tool['name']}"

    def test_web_search_is_server_side(self):
        assert WEB_SEARCH_TOOL["type"] == "web_search_20250305"
        assert WEB_SEARCH_TOOL["name"] == "web_search"
        assert "input_schema" not in WEB_SEARCH_TOOL

    def test_add_domain_has_url_required(self):
        tools = get_all_tools()
        add_domain = next(t for t in tools if t.get("name") == "add_domain")
        assert "url" in add_domain["input_schema"]["required"]

    def test_no_duplicate_tool_names(self):
        tools = get_all_tools()
        names = [t["name"] for t in tools]
        assert len(names) == len(set(names))


class TestToolDispatch:
    """Test that execute_tool dispatches correctly."""

    @pytest.mark.asyncio
    async def test_list_domains(self, config, scan_manager):
        result = await execute_tool("list_domains", {"group": "all"}, config, scan_manager)
        assert "count" in result
        assert "domains" in result
        assert result["count"] > 0

    @pytest.mark.asyncio
    async def test_list_domains_with_region(self, config, scan_manager):
        result = await execute_tool("list_domains", {"region": "eu"}, config, scan_manager)
        assert "count" in result
        for d in result["domains"]:
            assert "eu" in d["region"]

    @pytest.mark.asyncio
    async def test_estimate_cost(self, config, scan_manager):
        result = await execute_tool("estimate_cost", {"domains": "quick"}, config, scan_manager)
        assert "domain_count" in result
        assert "estimated_cost_usd" in result
        assert result["estimated_cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_match_keywords(self, config, scan_manager):
        result = await execute_tool(
            "match_keywords",
            {"text": "data center waste heat recovery policy"},
            config, scan_manager,
        )
        assert "score" in result
        assert result["score"] > 0
        assert len(result["matches"]) > 0

    @pytest.mark.asyncio
    async def test_get_policy_stats(self, config, scan_manager):
        result = await execute_tool("get_policy_stats", {}, config, scan_manager)
        assert "total" in result
        assert "by_jurisdiction" in result
        assert "by_type" in result

    @pytest.mark.asyncio
    async def test_unknown_tool(self, config, scan_manager):
        result = await execute_tool("nonexistent_tool", {}, config, scan_manager)
        assert "error" in result
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_get_domain_config_not_found(self, config, scan_manager):
        result = await execute_tool("get_domain_config", {"domain_id": "fake_domain"}, config, scan_manager)
        assert "error" in result
        assert "not found" in result["error"]


class TestSystemPrompt:
    """Test system prompt generation."""

    def test_includes_domain_count(self, config):
        prompt = _build_system_prompt(config)
        assert "275" in prompt or "government websites" in prompt

    def test_includes_regions(self, config):
        prompt = _build_system_prompt(config)
        assert "eu" in prompt
        assert "us" in prompt

    def test_includes_tool_descriptions(self, config):
        prompt = _build_system_prompt(config)
        assert "list_domains" in prompt
        assert "start_scan" in prompt
        assert "web_search" in prompt
        assert "add_domain" in prompt
        assert "analyze_url" in prompt

    def test_non_technical_language(self, config):
        prompt = _build_system_prompt(config)
        assert "not programmers" in prompt
        assert "plain" in prompt

    def test_polling_guidance_in_prompt(self, config):
        """System prompt should discourage aggressive polling."""
        prompt = _build_system_prompt(config)
        assert "recommended_wait_seconds" in prompt
        assert "30 seconds" in prompt


# --- _get_retry_delay ---

class TestGetRetryDelay:
    """Test retry delay extraction and exponential backoff."""

    def test_extracts_retry_after_header(self):
        """Should use retry-after header when present."""
        error = MagicMock(spec=anthropic.RateLimitError)
        error.response = MagicMock()
        error.response.headers = {"retry-after": "15"}
        delay = _get_retry_delay(error, attempt=1)
        assert delay == 15.0

    def test_caps_retry_after_at_max(self):
        """Extremely long retry-after should be capped."""
        error = MagicMock(spec=anthropic.RateLimitError)
        error.response = MagicMock()
        error.response.headers = {"retry-after": "9999"}
        delay = _get_retry_delay(error, attempt=1)
        assert delay == MAX_RETRY_DELAY

    def test_backoff_when_no_header(self):
        """Should use exponential backoff when no retry-after header."""
        error = MagicMock(spec=anthropic.RateLimitError)
        error.response = None
        delay1 = _get_retry_delay(error, attempt=1)
        delay2 = _get_retry_delay(error, attempt=2)
        delay3 = _get_retry_delay(error, attempt=3)
        assert delay1 == BASE_RETRY_DELAY           # 10s
        assert delay2 == BASE_RETRY_DELAY * 4        # 40s
        assert delay3 == min(BASE_RETRY_DELAY * 16, MAX_RETRY_DELAY)  # capped

    def test_backoff_with_invalid_header(self):
        """Should fall back to backoff when header is garbage."""
        error = MagicMock(spec=anthropic.RateLimitError)
        error.response = MagicMock()
        error.response.headers = {"retry-after": "not-a-number"}
        delay = _get_retry_delay(error, attempt=1)
        assert delay == BASE_RETRY_DELAY


# --- Agent Rate Limit Retry ---

def _make_text_response(text: str):
    """Create a mock API response with text content and end_turn."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    return response


class TestAgentRateLimitRetry:
    """Test that the agent loop retries on rate limit errors."""

    def _build_agent(self):
        """Create a PolicyAgent without real API key (for testing)."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(
            config=agent.config, broadcaster=agent.broadcaster, data_dir="data",
        )
        agent.tools = get_all_tools()
        agent.system_prompt = "test"
        agent.model = "test-model"
        return agent

    @pytest.mark.asyncio
    async def test_rate_limit_retry_succeeds(self):
        """Agent should retry on 429 and succeed on second attempt."""
        agent = self._build_agent()

        rate_error = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        rate_error.response = None

        success_response = _make_text_response("Here are the results.")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[rate_error, success_response]
        )
        agent.client = mock_client

        text_output = []
        result = await agent.run(
            "test message",
            on_text=lambda t: text_output.append(t),
        )

        assert "results" in result
        assert mock_client.messages.create.call_count == 2
        # Check that user was notified about the retry
        assert any("Rate limited" in t or "waiting" in t for t in text_output)

    @pytest.mark.asyncio
    async def test_rate_limit_retry_exhausted(self):
        """Agent should return friendly error after exhausting retries."""
        agent = self._build_agent()

        rate_error = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        rate_error.response = None

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[rate_error] * MAX_API_RETRIES
        )
        agent.client = mock_client

        result = await agent.run("test message")

        assert "Rate limit exceeded" in result
        assert "saved" in result.lower() or "search_policies" in result
        assert mock_client.messages.create.call_count == MAX_API_RETRIES

    @pytest.mark.asyncio
    async def test_overload_error_retries(self):
        """Agent should retry on 529 overloaded errors."""
        agent = self._build_agent()

        # Simulate 529 overload
        overload_error = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
        overload_error.status_code = 529
        overload_error.response = None

        success_response = _make_text_response("Done.")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[overload_error, success_response]
        )
        agent.client = mock_client

        result = await agent.run("test message")

        assert "Done" in result
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_auth_error_no_retry(self):
        """Authentication errors should fail immediately — no retry."""
        agent = self._build_agent()

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.AuthenticationError.__new__(
                anthropic.AuthenticationError
            )
        )
        agent.client = mock_client

        result = await agent.run("test message")

        assert "Authentication failed" in result
        # Should NOT retry — only 1 call
        assert mock_client.messages.create.call_count == 1
