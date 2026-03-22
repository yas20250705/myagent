"""CommandManager / parse_cli_args のユニットテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from myagent.commands.manager import CommandManager, parse_cli_args


def write_toml(directory: Path, name: str, description: str = "説明", prompt: str = "プロンプト") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.toml").write_text(
        f'''name = "{name}"
description = "{description}"
prompt = "{prompt}"
''',
        encoding="utf-8",
    )


class TestCommandManager:
    def test_load_all_from_project_dir(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        write_toml(proj_dir, "cmd-a")
        write_toml(proj_dir, "cmd-b")

        manager = CommandManager(project_commands_dir=proj_dir)
        commands = manager.load_all()
        assert len(commands) == 2
        assert {c.name for c in commands} == {"cmd-a", "cmd-b"}

    def test_project_overrides_global(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        glob_dir = tmp_path / "global"

        write_toml(proj_dir, "shared-cmd", description="プロジェクト版")
        write_toml(glob_dir, "shared-cmd", description="グローバル版")

        manager = CommandManager(
            project_commands_dir=proj_dir,
            global_commands_dir=glob_dir,
        )
        commands = manager.load_all()
        assert len(commands) == 1
        assert commands[0].description == "プロジェクト版"
        assert commands[0].scope == "project"

    def test_global_only_when_no_project_override(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        glob_dir = tmp_path / "global"

        write_toml(proj_dir, "proj-cmd")
        write_toml(glob_dir, "global-cmd")

        manager = CommandManager(
            project_commands_dir=proj_dir,
            global_commands_dir=glob_dir,
        )
        commands = manager.load_all()
        assert len(commands) == 2

    def test_get_existing_command(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        write_toml(proj_dir, "my-cmd")

        manager = CommandManager(project_commands_dir=proj_dir)
        cmd = manager.get("my-cmd")
        assert cmd is not None
        assert cmd.name == "my-cmd"

    def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        manager = CommandManager(project_commands_dir=tmp_path)
        assert manager.get("nonexistent") is None

    def test_find_similar_partial_match(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        write_toml(proj_dir, "test-fix")
        write_toml(proj_dir, "test-run")
        write_toml(proj_dir, "lint-fix")

        manager = CommandManager(project_commands_dir=proj_dir)
        similar = manager.find_similar("test")
        assert "test-fix" in similar
        assert "test-run" in similar
        assert "lint-fix" not in similar

    def test_find_similar_returns_empty_for_no_match(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        write_toml(proj_dir, "cmd-a")

        manager = CommandManager(project_commands_dir=proj_dir)
        similar = manager.find_similar("xyz")
        assert similar == []

    def test_find_similar_limits_to_5(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        for i in range(10):
            write_toml(proj_dir, f"test-cmd-{i}")

        manager = CommandManager(project_commands_dir=proj_dir)
        similar = manager.find_similar("test")
        assert len(similar) <= 5

    def test_load_all_caches_result(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "proj"
        write_toml(proj_dir, "cmd-a")

        manager = CommandManager(project_commands_dir=proj_dir)
        first = manager.load_all()
        # 新しいファイルを追加してもキャッシュが使われる
        write_toml(proj_dir, "cmd-b")
        second = manager.load_all()
        assert len(first) == len(second)


class TestParseCLIArgs:
    def test_empty_string(self) -> None:
        assert parse_cli_args("") == {}

    def test_single_arg(self) -> None:
        result = parse_cli_args("--target src/")
        assert result == {"target": "src/"}

    def test_multiple_args(self) -> None:
        result = parse_cli_args("--cmd pytest --path tests/")
        assert result == {"cmd": "pytest", "path": "tests/"}

    def test_quoted_value(self) -> None:
        result = parse_cli_args('--cmd "pytest -x"')
        assert result == {"cmd": "pytest -x"}

    def test_equals_format(self) -> None:
        result = parse_cli_args("--target=src/main.py")
        assert result == {"target": "src/main.py"}

    def test_flag_without_value(self) -> None:
        result = parse_cli_args("--verbose")
        assert result == {"verbose": "true"}

    def test_mixed_formats(self) -> None:
        result = parse_cli_args("--flag --key=val --other value")
        assert result["flag"] == "true"
        assert result["key"] == "val"
        assert result["other"] == "value"
