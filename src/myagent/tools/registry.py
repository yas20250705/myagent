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
from myagent.tools.path_security import AllowedDirectories
from myagent.tools.shared_state import WorkingDirectory
from myagent.tools.shell_tools import RunCommandTool
from myagent.tools.web_tools import WebFetchTool, WebSearchTool


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


def create_default_registry(
    project_root: Path | None = None,
    extra_allowed_dirs: list[Path] | None = None,
    initial_cwd: Path | None = None,
    web_search_api_key: str = "",
    web_search_timeout: int = 25,
    web_search_default_num_results: int = 5,
    web_fetch_timeout: int = 30,
    web_fetch_max_size_bytes: int = 5 * 1024 * 1024,
    web_search_fallback_enabled: bool = True,
    web_search_backend_names: list[str] | None = None,
) -> ToolRegistry:
    """デフォルトのツール一式を登録したレジストリを作成する.

    Args:
        project_root: プロジェクトルートパス。Noneの場合はカレントディレクトリ。
        extra_allowed_dirs: 追加の許可ディレクトリ。
        initial_cwd: 初期作業ディレクトリ。Noneの場合はproject_rootと同じ。
        web_search_api_key: Exa AI Web検索APIキー。
        web_search_timeout: Web検索タイムアウト秒数。
        web_search_default_num_results: Web検索デフォルト件数。
        web_fetch_timeout: Webページ取得タイムアウト秒数。
        web_fetch_max_size_bytes: Webページ取得最大サイズ（バイト）。
        web_search_fallback_enabled: フォールバック検索の有効/無効。
        web_search_backend_names: 検索バックエンド名リスト。

    Returns:
        全デフォルトツールが登録されたToolRegistry。
    """
    root = project_root or Path.cwd()
    start_cwd = initial_cwd.resolve() if initial_cwd else root

    # initial_cwd が extra_allowed_dirs に含まれていない場合は自動追加
    extra = list(extra_allowed_dirs) if extra_allowed_dirs else []
    if initial_cwd and not any(
        start_cwd == d.resolve() or str(start_cwd).startswith(str(d.resolve()))
        for d in [root] + extra
    ):
        extra.append(start_cwd)

    allowed = AllowedDirectories(root, extra or None)
    wd = WorkingDirectory(start_cwd)
    registry = ToolRegistry()

    registry.register(ReadFileTool(allowed_dirs=allowed, working_dir=wd))
    registry.register(WriteFileTool(allowed_dirs=allowed, working_dir=wd))
    registry.register(EditFileTool(allowed_dirs=allowed, working_dir=wd))
    registry.register(ListDirectoryTool(allowed_dirs=allowed, working_dir=wd))
    registry.register(GlobSearchTool(allowed_dirs=allowed, working_dir=wd))
    registry.register(GrepSearchTool(allowed_dirs=allowed, working_dir=wd))
    registry.register(
        RunCommandTool(cwd=start_cwd, allowed_dirs=allowed, working_dir=wd)
    )
    backend_names = web_search_backend_names or [
        "exa",
        "duckduckgo",
    ]
    registry.register(
        WebSearchTool(
            api_key=web_search_api_key,
            timeout_seconds=web_search_timeout,
            default_num_results=web_search_default_num_results,
            fallback_enabled=web_search_fallback_enabled,
            search_backend_names=backend_names,
        )
    )
    registry.register(
        WebFetchTool(
            timeout_seconds=web_fetch_timeout,
            max_size_bytes=web_fetch_max_size_bytes,
        )
    )

    return registry
