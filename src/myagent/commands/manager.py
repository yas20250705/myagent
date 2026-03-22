"""カスタムコマンドの管理・検索・引数パース."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Literal

from myagent.commands.loader import load_commands_from_dir
from myagent.commands.models import CommandDefinition


class CommandManager:
    """コマンドの管理・検索を担う.

    プロジェクトローカルとグローバルの2ディレクトリを管理し、
    同名コマンドはプロジェクトローカルが優先される。
    """

    def __init__(
        self,
        project_commands_dir: Path | None = None,
        global_commands_dir: Path | None = None,
    ) -> None:
        self._project_dir = project_commands_dir
        self._global_dir = global_commands_dir
        self._commands: dict[str, CommandDefinition] = {}
        self._loaded = False

    def load_all(self) -> list[CommandDefinition]:
        """全コマンドをロードして返す.

        プロジェクトローカルが同名グローバルコマンドを上書きする。
        ロード済みの場合はキャッシュを返す。

        Returns:
            ロード済み CommandDefinition のリスト。
        """
        if self._loaded:
            return list(self._commands.values())

        # グローバルを先にロード（プロジェクトローカルで上書き）
        if self._global_dir is not None:
            for cmd in load_commands_from_dir(self._global_dir, "global"):
                self._commands[cmd.name] = cmd

        if self._project_dir is not None:
            for cmd in load_commands_from_dir(self._project_dir, "project"):
                self._commands[cmd.name] = cmd

        self._loaded = True
        return list(self._commands.values())

    def get(self, name: str) -> CommandDefinition | None:
        """名前でコマンドを検索する.

        Args:
            name: コマンド名。

        Returns:
            見つかった CommandDefinition。見つからない場合は None。
        """
        if not self._loaded:
            self.load_all()
        return self._commands.get(name)

    def find_similar(self, name: str) -> list[str]:
        """類似したコマンド名を返す（部分一致）.

        Args:
            name: 検索するコマンド名。

        Returns:
            部分一致するコマンド名のリスト（最大5件）。
        """
        if not self._loaded:
            self.load_all()
        return [
            cmd_name
            for cmd_name in self._commands
            if name in cmd_name or cmd_name in name
        ][:5]


def parse_cli_args(raw_args: str) -> dict[str, str]:
    """`--key value` 形式の引数文字列を辞書にパースする.

    Args:
        raw_args: `--key1 value1 --key2 value2` 形式の文字列。

    Returns:
        {"key1": "value1", "key2": "value2"} 形式の辞書。
        パースに失敗した引数は無視する。
    """
    result: dict[str, str] = {}
    if not raw_args.strip():
        return result

    try:
        tokens = shlex.split(raw_args)
    except ValueError:
        # シェル構文エラーは生のスペース分割にフォールバック
        tokens = raw_args.split()

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            key = token[2:]
            if not key:
                i += 1
                continue
            if "=" in key:
                # --key=value 形式
                k, v = key.split("=", 1)
                result[k] = v
                i += 1
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                result[key] = tokens[i + 1]
                i += 2
            else:
                # 値なしフラグは "true" として扱う
                result[key] = "true"
                i += 1
        else:
            i += 1

    return result


def build_command_manager(
    project_commands_dir_str: str,
    global_commands_dir_str: str,
    scope: Literal["project", "global", "both"] = "both",
) -> CommandManager:
    """設定文字列から CommandManager を構築する.

    Args:
        project_commands_dir_str: プロジェクトコマンドディレクトリのパス文字列。
        global_commands_dir_str: グローバルコマンドディレクトリのパス文字列。
        scope: ロードするスコープ（テスト用）。

    Returns:
        CommandManager インスタンス。
    """
    project_dir: Path | None = None
    global_dir: Path | None = None

    if project_commands_dir_str and scope in ("project", "both"):
        project_dir = Path(project_commands_dir_str)
    if global_commands_dir_str and scope in ("global", "both"):
        global_dir = Path(global_commands_dir_str)
    elif scope in ("global", "both"):
        # デフォルトのグローバルディレクトリ
        global_dir = Path.home() / ".myagent" / "commands"

    return CommandManager(
        project_commands_dir=project_dir,
        global_commands_dir=global_dir,
    )
