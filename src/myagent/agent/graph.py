"""LangGraphステートマシン.

ReActパターンのエージェントを構築し、ツールバインドと最大ループ制御を行う。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from myagent.agent.critic import Critic
from myagent.agent.events import AgentEvent
from myagent.agent.executor import Executor
from myagent.agent.metrics import SessionMetrics
from myagent.agent.prompt_manager import PromptManager
from myagent.agent.state import AgentState
from myagent.agent.tool_validator import ToolValidator
from myagent.infra.context import ContextManager
from myagent.infra.errors import MyAgentError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool

    from myagent.tools.registry import ToolRegistry

_MAX_RECENT_MESSAGES = 30
_MAX_CONTENT_CHARS = 12000

# ファイルパスを持つ書き込みツール（競合検出対象）
_FILE_WRITE_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file"})


def _detect_file_conflicts(
    tool_calls: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """並列実行するtool_calls間のファイル書き込み競合を検出する.

    書き込みツール（write_file, edit_file）が同一ファイルに対して
    複数呼び出される場合、それらを競合グループとして分離する。
    読み取り専用ツールは競合対象外。

    Args:
        tool_calls: LLMが返したtool_callsのリスト。

    Returns:
        (non_conflict_calls, conflict_groups) のタプル。
        - non_conflict_calls: 競合なしで並列実行可能なtool_calls
        - conflict_groups: 同一ファイルへの書き込みが競合する
          tool_callsのグループリスト。各グループは逐次実行が必要。
    """
    # 書き込みツールのfile_pathごとにtool_callsをグループ化
    file_to_calls: dict[str, list[dict[str, Any]]] = {}
    non_write_calls: list[dict[str, Any]] = []

    for tc in tool_calls:
        tool_name: str = tc.get("name", "")
        tool_args: dict[str, Any] = tc.get("args", {})

        if tool_name in _FILE_WRITE_TOOLS:
            file_path = tool_args.get("file_path", "")
            if file_path:
                file_to_calls.setdefault(file_path, []).append(tc)
            else:
                non_write_calls.append(tc)
        else:
            non_write_calls.append(tc)

    # 競合判定: 同一ファイルに2つ以上の書き込みがあるか
    non_conflict_calls = list(non_write_calls)
    conflict_groups: list[list[dict[str, Any]]] = []

    for _file_path, calls in file_to_calls.items():
        if len(calls) == 1:
            non_conflict_calls.append(calls[0])
        else:
            conflict_groups.append(calls)

    return non_conflict_calls, conflict_groups


def _remove_orphaned_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """対応するtool_callsを持たないToolMessageを除去する.

    メッセージ切り詰め後にAIMessage(tool_calls)が失われ、
    ToolMessageだけが残る「孤立ToolMessage」を除去する。
    OpenAI APIはtool_callsのないToolMessageをエラーとするため必須。
    """
    available_ids: set[str] = set()
    result: list[BaseMessage] = []

    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tc_id = tc.get("id")
                if tc_id is not None:
                    available_ids.add(tc_id)
            result.append(msg)
        elif isinstance(msg, ToolMessage):
            if msg.tool_call_id in available_ids:
                available_ids.discard(msg.tool_call_id)
                result.append(msg)
            # else: 孤立ToolMessage → スキップ
        else:
            result.append(msg)

    return result


def _truncate_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """トークン制限に対応するためメッセージ履歴を切り詰める.

    SystemMessage と最初の HumanMessage は常に保持し、
    それ以降は直近 _MAX_RECENT_MESSAGES 件に絞る。
    各メッセージのコンテンツが長すぎる場合も切り詰める。
    切り詰め後に孤立した ToolMessage を除去してAPIエラーを防ぐ。
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

    # 切り詰めにより孤立したToolMessageを除去
    rest = _remove_orphaned_tool_messages(rest)

    return fixed + rest


# 後方互換性のために残す（テスト等で直接参照されている場合）
SYSTEM_PROMPT = PromptManager().build_prompt()


