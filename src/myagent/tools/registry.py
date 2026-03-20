"""ツールレジストリ.

ツールの登録・取得・スキーマ一覧機能を提供する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool

from myagent.tools.file_tools import (
    EditFileTool,
    GlobSearchTool,
    GrepSearchTool,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
)
from myagent.tools.shell_tools import RunCommandTool


class ToolRegistry:
    """ツールの登録と管理を行うレジストリ."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """ツールを登録する."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """名前でツールを取得する."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """登録済みの全ツールをリストで返す."""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict[str, Any]]:
        """全ツールのスキーマ一覧を返す."""
        schemas: list[dict[str, Any]] = []
        for tool in self._tools.values():
            schema: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description,
            }
            args_schema = tool.args_schema
            if args_schema is not None and hasattr(args_schema, "model_json_schema"):
                schema["parameters"] = args_schema.model_json_schema()
            schemas.append(schema)
        return schemas


def create_default_registry(project_root: Path | None = None) -> ToolRegistry:
    """デフォルトのツール一式を登録したレジストリを作成する.

    Args:
        project_root: プロジェクトルートパス。Noneの場合はカレントディレクトリ。

    Returns:
        全デフォルトツールが登録されたToolRegistry。
    """
    root = project_root or Path.cwd()
    registry = ToolRegistry()

    registry.register(ReadFileTool(project_root=root))
    registry.register(WriteFileTool(project_root=root))
    registry.register(EditFileTool(project_root=root))
    registry.register(ListDirectoryTool(project_root=root))
    registry.register(GlobSearchTool(project_root=root))
    registry.register(GrepSearchTool(project_root=root))
    registry.register(RunCommandTool())

    return registry
