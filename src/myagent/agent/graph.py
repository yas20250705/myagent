"""LangGraphステートマシン.

ReActパターンのエージェントを構築し、ツールバインドと最大ループ制御を行う。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from myagent.agent.critic import Critic
from myagent.agent.events import AgentEvent
from myagent.agent.executor import Executor
from myagent.agent.state import AgentState
from myagent.infra.context import ContextManager
from myagent.infra.errors import MyAgentError

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool

_MAX_RECENT_MESSAGES = 20
_MAX_CONTENT_CHARS = 8000


def _truncate_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """トークン制限に対応するためメッセージ履歴を切り詰める.

    SystemMessage と最初の HumanMessage は常に保持し、
    それ以降は直近 _MAX_RECENT_MESSAGES 件に絞る。
    各メッセージのコンテンツが長すぎる場合も切り詰める。
    """

    def _trim_content(msg: BaseMessage) -> BaseMessage:
        if isinstance(msg.content, str) and len(msg.content) > _MAX_CONTENT_CHARS:
            trimmed = msg.content[:_MAX_CONTENT_CHARS] + "\n...(省略)..."
            return msg.model_copy(update={"content": trimmed})
        return msg

    if not messages:
        return messages

    # 先頭の SystemMessage / HumanMessage を固定枠として保持
    fixed: list[BaseMessage] = []
    rest_start = 0
    for i, msg in enumerate(messages[:2]):
        if isinstance(msg, (SystemMessage, HumanMessage)):
            fixed.append(_trim_content(msg))
            rest_start = i + 1
        else:
            break

    rest = [_trim_content(m) for m in messages[rest_start:]]
    if len(rest) > _MAX_RECENT_MESSAGES:
        rest = rest[-_MAX_RECENT_MESSAGES:]

    return fixed + rest


SYSTEM_PROMPT = """あなたは高度なAIコーディングアシスタントです。
ユーザーの指示に従い、利用可能なツールを使って作業を完了してください。