def build_agent_graph(
    model: BaseChatModel,
    tools: list[BaseTool],
    max_loops: int = 20,
    executor: Executor | None = None,
    confirm_callback: Callable[[str, dict[str, Any]], bool] | None = None,
    batch_confirm_callback: (
        Callable[[list[tuple[str, dict[str, Any]]]], list[bool]] | None
    ) = None,
    tool_validator: ToolValidator | None = None,
    metrics: SessionMetrics | None = None,
    max_recovery_attempts: int = 2,
) -> StateGraph[AgentState]:
    """ReActエージェントのLangGraphステートマシンを構築する.

    Args:
        model: ツールバインド済みのLLMモデル。
        tools: 利用可能なツール一覧。
        max_loops: 最大ループ回数。
        executor: ツール確認フローを管理するExecutor。Noneの場合は確認なし。
        confirm_callback: ユーザー確認を求めるコールバック。承認でTrue、拒否でFalse。
        batch_confirm_callback: 複数ツール呼び出しの一括確認
            コールバック。各tool_callの(name, args)リストを受け取り、
            各要素の承認/拒否をboolリストで返す。
            Noneの場合はconfirm_callbackで逐次確認。
            確認対象が1件のみの場合もconfirm_callbackで逐次確認。
        tool_validator: ツールパラメータバリデーター。Noneの場合はバリデーションなし。
        metrics: セッションメトリクス。Noneの場合はメトリクス収集なし。

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

        # needs_recovery フラグは返却時に常に False にリセット
        recovery_count = state.get("recovery_count", 0)
        failed_approaches = list(state.get("failed_approaches", []))

        if critic.detect_loop(messages):
            if recovery_count < max_recovery_attempts:
                detail = "同一ツール呼び出しが連続しています"
                recovery_msg = critic.build_recovery_message(
                    "loop", detail, failed_approaches or None
                )
                failed_approaches.append(
                    "同一ツール呼び出しの繰り返し"
                    f"（{recovery_count + 1}回目の回復試行）"
                )
                logger.info(
                    "回復誘導 #%d: loop - %s",
                    recovery_count + 1,
                    detail,
                )
                if metrics is not None:
                    metrics.record_recovery_attempt()
                return {
                    "messages": messages + [
                        AIMessage(content=f"⚠️ パターン検知: {detail}"),
                        HumanMessage(content=recovery_msg),
                    ],
                    "loop_count": loop_count,
                    "recovery_count": recovery_count + 1,
                    "failed_approaches": failed_approaches,
                    "needs_recovery": True,
                }
            loop_msg = (
                "同一ツール呼び出しの繰り返しを検知しました。"
                f"回復試行が上限({max_recovery_attempts}回)に達したため、処理を中断します。"
            )
            return {
                "messages": messages + [AIMessage(content=loop_msg)],
                "loop_count": loop_count,
                "is_completed": True,
            }

        # エラー繰り返し検知
        error_detected, error_msg = critic.detect_error_repetition(messages)
        if error_detected:
            if recovery_count < max_recovery_attempts:
                recovery_msg = critic.build_recovery_message(
                    "error_repetition", error_msg, failed_approaches or None
                )
                failed_approaches.append(
                    f"同一エラーの繰り返し: {error_msg}"
                    f"（{recovery_count + 1}回目の回復試行）"
                )
                logger.info(
                    "回復誘導 #%d: error_repetition - %s",
                    recovery_count + 1,
                    error_msg,
                )
                if metrics is not None:
                    metrics.record_recovery_attempt()
                return {
                    "messages": messages + [
                        AIMessage(content=f"⚠️ パターン検知: {error_msg}"),
                        HumanMessage(content=recovery_msg),
                    ],
                    "loop_count": loop_count,
                    "recovery_count": recovery_count + 1,
                    "failed_approaches": failed_approaches,
                    "needs_recovery": True,
                }
            return {
                "messages": messages + [AIMessage(content=(
                    f"{error_msg} "
                    f"回復試行が上限({max_recovery_attempts}回)に達したため、処理を中断します。"
                ))],
                "loop_count": loop_count,
                "is_completed": True,
            }

        response = await model_with_tools.ainvoke(_truncate_messages(messages))

        if metrics is not None:
            metrics.record_step()
            # 回復後にツール呼び出しが成功した場合（回復成功とみなす）
            has_tool_calls = (
                hasattr(response, "tool_calls") and response.tool_calls
            )
            if recovery_count > 0 and has_tool_calls:
                metrics.record_recovery_success()

        return {
            "messages": messages + [response],
            "loop_count": loop_count + 1,
            "needs_recovery": False,
        }

    def should_continue(state: AgentState) -> str:
        """ツール呼び出しが必要か判定するルーティング関数."""
        if state.get("is_completed", False):
            return END

        # 回復誘導後: LLMに再度考えさせるためagentノードに戻す
        if state.get("needs_recovery", False):
            return "agent"

        messages = state.get("messages", [])
        if not messages:
            return END

        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    tool_node = ToolNode(tools)

    async def tool_node_wrapper(state: AgentState) -> dict[str, Any]:
        """ツールノードのラッパー。バリデーション・確認フローを経てツールを実行する。"""
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        tool_calls = getattr(last_message, "tool_calls", []) if last_message else []

        denied_messages: list[ToolMessage] = []
        validation_error_messages: list[ToolMessage] = []
        approved_calls: list[dict[str, Any]] = []
        # 確認が必要なtool_callsを一時保持（バッチ確認用）
        needs_confirm_calls: list[dict[str, Any]] = []

        for tc in tool_calls:
            tool_name: str = tc["name"]
            tool_args: dict[str, Any] = tc["args"]
            tool_call_id: str = tc["id"]

            # パラメータバリデーション
            if tool_validator is not None:
                result = tool_validator.validate(tool_name, tool_args)
                if not result.is_valid:
                    validation_error_messages.append(
                        ToolMessage(
                            content=f"パラメータエラー: {result.error_message}\n"
                            "正しいパラメータで再度呼び出してください。",
                            tool_call_id=tool_call_id,
                            name=tool_name,
                        )
                    )
                    if metrics is not None:
                        metrics.record_tool_call(tool_name, is_success=False)
                    continue

            needs_confirm = executor is not None and executor.should_confirm(
                tool_name, tool_args
            )
            if needs_confirm:
                needs_confirm_calls.append(tc)
            else:
                approved_calls.append(tc)

        # 確認が必要なtool_callsの処理（バッチ or 逐次）
        if needs_confirm_calls:
            if batch_confirm_callback is not None and len(needs_confirm_calls) > 1:
                # バッチ確認: 複数tool_callsを一括で確認
                confirm_items = [(tc["name"], tc["args"]) for tc in needs_confirm_calls]
                results = batch_confirm_callback(confirm_items)
                for tc, is_approved in zip(needs_confirm_calls, results, strict=True):
                    if is_approved:
                        approved_calls.append(tc)
                    else:
                        denied_messages.append(
                            ToolMessage(
                                content="ユーザーがこの操作を拒否しました。",
                                tool_call_id=tc["id"],
                                name=tc["name"],
                            )
                        )
            else:
                # 逐次確認: 従来のconfirm_callbackで1つずつ確認
                for tc in needs_confirm_calls:
                    cb = confirm_callback
                    approved = cb(tc["name"], tc["args"]) if cb else True
                    if approved:
                        approved_calls.append(tc)
                    else:
                        denied_messages.append(
                            ToolMessage(
                                content="ユーザーがこの操作を拒否しました。",
                                tool_call_id=tc["id"],
                                name=tc["name"],
                            )
                        )

        # 全てのtool_callsが拒否された場合はエージェントを停止する
        # 一部拒否の場合は承認済みcallsを実行して継続する
        if denied_messages and not approved_calls:
            return {
                "messages": messages + denied_messages,
                "is_completed": True,
            }

        if approved_calls and last_message is not None:
            modified_last = last_message.model_copy(
                update={"tool_calls": approved_calls}
            )
            modified_state = {**state, "messages": messages[:-1] + [modified_last]}
            result_state = await tool_node.ainvoke(modified_state)
            new_messages: list[BaseMessage] = result_state.get("messages", [])

            # メトリクス記録
            if metrics is not None:
                for msg in new_messages:
                    if isinstance(msg, ToolMessage):
                        content = msg.content if isinstance(msg.content, str) else ""
                        is_error = getattr(msg, "status", None) == "error" or any(
                            kw in content
                            for kw in (
                                "Error",
                                "エラー",
                                "失敗",
                                "error",
                                "Exception",
                                "禁止",
                            )
                        )
                        tool_name_for_metric = getattr(msg, "name", "") or ""
                        metrics.record_tool_call(
                            tool_name_for_metric, is_success=not is_error
                        )
        else:
            new_messages = []

        return {
            "messages": messages
            + validation_error_messages
            + denied_messages
            + new_messages
        }

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node_wrapper)

    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", "agent": "agent", END: END}
    )
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
        batch_confirm_callback: (
            Callable[[list[tuple[str, dict[str, Any]]]], list[bool]] | None
        ) = None,
        context_manager: ContextManager | None = None,
        prompt_manager: PromptManager | None = None,
        tool_registry: ToolRegistry | None = None,
        max_parallel_workers: int = 3,
        max_recovery_attempts: int = 2,
        langsmith_project: str = "",
        skills_context: str = "",
    ) -> None:
        self._model = model
        self._langsmith_project = langsmith_project
        self._tools = tools
        self._max_loops = max_loops
        self._executor = executor
        self._confirm_callback = confirm_callback
        self._batch_confirm_callback = batch_confirm_callback
        self._context_manager = context_manager
        self._prompt_manager = prompt_manager or PromptManager()
        self._skills_context = skills_context
        self._metrics = SessionMetrics()
        self._max_parallel_workers = max_parallel_workers

        # ToolValidator はレジストリがあれば作成
        tool_validator: ToolValidator | None = None
        if tool_registry is not None:
            tool_validator = ToolValidator(tool_registry)

        self._graph = build_agent_graph(
            model,
            tools,
            max_loops,
            executor,
            confirm_callback,
            batch_confirm_callback=batch_confirm_callback,
            tool_validator=tool_validator,
            metrics=self._metrics,
            max_recovery_attempts=max_recovery_attempts,
        )
        self._compiled = self._graph.compile()
        # ターン間で引き継ぐメッセージ履歴（SystemMessage + 会話全体）
        self._history: list[BaseMessage] = []

        # Orchestrator と Planner（遅延初期化、循環インポート回避のためAny型）
        self._planner: Any = None
        self._orchestrator: Any = None
        self._tool_registry = tool_registry

    @property
    def metrics(self) -> SessionMetrics:
        """セッションメトリクスを返す."""
        return self._metrics

    def _make_runnable_config(self, run_name: str = "agent-run") -> RunnableConfig:
        """LangSmith用 RunnableConfig を生成する."""
        tags = ["myagent"]
        metadata: dict[str, Any] = {"max_loops": self._max_loops}
        if self._langsmith_project:
            metadata["project"] = self._langsmith_project
        return RunnableConfig(run_name=run_name, tags=tags, metadata=metadata)

    def clear_history(self) -> None:
        """会話履歴をリセットする."""
        self._history = []

    def get_last_ai_text(self) -> str:
        """最後のAIメッセージのテキストコンテンツを返す."""
        for msg in reversed(self._history):
            if isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    texts = [
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    return "".join(texts)
        return ""

    def inject_context(self, user_text: str, assistant_text: str) -> None:
        """会話履歴にコンテキスト情報を注入する.

        スラッシュコマンドの出力など、エージェント外で生成された情報を
        会話履歴に追加し、後続のターンで参照可能にする。

        注入メッセージには明確なラベルを付与し、LLMが主タスクの文脈と
        混同しないようにする。

        Args:
            user_text: ユーザー側のメッセージ（コマンド入力等）。
            assistant_text: アシスタント側のメッセージ（コマンド出力等）。
        """
        labeled_user = (
            f"[システム管理コマンドの実行（主タスクとは無関係）]\n{user_text}"
        )
        labeled_assistant = (
            f"[システム管理コマンドの実行結果（参照情報のみ。"
            f"主タスクの指示や文脈として扱わないこと）]\n{assistant_text}"
        )
        self._history.append(HumanMessage(content=labeled_user))
        self._history.append(AIMessage(content=labeled_assistant))

    def _build_initial_messages(self, instruction: str) -> list[BaseMessage]:
        """履歴に新しいユーザー指示を加えた初期メッセージリストを生成する.

        初回ターンの場合、PromptManager でシステムプロンプトを構築する。
        """
        if self._history:
            return list(self._history) + [HumanMessage(content=instruction)]

        # 初回ターン: PromptManager でプロンプト構築
        project_index = (
            self._context_manager.project_index
            if self._context_manager is not None
            else None
        )
        working_directory = (
            self._context_manager.working_directory
            if self._context_manager is not None
            else ""
        )
        system_content = self._prompt_manager.build_prompt(
            project_index=project_index,
            working_directory=working_directory,
            skills_context=self._skills_context or None,
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
        DCP を実行してから LLM を使って古い会話を要約・圧縮する。
        """
        if (
            self._context_manager is None
            or not self._history
            or not self._context_manager.needs_compression(self._history)
        ):
            return

        # DCP: 圧縮前に冗長なツール出力を刈り込む
        self._history = self._context_manager.prune_redundant_tool_outputs(
            self._history
        )

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
            "recovery_count": 0,
            "failed_approaches": [],
            "needs_recovery": False,
        }

        try:
            result = await self._compiled.ainvoke(
                initial_state,  # type: ignore[arg-type]
                config=self._make_runnable_config("agent-run"),
            )
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

    def _get_planner(self) -> Any:
        """Planner を遅延初期化して返す."""
        if self._planner is None:
            from myagent.agent.planner import Planner

            self._planner = Planner(self._model)
        return self._planner

    def _get_orchestrator(self) -> Any:
        """Orchestrator を遅延初期化して返す."""
        if self._orchestrator is None:
            from myagent.agent.orchestrator import Orchestrator

            self._orchestrator = Orchestrator(
                model=self._model,
                tools=self._tools,
                max_workers=self._max_parallel_workers,
                max_loops=self._max_loops,
                executor=self._executor,
                confirm_callback=self._confirm_callback,
                context_manager=self._context_manager,
                prompt_manager=self._prompt_manager,
                tool_registry=self._tool_registry,
            )
        return self._orchestrator

    async def run_parallel(self, instruction: str) -> str:
        """Planner + Orchestrator 経由で並列実行する.

        サブタスクを依存関係分析し、独立したタスクを並列実行する。

        Args:
            instruction: ユーザーからの指示テキスト。

        Returns:
            全ワーカーの実行結果の要約。

        Raises:
            MyAgentError: 実行中にエラーが発生した場合。
        """
        from myagent.agent.orchestrator import _build_summary

        planner = self._get_planner()
        orchestrator = self._get_orchestrator()

        try:
            tasks = await planner.plan_with_dependencies(instruction)
        except Exception as e:
            msg = f"タスク分解に失敗しました: {e}"
            raise MyAgentError(msg) from e

        try:
            results = await orchestrator.execute(tasks, metrics=self._metrics)
        except Exception as e:
            msg = f"並列実行中にエラーが発生しました: {e}"
            raise MyAgentError(msg) from e

        return _build_summary(results)

    async def run_parallel_with_events(
        self, instruction: str
    ) -> AsyncIterator[AgentEvent]:
        """Planner + Orchestrator 経由でイベント付き並列実行する.

        Args:
            instruction: ユーザーからの指示テキスト。

        Yields:
            エージェントイベント。
        """
        planner = self._get_planner()
        orchestrator = self._get_orchestrator()

        try:
            tasks = await planner.plan_with_dependencies(instruction)
        except Exception as e:
            yield AgentEvent.agent_error(f"タスク分解に失敗しました: {e}")
            return

        try:
            async for event in orchestrator.execute_with_events(
                tasks, metrics=self._metrics
            ):
                yield event
        except Exception as e:
            yield AgentEvent.agent_error(f"並列実行中にエラーが発生しました: {e}")

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
            "recovery_count": 0,
            "failed_approaches": [],
            "needs_recovery": False,
        }

        _prompt_tokens = 0
        _completion_tokens = 0
        _model_name = ""
        _final_messages: list[BaseMessage] = []
        _fallback_messages: list[BaseMessage] = []

        try:
            async for event in self._compiled.astream_events(
                initial_state,
                version="v2",
                config=self._make_runnable_config("agent-stream"),
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
                    # ToolMessage等のオブジェクトから content を抽出する
                    if isinstance(output, str):
                        output_str = output
                    elif hasattr(output, "content"):
                        c = output.content
                        output_str = c if isinstance(c, str) else str(c)
                    else:
                        output_str = str(output)
                    yield AgentEvent.tool_end(name, output_str)

                elif kind == "on_chain_end":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        msgs = output.get("messages", [])
                        if msgs:
                            if event.get("name") == "LangGraph":
                                # トップレベルグラフの完了イベント（最優先）
                                _final_messages = msgs
                            else:
                                # ノード単位の完了イベント（フォールバック用）
                                _fallback_messages = msgs

        except Exception as e:
            yield AgentEvent.agent_error(str(e))
            return

        if not _final_messages and _fallback_messages:
            logger.warning(
                "LangGraph の on_chain_end イベントをキャプチャできませんでした。"
                "フォールバックメッセージを使用します。"
            )
            _final_messages = _fallback_messages

        if not _final_messages:
            logger.warning(
                "最終メッセージが空です。会話履歴が次のターンに引き継がれません。"
            )

        self._update_history(_final_messages)

        yield AgentEvent.agent_complete(
            "実行完了",
            prompt_tokens=_prompt_tokens,
            completion_tokens=_completion_tokens,
            model_name=_model_name,
        )
