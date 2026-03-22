"""カスタムコマンドのデータモデル定義."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

_TEMPLATE_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class CommandArgument:
    """コマンド引数の定義."""

    description: str
    default: str | None = None

    @property
    def required(self) -> bool:
        """デフォルト値がない場合は必須引数."""
        return self.default is None


@dataclass
class CommandDefinition:
    """コマンド定義."""

    name: str
    description: str
    prompt: str
    arguments: dict[str, CommandArgument] = field(default_factory=dict)
    scope: Literal["project", "global"] = "project"

    def render(self, args: dict[str, str]) -> str:
        """プロンプトテンプレートを引数で展開する.

        `{{variable}}` 形式のプレースホルダーを args またはデフォルト値で置換する。

        Args:
            args: 引数名と値の辞書。

        Returns:
            展開済みのプロンプト文字列。

        Raises:
            ValueError: 必須引数が未指定の場合。
        """
        # 必須引数の未指定チェック
        missing = [
            name
            for name, arg_def in self.arguments.items()
            if arg_def.required and name not in args
        ]
        if missing:
            arg_defs = "\n".join(
                f"  --{name}: {self.arguments[name].description}"
                for name in missing
            )
            raise ValueError(
                f"必須引数が指定されていません: {', '.join(missing)}\n"
                f"引数定義:\n{arg_defs}"
            )

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name in args:
                return args[var_name]
            arg_def = self.arguments.get(var_name)
            if arg_def is not None and arg_def.default is not None:
                return arg_def.default
            # 定義されていない変数はそのまま残す
            return match.group(0)

        return _TEMPLATE_VAR_PATTERN.sub(replacer, self.prompt)
