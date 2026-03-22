"""ツールレジストリのテスト."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from langchain_core.tools import BaseTool

from myagent.tools.registry import ToolRegistry, create_default_registry


class TestToolRegistry:
    """ToolRegistry のテスト."""

    def test_ツールを登録して取得できる(self) -> None:
        registry = ToolRegistry()
        mock_tool = MagicMock(spec=BaseTool)
        mock_tool.name = "test_tool"
        registry.register(mock_tool)
        assert registry.get("test_tool") is mock_tool

    def test_存在しないツールはNoneを返す(self) -> None:
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_全ツールをリストで取得できる(self) -> None:
        registry = ToolRegistry()
        tool1 = MagicMock(spec=BaseTool)
        tool1.name = "tool1"
        tool2 = MagicMock(spec=BaseTool)
        tool2.name = "tool2"
        registry.register(tool1)
        registry.register(tool2)
        tools = registry.list_tools()
        assert len(tools) == 2

    def test_全ツールのスキーマ一覧を取得できる(self) -> None:
        registry = ToolRegistry()
        mock_tool = MagicMock(spec=BaseTool)
        mock_tool.name = "test_tool"
        mock_tool.description = "テスト用ツール"
        mock_tool.args_schema = None
        registry.register(mock_tool)
        schemas = registry.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "test_tool"


class Testcreate_default_registry:
    """create_default_registry 関数のテスト."""

    def test_デフォルトレジストリに9つのツールが登録される(
        self, tmp_path: Path
    ) -> None:
        registry = create_default_registry(project_root=tmp_path)
        tools = registry.list_tools()
        assert len(tools) == 9

    def test_デフォルトレジストリにread_fileが含まれる(self, tmp_path: Path) -> None:
        registry = create_default_registry(project_root=tmp_path)
        assert registry.get("read_file") is not None

    def test_デフォルトレジストリにrun_commandが含まれる(self, tmp_path: Path) -> None:
        registry = create_default_registry(project_root=tmp_path)
        assert registry.get("run_command") is not None
