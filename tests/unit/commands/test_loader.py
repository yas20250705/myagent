"""CommandLoader のユニットテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from myagent.commands.loader import load_command_file, load_commands_from_dir


def write_toml(tmp_path: Path, name: str, content: str) -> Path:
    """テスト用TOMLファイルを作成する."""
    path = tmp_path / f"{name}.toml"
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadCommandFile:
    def test_load_basic(self, tmp_path: Path) -> None:
        path = write_toml(
            tmp_path,
            "test-cmd",
            '''name = "test-cmd"
description = "テストコマンド"
prompt = "テストプロンプト"
''',
        )
        cmd = load_command_file(path, "project")
        assert cmd is not None
        assert cmd.name == "test-cmd"
        assert cmd.description == "テストコマンド"
        assert cmd.prompt == "テストプロンプト"
        assert cmd.scope == "project"
        assert cmd.arguments == {}

    def test_load_with_arguments(self, tmp_path: Path) -> None:
        path = write_toml(
            tmp_path,
            "my-cmd",
            '''name = "my-cmd"
description = "引数ありコマンド"
prompt = "{{target}} を処理する"

[arguments]
target = { description = "対象ファイル", default = "." }
''',
        )
        cmd = load_command_file(path, "global")
        assert cmd is not None
        assert cmd.scope == "global"
        assert "target" in cmd.arguments
        assert cmd.arguments["target"].description == "対象ファイル"
        assert cmd.arguments["target"].default == "."
        assert cmd.arguments["target"].required is False

    def test_load_required_argument(self, tmp_path: Path) -> None:
        path = write_toml(
            tmp_path,
            "req-cmd",
            '''name = "req-cmd"
description = "必須引数コマンド"
prompt = "{{path}} を処理する"

[arguments]
path = { description = "ファイルパス" }
''',
        )
        cmd = load_command_file(path, "project")
        assert cmd is not None
        assert cmd.arguments["path"].required is True

    def test_returns_none_on_missing_name(self, tmp_path: Path) -> None:
        path = write_toml(
            tmp_path,
            "no-name",
            '''description = "説明"
prompt = "プロンプト"
''',
        )
        cmd = load_command_file(path, "project")
        assert cmd is None

    def test_returns_none_on_missing_description(self, tmp_path: Path) -> None:
        path = write_toml(
            tmp_path,
            "no-desc",
            '''name = "no-desc"
prompt = "プロンプト"
''',
        )
        cmd = load_command_file(path, "project")
        assert cmd is None

    def test_returns_none_on_missing_prompt(self, tmp_path: Path) -> None:
        path = write_toml(
            tmp_path,
            "no-prompt",
            '''name = "no-prompt"
description = "説明"
''',
        )
        cmd = load_command_file(path, "project")
        assert cmd is None

    def test_returns_none_on_invalid_toml(self, tmp_path: Path) -> None:
        path = tmp_path / "bad-cmd.toml"
        path.write_text("invalid toml content ::::", encoding="utf-8")
        cmd = load_command_file(path, "project")
        assert cmd is None

    def test_returns_none_on_invalid_name(self, tmp_path: Path) -> None:
        """命名規則違反のコマンド名はNoneを返す."""
        path = write_toml(
            tmp_path,
            "InvalidName",
            '''name = "InvalidName"
description = "説明"
prompt = "プロンプト"
''',
        )
        cmd = load_command_file(path, "project")
        assert cmd is None

    def test_returns_none_when_name_mismatch_filename(self, tmp_path: Path) -> None:
        """ファイル名とnameフィールドが一致しない場合はNoneを返す."""
        path = write_toml(
            tmp_path,
            "file-name",
            '''name = "different-name"
description = "説明"
prompt = "プロンプト"
''',
        )
        cmd = load_command_file(path, "project")
        assert cmd is None

    def test_returns_none_on_file_not_found(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.toml"
        cmd = load_command_file(path, "project")
        assert cmd is None


class TestLoadCommandsFromDir:
    def test_load_multiple(self, tmp_path: Path) -> None:
        for name in ["cmd-a", "cmd-b", "cmd-c"]:
            write_toml(
                tmp_path,
                name,
                f'''name = "{name}"
description = "{name}の説明"
prompt = "{name}プロンプト"
''',
            )
        commands = load_commands_from_dir(tmp_path, "project")
        assert len(commands) == 3
        names = {c.name for c in commands}
        assert names == {"cmd-a", "cmd-b", "cmd-c"}

    def test_skips_invalid(self, tmp_path: Path) -> None:
        write_toml(
            tmp_path,
            "valid-cmd",
            '''name = "valid-cmd"
description = "説明"
prompt = "プロンプト"
''',
        )
        # 無効なファイル
        (tmp_path / "bad.toml").write_text(":::invalid:::", encoding="utf-8")

        commands = load_commands_from_dir(tmp_path, "project")
        assert len(commands) == 1
        assert commands[0].name == "valid-cmd"

    def test_returns_empty_for_nonexistent_dir(self, tmp_path: Path) -> None:
        commands = load_commands_from_dir(tmp_path / "nonexistent", "project")
        assert commands == []

    def test_returns_empty_for_empty_dir(self, tmp_path: Path) -> None:
        commands = load_commands_from_dir(tmp_path, "project")
        assert commands == []
