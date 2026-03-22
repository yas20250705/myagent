"""エージェントイベント定義.

Agent→CLIレイヤー間の通信用イベントを定義する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EventType = Literal[
    "stream_token",
    "tool_start",
    "tool_end",
    "plan_start",
    "plan_end",
    "evaluate_start",
    "evaluate_end",
    "confirm_request",
    "agent_complete",
    "agent_error",
    "parallel_start",
    "worker_start",
    "worker_end",
    "parallel_end",
]


@dataclass
class AgentEvent:
    """エージェントが発行するイベント.

    CLIレイヤーがこのイベントを受け取り、表示やユーザー確認を行う。
    """

    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def stream_token(token: str) -> AgentEvent:
        """ストリーミングトークンイベントを作成する."""
        return AgentEvent(event_type="stream_token", data={"token": token})

    @staticmethod
    def tool_start(tool_name: str, arguments: dict[str, Any]) -> AgentEvent:
        """ツール実行開始イベントを作成する."""
        return AgentEvent(
            event_type="tool_start",
            data={"tool_name": tool_name, "arguments": arguments},
        )

    @staticmethod
    def tool_end(tool_name: str, result: str, is_success: bool = True) -> AgentEvent:
        """ツール実行完了イベントを作成する."""
        return AgentEvent(
            event_type="tool_end",
            data={
                "tool_name": tool_name,
                "result": result,
                "is_success": is_success,
            },
        )

    @staticmethod
    def confirm_request(action: str, details: str) -> AgentEvent:
        """ユーザー確認要求イベントを作成する."""
        return AgentEvent(
            event_type="confirm_request",
            data={"action": action, "details": details},
        )

    @staticmethod
    def agent_complete(
        final_answer: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model_name: str = "",
    ) -> AgentEvent:
        """エージェント完了イベントを作成する."""
        return AgentEvent(
            event_type="agent_complete",
            data={
                "final_answer": final_answer,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "model_name": model_name,
            },
        )

    @staticmethod
    def agent_error(error: str) -> AgentEvent:
        """エージェントエラーイベントを作成する."""
        return AgentEvent(
            event_type="agent_error",
            data={"error": error},
        )

    @staticmethod
    def parallel_start(total_workers: int, task_descriptions: list[str]) -> AgentEvent:
        """並列実行開始イベントを作成する."""
        return AgentEvent(
            event_type="parallel_start",
            data={
                "total_workers": total_workers,
                "task_descriptions": task_descriptions,
            },
        )

    @staticmethod
    def worker_start(worker_id: str, task_description: str) -> AgentEvent:
        """ワーカー開始イベントを作成する."""
        return AgentEvent(
            event_type="worker_start",
            data={"worker_id": worker_id, "task_description": task_description},
        )

    @staticmethod
    def worker_end(
        worker_id: str,
        task_description: str,
        is_success: bool,
        result: str = "",
    ) -> AgentEvent:
        """ワーカー完了イベントを作成する."""
        return AgentEvent(
            event_type="worker_end",
            data={
                "worker_id": worker_id,
                "task_description": task_description,
                "is_success": is_success,
                "result": result,
            },
        )

    @staticmethod
    def parallel_end(
        total: int,
        succeeded: int,
        failed: int,
        summary: str = "",
    ) -> AgentEvent:
        """並列実行完了イベントを作成する."""
        return AgentEvent(
            event_type="parallel_end",
            data={
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "summary": summary,
            },
        )
