"""ToolValidator のユニットテスト."""

from __future__ import annotations

from unittest.mock import MagicMock

from pydantic import BaseModel, Field

from myagent.agent.tool_validator import ToolValidator
from myagent.tools.registry import ToolRegistry


class _DummyArgsSchema(BaseModel):
    """テスト用のツールパラメータスキーマ."""

    file_path: str
    content: str = ""
    line_number: int = Field(default=1, ge=1)


def _create_mock_tool(
    name: str, args_schema: type[BaseModel] | None = _DummyArgsSchema
) -> MagicMock:
    """テスト用のモックツールを作成する."""
    tool = MagicMock()
    tool.name = name
    tool.args_schema = args_schema
    return tool


class TestToolValidator:
    """ToolValidator のテスト."""

    def test_正常なパラメータでバリデーション成功(self) -> None:
        registry = ToolRegistry()
        registry.register(_create_mock_tool("write_file"))
        validator = ToolValidator(registry)

        result = validator.validate(
            "write_file", {"file_path": "/tmp/test.py", "content": "hello"}
        )

        assert result.is_valid is True
        assert result.error_message == ""

    def test_必須フィールド欠落でバリデーション失敗(self) -> None:
        registry = ToolRegistry()
        registry.register(_create_mock_tool("write_file"))
        validator = ToolValidator(registry)

        result = validator.validate("write_file", {"content": "hello"})

        assert result.is_valid is False
        assert "file_path" in result.error_message

    def test_型エラーでバリデーション失敗(self) -> None:
        registry = ToolRegistry()
        registry.register(_create_mock_tool("write_file"))
        validator = ToolValidator(registry)

        result = validator.validate(
            "write_file",
            {"file_path": "/tmp/test.py", "line_number": -1},
        )

        assert result.is_valid is False
        assert "line_number" in result.error_message

    def test_スキーマ未定義ツールはバリデーションスキップ(self) -> None:
        registry = ToolRegistry()
        registry.register(_create_mock_tool("custom_tool", args_schema=None))
        validator = ToolValidator(registry)

        result = validator.validate("custom_tool", {"any_arg": "value"})

        assert result.is_valid is True

    def test_未登録ツールでバリデーション失敗(self) -> None:
        registry = ToolRegistry()
        validator = ToolValidator(registry)

        result = validator.validate("nonexistent_tool", {"arg": "value"})

        assert result.is_valid is False
        assert "nonexistent_tool" in result.error_message
        assert "登録されていません" in result.error_message

    def test_デフォルト値のみでバリデーション成功(self) -> None:
        registry = ToolRegistry()
        registry.register(_create_mock_tool("write_file"))
        validator = ToolValidator(registry)

        result = validator.validate("write_file", {"file_path": "/tmp/test.py"})

        assert result.is_valid is True
