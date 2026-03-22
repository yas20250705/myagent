"""エージェント状態管理.

AgentState, SubTask, ToolCall のデータクラスを定義する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from langchain_core.messages import BaseMessage

AgentPhase = Literal[
    "planning",
    "executing",
    "observing",
    "evaluating",
    "completed",
    "failed",
]


@dataclass
class SubTask:
    """エージェントが生成するサブタスク."""

    description: str
    is_completed: bool = False
    result: str = ""
    task_id: str = ""
    depends_on: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)


@dataclass
class ToolCallRecord:
    """ツール呼び出しの記録."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    is_success: bool = True


class AgentState(TypedDict, total=False):
    """LangGraphステートマシンの状態.

    LangGraph StateGraph で使用する状態辞書。
    """

    messages: list[BaseMessage]
    phase: AgentPhase
    sub_tasks: list[SubTask]
    tool_call_history: list[ToolCallRecord]
    current_task_index: int
    loop_count: int
    max_loops: int
    is_completed: bool
    final_answer: str
    error: str
