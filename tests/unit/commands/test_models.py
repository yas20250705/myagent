"""CommandDefinition / CommandArgument のユニットテスト."""

from __future__ import annotations

import pytest

from myagent.commands.models import CommandArgument, CommandDefinition


def _make_cmd(prompt: str, arguments: dict | None = None) -> CommandDefinition:
    return CommandDefinition(
        name="test-cmd",
        description="テスト用コマンド",
        prompt=prompt,
        arguments=arguments or {},
        scope="project",
    )


class TestCommandArgument:
    def test_required_when_no_default(self) -> None:
        arg = CommandArgument(description="必須引数")
        assert arg.required is True

    def test_not_required_when_default_set(self) -> None:
        arg = CommandArgument(description="省略可能", default="default_value")
        assert arg.required is False


class TestCommandDefinitionRender:
    def test_render_no_variables(self) -> None:
        cmd = _make_cmd("変数なしのプロンプト")
        result = cmd.render({})
        assert result == "変数なしのプロンプト"

    def test_render_with_arg(self) -> None:
        cmd = _make_cmd(
            "対象: {{target}}",
            {"target": CommandArgument(description="対象")},
        )
        result = cmd.render({"target": "src/"})
        assert result == "対象: src/"

    def test_render_with_default(self) -> None:
        cmd = _make_cmd(
            "コマンド: {{cmd}}",
            {"cmd": CommandArgument(description="コマンド", default="pytest")},
        )
        result = cmd.render({})
        assert result == "コマンド: pytest"

    def test_render_arg_overrides_default(self) -> None:
        cmd = _make_cmd(
            "コマンド: {{cmd}}",
            {"cmd": CommandArgument(description="コマンド", default="pytest")},
        )
        result = cmd.render({"cmd": "pytest -x"})
        assert result == "コマンド: pytest -x"

    def test_render_missing_required_raises(self) -> None:
        cmd = _make_cmd(
            "対象: {{target}}",
            {"target": CommandArgument(description="必須の対象")},
        )
        with pytest.raises(ValueError, match="必須引数が指定されていません"):
            cmd.render({})

    def test_render_missing_required_shows_arg_def(self) -> None:
        cmd = _make_cmd(
            "{{path}}",
            {"path": CommandArgument(description="ファイルパス")},
        )
        with pytest.raises(ValueError, match="ファイルパス"):
            cmd.render({})

    def test_render_unknown_variable_kept_as_is(self) -> None:
        """定義されていない変数はそのまま残る."""
        cmd = _make_cmd("{{undefined}}")
        result = cmd.render({})
        assert result == "{{undefined}}"

    def test_render_multiple_variables(self) -> None:
        cmd = _make_cmd(
            "{{a}} と {{b}}",
            {
                "a": CommandArgument(description="A"),
                "b": CommandArgument(description="B", default="B_default"),
            },
        )
        result = cmd.render({"a": "value_a"})
        assert result == "value_a と B_default"