ツールを使う必要がある場合はツールを呼び出し、結果を確認してから次のステップに進んでください。
すべての作業が完了したら、最終的な回答をテキストで返してください。"""


def build_agent_graph(
    model: BaseChatModel,
    tools: list[BaseTool],
    max_loops: int = 20,
    executor: Executor | None = None,
    confirm_callback: Callable[[str, dict[str, Any]], bool] | None = None,
) -> StateGraph[AgentState]:
    """ReActエージェントのLangGraphステートマシンを構築する.

    Args:
        model: ツールバインド済みのLLMモデル。
        tools: 利用可能なツール一覧。
        max_loops: 最大ループ回数。
        executor: ツール確認フローを管理するExecutor。Noneの場合は確認なし。
        confirm_callback: ユーザー確認を求めるコールバック。承認でTrue、拒否でFalse。

    Returns:
        コンパイル済みのStateGraph。
    """
    model_with_tools = model.bind_tools(tools)
    critic = Critic()

    async def agent_node(state: AgentState) -> dict[str, Any]:
        """LLMを呼び出しツール使用を判断するノード."""
        messages = state.get("messages", [])
        loop_count = state.get("loop_count", 0)

        if loop_count >= max_loops:
            limit_msg = (
                f"最大ループ回数({max_loops})に達しました。現時点の結果をまとめます。"
            )
            return {
                "messages": messages + [AIMessage(content=limit_msg)],
                "loop_count": loop_count,
                "is_completed": True,
            }

        if critic.detect_loop(messages):
            loop_msg = "同一ツール呼び出しの繰り返しを検知しました。処理を中断します。"
            return {
                "messages": messages + [AIMessage(content=loop_msg)],
                "loop_count": loop_count,
                "is_completed": True,
            }

        response = await model_with_tools.ainvoke(_truncate_messages(messages))

        return {
            "messages": messages + [response],
            "loop_count": loop_count + 1,
        }

    def should_continue(state: AgentState) -> str:
        """ツール呼び出しが必要か判定するルーティング関数."""
        if state.get("is_completed", False):
            return END

        messages = state.get("messages", [])
        if not messages:
            return END

        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    tool_node = ToolNode(tools)

    def tool_node_wrapper(state: AgentState) -> dict[str, Any]:
        """ツールノードのラッパー。確認フローを経てツールを実行する。"""
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        tool_calls = getattr(last_message, "tool_calls", []) if last_message else []

        denied_messages: list[ToolMessage] = []
        approved_calls: list[dict[str, Any]] = []

        for tc in tool_calls:
            tool_name: str = tc["name"]
            tool_args: dict[str, Any] = tc["args"]
            tool_call_id: str = tc["id"]

            needs_confirm = executor is not None and executor.should_confirm(
                tool_name, tool_args
            )
            if needs_confirm:
                cb = confirm_callback
                approved = cb(tool_name, tool_args) if cb else True
                if not approved:
                    denied_messages.append(
                        ToolMessage(
                            content="ユーザーがこの操作を拒否しました。",
                            tool_call_id=tool_call_id,
                            name=tool_name,
                        )
                    )
                    continue

            approved_calls.append(tc)

        if approved_calls and last_message is not None:
            modified_last = last_message.model_copy(
                update={"tool_calls": approved_calls}
            )
            modified_state = {**state, "messages": messages[:-1] + [modified_last]}
            result = tool_node.invoke(modified_state)
            new_messages: list[BaseMessage] = result.get("messages", [])
        else:
            new_messages = []

        return {"messages": messages + denied_messages + new_messages}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node_wrapper)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph


class AgentRunner:
    """エージェントの実行を管理するランナー.

    グラフの構築・実行とイベント発行を担当する。
    ターン間のメッセージ履歴を保持し、マルチターン会話を実現する。
    """

    def __init__(
        self,
        model: BaseChatModel,
        tools: list[BaseTool],
        max_loops: int = 20,
        executor: Executor | None = None,
        confirm_callback: Callable[[str, dict[str, Any]], bool] | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        self._model = model
        self._context_manager = context_manager
        self._graph = build_agent_graph(
            model, tools, max_loops, executor, confirm_callback
        )
        self._compiled = self._graph.compile()
        # ターン間で引き継ぐメッセージ履歴（SystemMessage + 会話全体）
        self._history: list[BaseMessage] = []

    def clear_history(self) -> None:
        """会話履歴をリセットする."""
        self._history = []

    def _build_initial_messages(self, instruction: str) -> list[BaseMessage]:
        """履歴に新しいユーザー指示を加えた初期メッセージリストを生成する.

        初回ターンの場合、project_index が設定されていれば SystemMessage に注入する。
        """
        if self._history:
            return list(self._history) + [HumanMessage(content=instruction)]
        # 初回ターン: project_index があれば SystemMessage に注入
        system_content = SYSTEM_PROMPT
        if (
            self._context_manager is not None
            and self._context_manager.project_index is not None
        ):
            system_content = (
                SYSTEM_PROMPT
                + "\n\n## プロジェクト構造\n\n"
                + self._context_manager.project_index
            )
        return [
            SystemMessage(content=system_content),
            HumanMessage(content=instruction),
        ]

    def _update_history(self, final_messages: list[BaseMessage]) -> None:
        """実行結果のメッセージ履歴を保存する."""
        if final_messages:
            self._history = list(final_messages)

    async def _maybe_compress_history(self) -> None:
        """必要に応じて会話履歴をコンテキスト圧縮する.

        ContextManager が設定されており、履歴が圧縮閾値を超えている場合に
        LLM を使って古い会話を要約・圧縮する。
        """
        if (
            self._context_manager is None
            or not self._history
            or not self._context_manager.needs_compression(self._history)
        ):
            return

        compressed = await self._context_manager.compress_messages(
            self._history, self._model
        )
        self._history = compressed

    async def run(self, instruction: str) -> str:
        """指示を実行し、最終回答を返す.

        Args:
            instruction: ユーザーからの指示テキスト。

        Returns:
            エージェントの最終回答。

        Raises:
            MyAgentError: エージェント実行中にエラーが発生した場合。
        """
        await self._maybe_compress_history()

        initial_state: AgentState = {
            "messages": self._build_initial_messages(instruction),
            "phase": "planning",
            "loop_count": 0,
            "is_completed": False,
        }

        try:
            result = await self._compiled.ainvoke(initial_state)  # type: ignore[arg-type]
        except Exception as e:
            msg = f"エージェント実行中にエラーが発生しました: {e}"
            raise MyAgentError(msg) from e

        messages = result.get("messages", [])
        self._update_history(messages)

        if messages:
            last = messages[-1]
            if hasattr(last, "content"):
                content = last.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # Gemini形式: [{'type': 'text', 'text': '...'}]
                    texts = [
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    return "".join(texts) or "(回答なし)"
        return "(回答なし)"

    async def run_with_events(self, instruction: str) -> AsyncIterator[AgentEvent]:
        """指示を実行し、イベントをストリーミングで返す.

        Args:
            instruction: ユーザーからの指示テキスト。

        Yields:
            エージェントイベント。
        """
        await self._maybe_compress_history()

        initial_state: AgentState = {
            "messages": self._build_initial_messages(instruction),
            "phase": "planning",
            "loop_count": 0,
            "is_completed": False,
        }

        _prompt_tokens = 0
        _completion_tokens = 0
        _model_name = ""
        _final_messages: list[BaseMessage] = []

        try:
            async for event in self._compiled.astream_events(
                initial_state, version="v2"
            ):
                kind = event.get("event", "")

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        content = chunk.content
                        if isinstance(content, str) and content:
                            # OpenAI形式: content は文字列
                            yield AgentEvent.stream_token(content)
                        elif isinstance(content, list):
                            # Gemini形式: [{'type': 'text', 'text': '...'}]
                            for part in content:
                                is_text = (
                                    isinstance(part, dict)
                                    and part.get("type") == "text"
                                )
                                if is_text:
                                    text = part.get("text", "")
                                    if text:
                                        yield AgentEvent.stream_token(text)

                elif kind == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    if output and hasattr(output, "usage_metadata"):
                        usage = output.usage_metadata
                        if isinstance(usage, dict):
                            _prompt_tokens += usage.get("input_tokens", 0)
                            _completion_tokens += usage.get("output_tokens", 0)
                    if not _model_name:
                        _model_name = event.get("metadata", {}).get(
                            "ls_model_name", ""
                        ) or event.get("name", "")

                elif kind == "on_tool_start":
                    name = event.get("name", "")
                    inputs: dict[str, Any] = event.get("data", {}).get("input", {})
                    yield AgentEvent.tool_start(name, inputs)

                elif kind == "on_tool_end":
                    name = event.get("name", "")
                    output = event.get("data", {}).get("output", "")
                    output_str = str(output) if not isinstance(output, str) else output
                    yield AgentEvent.tool_end(name, output_str)

                elif kind == "on_chain_end":
                    # name == "LangGraph" がトップレベルグラフの完了イベント
                    # ノード単位の on_chain_end（name == "agent" 等）は除外
                    if event.get("name") == "LangGraph":
                        output = event.get("data", {}).get("output", {})
                        if isinstance(output, dict):
                            msgs = output.get("messages", [])
                            if msgs:
                                _final_messages = msgs

        except Exception as e:
            yield AgentEvent.agent_error(str(e))
            return

        self._update_history(_final_messages)

        yield AgentEvent.agent_complete(
            "実行完了",
            prompt_tokens=_prompt_tokens,
            completion_tokens=_completion_tokens,
            model_name=_model_name,
        )
