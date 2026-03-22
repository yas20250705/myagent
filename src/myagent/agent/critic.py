"""Critic モジュール.

エージェントの実行結果を評価し、無限ループ検知とエラー繰り返し検知を行う。
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, ToolMessage

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

_LOOP_DETECTION_WINDOW = 4
_ERROR_REPETITION_THRESHOLD = 3


class Critic:
    """エージェントの実行結果を評価する.

    無限ループ検知とエラー繰り返し検知を行い、
    エージェントの非生産的な動作を検出する。
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

    def detect_error_repetition(
        self,
        messages: list[BaseMessage],
        threshold: int = _ERROR_REPETITION_THRESHOLD,
    ) -> tuple[bool, str]:
        """同一ツール・同一エラーの繰り返しを検知する.

        ToolMessage の内容からエラーパターンを抽出し、
        同一ツール名で同じエラーメッセージが threshold 回以上
        繰り返された場合に検知する。

        Args:
            messages: 会話履歴。
            threshold: 検知する繰り返し回数の閾値。

        Returns:
            (検知フラグ, 検知メッセージ) のタプル。
            検知しなかった場合は (False, "")。
        """
        # ツール名とエラー内容のペアでカウント
        error_counts: Counter[tuple[str, str]] = Counter()

        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            content = msg.content if isinstance(msg.content, str) else ""
            if not content:
                continue
            # エラーを示すキーワードを含むメッセージを対象とする
            is_error = any(
                keyword in content
                for keyword in ("Error", "エラー", "失敗", "error", "Exception")
            )
            if not is_error:
                continue
            tool_name = getattr(msg, "name", "") or ""
            # エラーメッセージの先頭200文字をキーとする（長いメッセージの揺れを吸収）
            error_key = content[:200]
            error_counts[(tool_name, error_key)] += 1

        for (tool_name, _error_key), count in error_counts.items():
            if count >= threshold:
                return (
                    True,
                    f"{tool_name} で同じエラーが{count}回繰り返されました。"
                    "別のアプローチを試してください。",
                )

        return (False, "")
