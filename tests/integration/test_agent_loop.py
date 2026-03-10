"""Integration tests for the agent loop with mocked Anthropic API."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from src.agent.orchestrator import PolicyAgent


def _make_text_response(text: str):
    """Create a mock API response with text content and end_turn."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    return response


def _make_tool_use_response(tool_name: str, tool_input: dict, tool_id: str = "tool_1"):
    """Create a mock API response with a tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    block.id = tool_id

    response = MagicMock()
    response.content = [block]
    response.stop_reason = "tool_use"
    return response


class TestAgentLoop:
    """Test the agent loop with mocked Anthropic API."""

    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """Agent returns text without calling any tools."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent._messages = []

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_text_response("Here are the available domains.")
        )
        agent.client = mock_client

        # Need config and scan_manager for tool dispatch
        from src.core.config import ConfigLoader
        from src.orchestration.events import EventBroadcaster
        from src.orchestration.scan_manager import ScanManager
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(config=agent.config, broadcaster=agent.broadcaster, data_dir="data")

        result = await agent.run("What domains are available?")
        assert "available domains" in result

    @pytest.mark.asyncio
    async def test_tool_call_then_response(self):
        """Agent calls a tool, gets result, then responds with text."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent._messages = []

        from src.core.config import ConfigLoader
        from src.orchestration.events import EventBroadcaster
        from src.orchestration.scan_manager import ScanManager
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(config=agent.config, broadcaster=agent.broadcaster, data_dir="data")

        # First call: Claude wants to use list_domains
        tool_response = _make_tool_use_response("list_domains", {"group": "quick"})
        # Second call: Claude responds with text
        text_response = _make_text_response("I found 2 domains in the quick group.")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[tool_response, text_response]
        )
        agent.client = mock_client

        result = await agent.run("List quick domains")
        assert "2 domains" in result
        # Verify two API calls were made
        assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self):
        """Agent stops after hitting max_iterations."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent._messages = []

        from src.core.config import ConfigLoader
        from src.orchestration.events import EventBroadcaster
        from src.orchestration.scan_manager import ScanManager
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(config=agent.config, broadcaster=agent.broadcaster, data_dir="data")

        # Always returns tool_use (infinite loop)
        tool_response = _make_tool_use_response("get_policy_stats", {})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=tool_response)
        agent.client = mock_client

        result = await agent.run("Test", max_iterations=3)
        assert "3 iteration limit" in result
        assert mock_client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_on_text_callback(self):
        """on_text callback receives Claude's text output."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent._messages = []

        from src.core.config import ConfigLoader
        from src.orchestration.events import EventBroadcaster
        from src.orchestration.scan_manager import ScanManager
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(config=agent.config, broadcaster=agent.broadcaster, data_dir="data")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_text_response("Hello, I can help you find policies.")
        )
        agent.client = mock_client

        text_received = []
        await agent.run("Hi", on_text=lambda t: text_received.append(t))

        assert len(text_received) == 1
        assert "find policies" in text_received[0]

    @pytest.mark.asyncio
    async def test_on_tool_call_callback(self):
        """on_tool_call callback fires when tools are called."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent._messages = []

        from src.core.config import ConfigLoader
        from src.orchestration.events import EventBroadcaster
        from src.orchestration.scan_manager import ScanManager
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(config=agent.config, broadcaster=agent.broadcaster, data_dir="data")

        tool_response = _make_tool_use_response("estimate_cost", {"domains": "quick"})
        text_response = _make_text_response("Estimated cost: $0.81")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[tool_response, text_response]
        )
        agent.client = mock_client

        tools_called = []
        await agent.run(
            "Estimate cost for quick scan",
            on_tool_call=lambda name, inp: tools_called.append(name),
        )

        assert tools_called == ["estimate_cost"]

    @pytest.mark.asyncio
    async def test_tool_error_handling(self):
        """Agent handles tool execution errors gracefully."""
        agent = PolicyAgent.__new__(PolicyAgent)
        agent.tools = []
        agent.system_prompt = "test"
        agent.model = "test-model"
        agent._messages = []

        from src.core.config import ConfigLoader
        from src.orchestration.events import EventBroadcaster
        from src.orchestration.scan_manager import ScanManager
        agent.config = ConfigLoader(config_dir="config")
        agent.config.load()
        agent.broadcaster = EventBroadcaster()
        agent.scan_manager = ScanManager(config=agent.config, broadcaster=agent.broadcaster, data_dir="data")

        # Claude calls a tool that will return an error
        tool_response = _make_tool_use_response("get_scan_status", {"scan_id": "nonexistent"})
        # Claude handles the error gracefully
        text_response = _make_text_response("That scan was not found.")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[tool_response, text_response]
        )
        agent.client = mock_client

        result = await agent.run("Check scan nonexistent")
        assert "not found" in result
