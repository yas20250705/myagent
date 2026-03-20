"""LangGraphエージェントグラフのテスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from myagent.agent.executor import Executor
from myagent.agent.graph import AgentRunner, _truncate_messages, build_agent_graph
from myagent.agent.state import AgentState
from myagent.infra.context import ContextManager
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

    def test_初期履歴は空である(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        assert runner._history == []

    def test_clear_historyで履歴がリセットされる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        runner._history = [SystemMessage(content="test")]
        runner.clear_history()
        assert runner._history == []


class TestAgentRunnerの履歴管理:
    """AgentRunner のマルチターン履歴テスト."""

    @pytest.mark.asyncio
    async def test_runで履歴が更新される(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        final_msgs = [
            SystemMessage(content="sys"),
            HumanMessage(content="1回目"),
            AIMessage(content="1回目の回答"),
        ]
        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(
            return_value={"messages": final_msgs, "is_completed": True}
        )

        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        runner._compiled = mock_compiled

        await runner.run("1回目")
        assert len(runner._history) == 3
        assert runner._history[-1].content == "1回目の回答"

    @pytest.mark.asyncio
    async def test_2回目のrunで履歴が引き継がれる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        # 1回目の結果
        msgs_turn1 = [
            SystemMessage(content="sys"),
            HumanMessage(content="1回目"),
            AIMessage(content="1回目の回答"),
        ]
        # 2回目の結果（1回目の履歴 + 新メッセージ）
        msgs_turn2 = [
            SystemMessage(content="sys"),
            HumanMessage(content="1回目"),
            AIMessage(content="1回目の回答"),
            HumanMessage(content="2回目"),
            AIMessage(content="2回目の回答"),
        ]
        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(
            side_effect=[
                {"messages": msgs_turn1, "is_completed": True},
                {"messages": msgs_turn2, "is_completed": True},
            ]
        )

        runner = AgentRunner(model=mock_model, tools=[], max_loops=5)
        runner._compiled = mock_compiled

        await runner.run("1回目")
        # 2回目のinvoke引数に1回目の履歴が含まれるか確認
        await runner.run("2回目")
        call_args = mock_compiled.ainvoke.call_args_list[1][0][0]
        messages_sent = call_args["messages"]
        # 先頭3件は1回目の履歴
        assert messages_sent[0].content == "sys"
        assert messages_sent[2].content == "1回目の回答"
        # 末尾が2回目の指示
        assert messages_sent[-1].content == "2回目"


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


class Test_truncate_messages:
    """_truncate_messages 関数のテスト."""

    def test_空リストはそのまま返す(self) -> None:
        result = _truncate_messages([])
        assert result == []

    def test_通常メッセージはそのまま返す(self) -> None:
        msgs = [
            SystemMessage(content="sys"),
            HumanMessage(content="hello"),
        ]
        result = _truncate_messages(msgs)
        assert len(result) == 2

    def test_最大件数を超えた場合に切り詰める(self) -> None:
        # SystemMessage + HumanMessage を固定枠として保持し、それ以降を20件に制限
        fixed = [
            SystemMessage(content="sys"),
            HumanMessage(content="first"),
        ]
        extra = [AIMessage(content=f"msg{i}") for i in range(25)]
        msgs = fixed + extra

        result = _truncate_messages(msgs)
        # fixed 2件 + 直近20件 = 22件
        assert len(result) == 22
        # fixed が保持されている
        assert result[0].content == "sys"
        assert result[1].content == "first"
        # 直近のメッセージが含まれている
        assert result[-1].content == "msg24"

    def test_長いコンテンツは切り詰める(self) -> None:
        long_content = "a" * 10000
        msgs = [AIMessage(content=long_content)]
        result = _truncate_messages(msgs)
        assert len(result[0].content) < 10000  # type: ignore[arg-type]
        assert "省略" in str(result[0].content)

    def test_SystemMessageは固定枠として保持される(self) -> None:
        sys_msg = SystemMessage(content="sys")
        extra = [AIMessage(content=f"msg{i}") for i in range(25)]
        msgs = [sys_msg] + extra

        result = _truncate_messages(msgs)
        # sys + 直近20件 = 21件
        assert len(result) == 21
        assert result[0].content == "sys"


class TestAgentRunnerの確認フロー:
    """AgentRunner の確認フロー（Executor + confirm_callback）テスト."""

    def test_executorとconfirm_callbackで初期化できる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        executor = Executor(confirmation_level="normal")
        callback = MagicMock(return_value=True)
        runner = AgentRunner(
            model=mock_model,
            tools=[],
            max_loops=5,
            executor=executor,
            confirm_callback=callback,
        )
        assert runner is not None

    def test_確認承認時にAgentRunnerを構築できる(self) -> None:
        """confirm_callback で AgentRunner が正常に構築される."""
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        executor = Executor(confirmation_level="normal")
        callback_calls: list[str] = []

        def callback(tool_name: str, tool_input: dict) -> bool:
            callback_calls.append(tool_name)
            return True

        runner = AgentRunner(
            model=mock_model,
            tools=[],
            max_loops=5,
            executor=executor,
            confirm_callback=callback,
        )
        assert runner is not None

    @pytest.mark.asyncio
    async def test_autonomous_levelでcallbackが呼ばれない(self) -> None:
        """autonomous レベルでは should_confirm が False を返す."""
        executor = Executor(confirmation_level="autonomous")
        called = False

        def callback(tool_name: str, tool_input: dict) -> bool:
            nonlocal called
            called = True
            return True

        assert not executor.should_confirm("write_file", {"file_path": "x"})
        assert not called  # callback は呼ばれていない

    def test_normalレベルでwrite_fileは確認が必要(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert executor.should_confirm("write_file", {}) is True

    def test_normalレベルでread_fileは確認不要(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert executor.should_confirm("read_file", {}) is False

    def test_strictレベルで書き込みツールは確認が必要(self) -> None:
        executor = Executor(confirmation_level="strict")
        assert executor.should_confirm("write_file", {}) is True

    def test_strictレベルでread_fileは確認不要(self) -> None:
        executor = Executor(confirmation_level="strict")
        assert executor.should_confirm("read_file", {}) is False

    @pytest.mark.asyncio
    async def test_拒否時に否定ToolMessageが注入される(self) -> None:
        """confirm_callback が False を返すと ToolMessage(拒否) が注入される."""
        from unittest.mock import patch

        mock_model = MagicMock()
        bound_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=bound_model)
        # agent_node が tool_calls を持つ AIMessage を返したあと
        # 2回目呼び出しでは最終回答を返す
        bound_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {"file_path": "out.txt", "content": "hello"},
                            "id": "tc-deny",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="了解しました"),
            ]
        )

        executor = Executor(confirmation_level="normal")
        # 常に拒否
        deny_callback = MagicMock(return_value=False)

        with patch("myagent.agent.graph.ToolNode") as mock_tn_cls:
            mock_tn = MagicMock()
            # ToolNode.invoke は呼ばれないはず（全て拒否）
            mock_tn.invoke = MagicMock(return_value={"messages": []})
            mock_tn_cls.return_value = mock_tn

            runner = AgentRunner(
                model=mock_model,
                tools=[],
                max_loops=10,
                executor=executor,
                confirm_callback=deny_callback,
            )
            result = await runner.run("ファイルを書いて")

        # callback が write_file で呼ばれた
        deny_callback.assert_called_once_with(
            "write_file", {"file_path": "out.txt", "content": "hello"}
        )
        # ToolNode.invoke は呼ばれなかった（全 tool_call が拒否）
        mock_tn.invoke.assert_not_called()
        # 最終回答が返る
        assert result == "了解しました"

    @pytest.mark.asyncio
    async def test_confirm_callback_noneの場合は自動承認(self) -> None:
        """executor が should_confirm=True でも confirm_callback=None なら自動承認."""
        from unittest.mock import patch

        mock_model = MagicMock()
        bound_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=bound_model)
        bound_model.ainvoke = AsyncMock(
            side_effect=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {"file_path": "x.txt", "content": "x"},
                            "id": "tc-auto",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="完了"),
            ]
        )

        executor = Executor(confirmation_level="normal")

        with patch("myagent.agent.graph.ToolNode") as mock_tn_cls:
            mock_tn = MagicMock()
            from langchain_core.messages import ToolMessage

            mock_tn.invoke = MagicMock(
                return_value={
                    "messages": [
                        ToolMessage(
                            content="ok", tool_call_id="tc-auto", name="write_file"
                        )
                    ]
                }
            )
            mock_tn_cls.return_value = mock_tn

            runner = AgentRunner(
                model=mock_model,
                tools=[],
                max_loops=10,
                executor=executor,
                confirm_callback=None,  # callback なし
            )
            result = await runner.run("書いて")

        # confirm_callback=None なので自動承認 → ToolNode.invoke が呼ばれた
        mock_tn.invoke.assert_called_once()
        assert result == "完了"


class TestAgentNodeの内部ロジック:
    """コンパイル済みグラフを通じて agent_node の内部ロジックをテスト."""

    @pytest.mark.asyncio
    async def test_最大ループ回数到達時にis_completedがTrueになる(self) -> None:
        mock_model = MagicMock()
        bound_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=bound_model)

        # ainvoke が呼ばれることはないはずだが念のためモック
        bound_model.ainvoke = AsyncMock(return_value=AIMessage(content=""))

        graph = build_agent_graph(mock_model, [], max_loops=3)
        compiled = graph.compile()

        initial_state: AgentState = {
            "messages": [
                SystemMessage(content="sys"),
                HumanMessage(content="test"),
            ],
            "phase": "planning",
            "loop_count": 3,  # max_loops に到達済み
            "is_completed": False,
        }

        result = await compiled.ainvoke(initial_state)  # type: ignore[arg-type]

        assert result.get("is_completed") is True
        messages = result.get("messages", [])
        last_content = messages[-1].content if messages else ""
        assert "最大ループ回数" in str(last_content)

    @pytest.mark.asyncio
    async def test_同一ツール連続呼び出しでループ検知しis_completedがTrueになる(
        self,
    ) -> None:
        mock_model = MagicMock()
        bound_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=bound_model)
        bound_model.ainvoke = AsyncMock(return_value=AIMessage(content=""))

        graph = build_agent_graph(mock_model, [], max_loops=10)
        compiled = graph.compile()

        # 同一ツール呼び出しを2回持つメッセージ履歴
        repeated_tool_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "foo.py"},
                    "id": "tc1",
                    "type": "tool_call",
                }
            ],
        )
        repeated_tool_msg2 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "foo.py"},
                    "id": "tc2",
                    "type": "tool_call",
                }
            ],
        )

        initial_state: AgentState = {
            "messages": [
                SystemMessage(content="sys"),
                HumanMessage(content="test"),
                repeated_tool_msg,
                repeated_tool_msg2,
            ],
            "phase": "executing",
            "loop_count": 2,
            "is_completed": False,
        }

        result = await compiled.ainvoke(initial_state)  # type: ignore[arg-type]

        assert result.get("is_completed") is True
        messages = result.get("messages", [])
        last_content = messages[-1].content if messages else ""
        assert "繰り返し" in str(last_content) or "中断" in str(last_content)


class TestAgentRunnerのContextManager統合:
    """AgentRunner と ContextManager の統合テスト."""

    def test_context_managerを設定できる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        cm = ContextManager()
        runner = AgentRunner(model=mock_model, tools=[], context_manager=cm)
        assert runner._context_manager is cm

    def test_context_managerなしで初期化できる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        runner = AgentRunner(model=mock_model, tools=[])
        assert runner._context_manager is None

    def test_project_indexがSystemMessageに注入される(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        cm = ContextManager()
        cm._project_index = "myproject/\n├── main.py"
        runner = AgentRunner(model=mock_model, tools=[], context_manager=cm)

        messages = runner._build_initial_messages("テスト指示")
        assert isinstance(messages[0], SystemMessage)
        assert "プロジェクト構造" in messages[0].content
        assert "myproject/" in messages[0].content

    def test_project_indexがなければSystemMessageは変更なし(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        cm = ContextManager()
        # project_index は None
        runner = AgentRunner(model=mock_model, tools=[], context_manager=cm)

        messages = runner._build_initial_messages("テスト指示")
        assert isinstance(messages[0], SystemMessage)
        assert "プロジェクト構造" not in messages[0].content

    def test_context_managerなしでもproject_index注入なし(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        runner = AgentRunner(model=mock_model, tools=[])

        messages = runner._build_initial_messages("テスト指示")
        assert isinstance(messages[0], SystemMessage)
        assert "プロジェクト構造" not in messages[0].content

    @pytest.mark.asyncio
    async def test_圧縮不要なら履歴が変わらない(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        cm = ContextManager(max_context_tokens=128_000)
        runner = AgentRunner(model=mock_model, tools=[], context_manager=cm)
        runner._history = [
            SystemMessage(content="sys"),
            HumanMessage(content="hello"),
        ]
        original_history = list(runner._history)
        await runner._maybe_compress_history()
        assert runner._history == original_history

    @pytest.mark.asyncio
    async def test_圧縮が必要なときにcompress_messagesが呼ばれる(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        cm = MagicMock(spec=ContextManager)
        cm.needs_compression = MagicMock(return_value=True)
        compressed = [SystemMessage(content="sys"), HumanMessage(content="compressed")]
        cm.compress_messages = AsyncMock(return_value=compressed)

        runner = AgentRunner(model=mock_model, tools=[], context_manager=cm)
        runner._history = [
            SystemMessage(content="sys"),
            HumanMessage(content="q1"),
            AIMessage(content="a1"),
            HumanMessage(content="q2"),
        ]
        await runner._maybe_compress_history()

        cm.compress_messages.assert_called_once()
        assert runner._history == compressed

    @pytest.mark.asyncio
    async def test_履歴が空なら圧縮は実行されない(self) -> None:
        mock_model = MagicMock()
        mock_model.bind_tools = MagicMock(return_value=mock_model)
        cm = MagicMock(spec=ContextManager)
        cm.needs_compression = MagicMock(return_value=True)
        cm.compress_messages = AsyncMock()

        runner = AgentRunner(model=mock_model, tools=[], context_manager=cm)
        runner._history = []

        await runner._maybe_compress_history()
        cm.compress_messages.assert_not_called()
