"""Critic モジュール.

エージェントの実行結果を評価し、無限ループ検知を行う。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

_LOOP_DETECTION_WINDOW = 4


class Critic:
    """エージェントの実行結果を評価する.

    無限ループ検知を行い、同一ツール呼び出しの繰り返しを検出する。
    """

    def detect_loop(
        self,
        messages: list[BaseMessage],
        window: int = _LOOP_DETECTION_WINDOW,
    ) -> bool:
        """同一ツール呼び出しの繰り返しを検知する.

        直近のAIメッセージのツール呼び出しシグネチャを比較し、
        同一の呼び出しが連続している場合にTrueを返す。

        Args:
            messages: 会話履歴。
            window: 検査するAIメッセージの最大件数。

        Returns:
            無限ループを検知した場合True。
        """
        ai_msgs_with_tools = [
            msg
            for msg in messages
            if isinstance(msg, AIMessage) and bool(getattr(msg, "tool_calls", None))
        ]

        if len(ai_msgs_with_tools) < 2:
            return False

        recent = ai_msgs_with_tools[-window:]
        if len(recent) < 2:
            return False

        def _signature(msg: AIMessage) -> str:
            calls = [
                (tc["name"], str(sorted(tc.get("args", {}).items())))
                for tc in msg.tool_calls
            ]
            return str(sorted(calls))

        last_sig = _signature(recent[-1])
        prev_sig = _signature(recent[-2])

        return last_sig == prev_sig
