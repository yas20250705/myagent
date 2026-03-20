"""LangGraphエージェントグラフのテスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myagent.agent.graph import AgentRunner, build_agent_graph
from myagent.agent.state import AgentState
from myagent.infra.errors import MyAgentError


class Testbuild_agent_graph:
    """build_agent_graph 関数のテスト."""

    def test_グラフを構築できる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        tools: list[object] = []
        graph = build_agent_graph(mock_model, tools, max_loops=5)
        assert graph is not None

    def test_コンパイルできる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        graph = build_agent_graph(mock_model, [], max_loops=5)
        compiled = graph.compile()
        assert compiled is not None


class TestAgentRunnerの初期化:
    """AgentRunner の初期化テスト."""

    def test_モデルとツールで初期化できる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        assert runner is not None


class TestAgentRunnerのrun:
    """AgentRunner.run のテスト."""

    @pytest.mark.asyncio
    async def test_指示を実行して文字列を返す(self) -> None:
        from langchain_core.messages import AIMessage

        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        # LangGraph グラフの ainvoke をモック
        final_state: AgentState = {
            "messages": [AIMessage(content="テスト完了しました")],
            "phase": "completed",
            "is_completed": True,
        }

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value=final_state)

        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        runner._compiled = mock_compiled

        result = await runner.run("テストを実行して")
        assert "テスト完了しました" == result

    @pytest.mark.asyncio
    async def test_メッセージがない場合に回答なしを返す(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value={"messages": []})

        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        runner._compiled = mock_compiled

        result = await runner.run("テスト")
        assert result == "(回答なし)"

    @pytest.mark.asyncio
    async def test_エラー時にMyAgentErrorが発生する(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(side_effect=Exception("グラフエラー"))

        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        runner._compiled = mock_compiled

        with pytest.raises(MyAgentError):
            await runner.run("エラーを起こして")


class TestAgentRunnerのrun_with_events:
    """AgentRunner.run_with_events のテスト."""

    @pytest.mark.asyncio
    async def test_イベントを生成できる(self) -> None:
        from myagent.agent.events import AgentEvent

        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        # astream_events のモック
        async def mock_astream_events(*args, **kwargs):  # type: ignore[no-untyped-def]
            yield {"event": "on_chat_model_stream", "data": {}}  # chunkなし

        mock_compiled = MagicMock()
        mock_compiled.astream_events = mock_astream_events

        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        runner._compiled = mock_compiled

        events: list[AgentEvent] = []
        async for event in runner.run_with_events("テスト"):
            events.append(event)

        # 最後にagent_completeイベントが来る
        assert events[-1].event_type == "agent_complete"

    @pytest.mark.asyncio
    async def test_エラー時にagent_errorイベントが来る(self) -> None:
        from myagent.agent.events import AgentEvent

        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        async def failing_astream_events(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise Exception("ストリームエラー")
            yield  # generator化

        mock_compiled = MagicMock()
        mock_compiled.astream_events = failing_astream_events

        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        runner._compiled = mock_compiled

        events: list[AgentEvent] = []
        async for event in runner.run_with_events("テスト"):
            events.append(event)

        assert events[0].event_type == "agent_error"
