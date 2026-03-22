"""ツールバリデーションモジュール.

ツール呼び出しパラメータのバリデーションを提供する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from myagent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """バリデーション結果."""

    is_valid: bool
    error_message: str = ""


class ToolValidator:
    """ツール呼び出しパラメータのバリデーションを行う.

    ToolRegistry に登録されたツールの args_schema（Pydantic モデル）を使用して
    パラメータを検証する。
    """

    def __init__(self, registry: ToolRegistry) -> None:
        """ToolValidator を初期化する.

        Args:
            registry: ツールレジストリ。
        """
        self._registry = registry

    def validate(
        self, tool_name: str, tool_args: dict[str, Any]
    ) -> ValidationResult:
        """ツール呼び出しパラメータをバリデーションする.

        Args:
            tool_name: ツール名。
            tool_args: ツールに渡すパラメータ。

        Returns:
            バリデーション結果。
        """
        tool = self._registry.get(tool_name)
        if tool is None:
            return ValidationResult(
                is_valid=False,
                error_message=f"ツール '{tool_name}' は登録されていません。",
            )

        args_schema = tool.args_schema
        if args_schema is None:
            # スキーマ未定義はバリデーションスキップ
            return ValidationResult(is_valid=True)

        try:
            validate_fn = getattr(args_schema, "model_validate", None)
            if validate_fn is None:
                return ValidationResult(is_valid=True)
            validate_fn(tool_args)
            return ValidationResult(is_valid=True)
        except Exception as e:
            error_msg = (
                f"ツール '{tool_name}' のパラメータが不正です: {e}"
            )
            logger.debug("パラメータバリデーションエラー: %s", error_msg)
            return ValidationResult(is_valid=False, error_message=error_msg)
