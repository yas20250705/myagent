"""Executor モジュール.

確認レベルに基づいてツール実行前の確認が必要か判定する。
"""

from __future__ import annotations

from typing import Any, Literal

ConfirmationLevel = Literal["strict", "normal", "autonomous"]

# normalレベルで確認が必要な書き込み・破壊操作ツール
_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "run_command",
        "git_commit",
        "git_checkout",
    }
)

# strictレベルで確認が不要な読み取り専用ツール
_READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "list_directory",
        "glob_search",
        "grep_search",
        "git_status",
        "git_diff",
        "git_log",
        "run_tests",
    }
)


class Executor:
    """ツール実行の確認フローを管理する.

    確認レベルに応じて、ツール実行前にユーザー確認が必要かを判定する。
    """

    def __init__(
        self,
        confirmation_level: ConfirmationLevel = "normal",
    ) -> None:
        self.confirmation_level = confirmation_level

    def should_confirm(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> bool:
        """確認が必要な操作かを判定する.

        Args:
            tool_name: ツール名。
            tool_input: ツールへの入力。

        Returns:
            確認が必要な場合True。
        """
        if self.confirmation_level == "autonomous":
            return False

        if self.confirmation_level == "strict":
            return tool_name not in _READ_ONLY_TOOLS

        # normal: 書き込み・破壊操作、およびMCPツール（外部サービス操作）は確認
        return tool_name in _WRITE_TOOLS or tool_name.startswith("mcp_")
