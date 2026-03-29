"""Critic モジュール.

エージェントの実行結果を評価し、無限ループ検知とエラー繰り返し検知を行う。
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, ToolMessage

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

_LOOP_DETECTION_WINDOW = 6
_LOOP_CONSECUTIVE_THRESHOLD = 3
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
        consecutive_threshold: int = _LOOP_CONSECUTIVE_THRESHOLD,
    ) -> bool:
        """同一ツール呼び出しの繰り返しを検知する.

        直近のAIメッセージのツール呼び出しシグネチャを比較し、
        同一の呼び出しが consecutive_threshold 回以上連続した場合にTrueを返す。

        2回連続では検知しない（techlearnなどのリサーチ系スキルで同一URLを
        複数ステップに渡って参照することがあるため）。

        Args:
            messages: 会話履歴。
            window: 検査するAIメッセージの最大件数。
            consecutive_threshold: ループと判定する連続回数（デフォルト3）。

        Returns:
            無限ループを検知した場合True。
        """
        ai_msgs_with_tools = [
            msg
            for msg in messages
            if isinstance(msg, AIMessage) and bool(getattr(msg, "tool_calls", None))
        ]

        if len(ai_msgs_with_tools) < consecutive_threshold:
            return False

        recent = ai_msgs_with_tools[-window:]
        if len(recent) < consecutive_threshold:
            return False

        def _signature(msg: AIMessage) -> str:
            calls = [
                (tc["name"], str(sorted(tc.get("args", {}).items())))
                for tc in msg.tool_calls
            ]
            return str(sorted(calls))

        # 末尾から連続して同一シグネチャが続く回数をカウント
        last_sig = _signature(recent[-1])
        consecutive = 1
        for msg in reversed(recent[:-1]):
            if _signature(msg) == last_sig:
                consecutive += 1
            else:
                break

        return consecutive >= consecutive_threshold

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
            # エラーを示すキーワードまたはstatusフィールドで判定する
            is_error = getattr(msg, "status", None) == "error" or any(
                keyword in content
                for keyword in (
                    "Error",
                    "エラー",
                    "失敗",
                    "error",
                    "Exception",
                    "禁止",
                )
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

    def build_recovery_message(
        self,
        detection_type: str,
        detail: str,
        failed_approaches: list[str] | None = None,
    ) -> str:
        """回復誘導メッセージを生成する.

        パターン検知時に処理を中断するのではなく、
        LLMに代替アプローチの検討を促すメッセージを生成する。

        Args:
            detection_type: 検知タイプ。"loop" または "error_repetition"。
            detail: 検知されたパターンの詳細説明。
            failed_approaches: これまでに失敗したアプローチのリスト。

        Returns:
            回復誘導メッセージ文字列。
        """
        if detection_type == "loop":
            pattern_desc = (
                f"同一ツール呼び出しの繰り返しが検知されました: {detail}"
            )
        elif detection_type == "error_repetition":
            pattern_desc = f"同一エラーの繰り返しが検知されました: {detail}"
        else:
            pattern_desc = f"非生産的なパターンが検知されました: {detail}"

        parts = [
            "⚠️ 現在のアプローチはブロックされています。",
            "",
            f"**検知されたパターン**: {pattern_desc}",
            "",
        ]

        if failed_approaches:
            parts.append("**これまでに失敗したアプローチ**:")
            for i, approach in enumerate(failed_approaches, 1):
                parts.append(f"  {i}. {approach}")
            parts.append("")
            parts.append(
                "上記のアプローチは既に失敗しています。"
                "これらとは**異なる**代替アプローチを検討してください。"
            )
        else:
            parts.append(
                "同じ方法を再試行するのではなく、代替アプローチを検討してください。"
            )

        parts.extend([
            "",
            "**指示**: 別のアプローチを最大3つ提案し、"
            "最も有望なものを試行してください。",
            "例: 別のツールを使う、問題を段階的に分解する、"
            "前提条件を確認する、別のファイルパスを試す等。",
        ])

        return "\n".join(parts)
