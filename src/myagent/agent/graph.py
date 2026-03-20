"""LangGraphステートマシン.

ReActパターンのエージェントを構築し、ツールバインドと最大ループ制御を行う。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from myagent.agent.events import AgentEvent
from myagent.agent.state import AgentState
from myagent.infra.errors import MyAgentError

if TYPE_CHECKING:
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
) -> StateGraph[AgentState]:
    """ReActエージェントのLangGraphステートマシンを構築する.

    Args:
        model: ツールバインド済みのLLMモデル。
        tools: 利用可能なツール一覧。
        max_loops: 最大ループ回数。

    Returns:
        コンパイル済みのStateGraph。
    """
    model_with_tools = model.bind_tools(tools)

    async def agent_node(state: AgentState) -> dict[str, Any]:
        """LLMを呼び出しツール使用を判断するノード."""
        messages = state.get("messages", [])
        loop_count = state.get("loop_count", 0)

        if loop_count >= max_loops:
            limit_msg = (
                f"最大ループ回数({max_loops})に達しました。"
                "現時点の結果をまとめます。"
            )
            return {
                "messages": messages + [AIMessage(content=limit_msg)],
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
        """ツールノードのラッパー。実行後にagentノードに戻す。"""
        result = tool_node.invoke(state)
        messages = state.get("messages", [])
        new_messages = result.get("messages", [])
        return {"messages": messages + new_messages}

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
    """

    def __init__(
        self,
        model: BaseChatModel,
        tools: list[BaseTool],
        max_loops: int = 20,
    ) -> None:
        self._graph = build_agent_graph(model, tools, max_loops)
        self._compiled = self._graph.compile()

    async def run(self, instruction: str) -> str:
        """指示を実行し、最終回答を返す.

        Args:
            instruction: ユーザーからの指示テキスト。

        Returns:
            エージェントの最終回答。

        Raises:
            MyAgentError: エージェント実行中にエラーが発生した場合。
        """
        initial_state: AgentState = {
            "messages": [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=instruction),
            ],
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

    async def run_with_events(
        self, instruction: str
    ) -> AsyncIterator[AgentEvent]:
        """指示を実行し、イベントをストリーミングで返す.

        Args:
            instruction: ユーザーからの指示テキスト。

        Yields:
            エージェントイベント。
        """
        initial_state: AgentState = {
            "messages": [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=instruction),
            ],
            "phase": "planning",
            "loop_count": 0,
            "is_completed": False,
        }

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

                elif kind == "on_tool_start":
                    name = event.get("name", "")
                    inputs: dict[str, Any] = event.get("data", {}).get("input", {})
                    yield AgentEvent.tool_start(name, inputs)

                elif kind == "on_tool_end":
                    name = event.get("name", "")
                    output = event.get("data", {}).get("output", "")
                    output_str = str(output) if not isinstance(output, str) else output
                    yield AgentEvent.tool_end(name, output_str)

        except Exception as e:
            yield AgentEvent.agent_error(str(e))
            return

        yield AgentEvent.agent_complete("実行完了")
