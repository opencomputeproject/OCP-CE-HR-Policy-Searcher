"""Tests for the reader Q&A agent (src/agent/ask.py).

The reader agent must be able to answer questions about STORED policies
only — it gets exactly two read-only tools and can never start a scan,
search the web, or otherwise spend real money.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.ask import (
    ASK_MAX_ITERATIONS,
    READER_TOOL_NAMES,
    reader_tools,
    answer_question,
)


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name, tool_input, block_id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def _response(blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


class TestReaderTools:
    def test_only_read_only_tools_exposed(self):
        names = {t["name"] for t in reader_tools()}
        assert names == set(READER_TOOL_NAMES)
        assert names == {"search_policies", "get_policy_stats"}

    def test_no_spending_tools(self):
        names = {t["name"] for t in reader_tools()}
        for forbidden in ("start_scan", "web_search", "add_domain", "analyze_url"):
            assert forbidden not in names


class TestAnswerQuestion:
    @pytest.mark.asyncio
    async def test_direct_answer_without_tools(self):
        client = MagicMock()
        client.messages.create = AsyncMock(
            return_value=_response([_text_block("No policies stored yet.")])
        )
        result = await answer_question(
            "Any policies in Peru?",
            client=client,
            model="test-model",
            config=MagicMock(),
            scan_manager=MagicMock(),
        )
        assert result["answer"] == "No policies stored yet."
        assert result["tool_calls"] == 0

    @pytest.mark.asyncio
    async def test_tool_loop_then_answer(self):
        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=[
            _response(
                [
                    _text_block("Let me search for that..."),
                    _tool_use_block("search_policies", {"jurisdiction": "Germany"}),
                ],
                stop_reason="tool_use",
            ),
            _response([_text_block("Germany has the EnEfG heat reuse mandate.")]),
        ])
        with patch(
            "src.agent.ask.execute_tool",
            new=AsyncMock(return_value={"policies": [], "count": 0}),
        ) as mock_exec:
            result = await answer_question(
                "What does Germany require?",
                client=client,
                model="test-model",
                config=MagicMock(),
                scan_manager=MagicMock(),
            )
        assert "EnEfG" in result["answer"]
        # Intermediate "let me search" narration must not reach the reader
        assert "Let me search" not in result["answer"]
        assert result["tool_calls"] == 1
        mock_exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disallowed_tool_is_refused_not_executed(self):
        """If the model somehow requests a non-reader tool, it must not run."""
        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=[
            _response(
                [_tool_use_block("start_scan", {"domains": "germany"})],
                stop_reason="tool_use",
            ),
            _response([_text_block("Sorry, I can only read stored policies.")]),
        ])
        with patch("src.agent.ask.execute_tool", new=AsyncMock()) as mock_exec:
            result = await answer_question(
                "Scan Germany now",
                client=client,
                model="test-model",
                config=MagicMock(),
                scan_manager=MagicMock(),
            )
        mock_exec.assert_not_awaited()
        assert result["answer"]

    @pytest.mark.asyncio
    async def test_iteration_cap(self):
        """A model that never stops calling tools gets cut off."""
        client = MagicMock()
        client.messages.create = AsyncMock(
            return_value=_response(
                [_tool_use_block("get_policy_stats", {})], stop_reason="tool_use",
            )
        )
        with patch(
            "src.agent.ask.execute_tool",
            new=AsyncMock(return_value={"total": 0}),
        ):
            result = await answer_question(
                "stats please",
                client=client,
                model="test-model",
                config=MagicMock(),
                scan_manager=MagicMock(),
            )
        assert client.messages.create.await_count == ASK_MAX_ITERATIONS
        assert result["tool_calls"] == ASK_MAX_ITERATIONS
