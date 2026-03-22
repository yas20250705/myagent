"""カスタムコマンドのTOMLファイルパースとロード."""

from __future__ import annotations

import logging
import re
import tomllib
from pathlib import Path
from typing import Any, Literal

from myagent.commands.models import CommandArgument, CommandDefinition

logger = logging.getLogger(__name__)

# 命名規則: 小文字英数字 + ハイフン（先頭・末尾はハイフン不可、連続ハイフン不可）
_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_NAME_LEN = 64


def load_command_file(
    path: Path,
    scope: Literal["project", "global"],
) -> CommandDefinition | None:
    """TOMLファイルをパースして CommandDefinition を返す.

    パース・バリデーションエラーが発生した場合は None を返し、警告ログを出力する。

    Args:
        path: コマンド定義TOMLファイルのパス。
        scope: コマンドのスコープ（"project" or "global"）。

    Returns:
        バリデーション済みの CommandDefinition。エラー時は None。
    """
    try:
        with open(path, "rb") as f:
            data: dict[str, Any] = tomllib.load(f)
    except OSError as e:
        logger.warning("コマンドファイルの読み込みに失敗しました: %s: %s", path, e)
        return None
    except tomllib.TOMLDecodeError as e:
        logger.warning("コマンドファイルのパースに失敗しました: %s: %s", path, e)
        return None

    return _validate_and_build(data, path, scope)


def load_commands_from_dir(
    dir_path: Path,
    scope: Literal["project", "global"],
) -> list[CommandDefinition]:
    """ディレクトリ内の全TOMLファイルをスキャンしてコマンド一覧を返す.

    パースエラーのファイルはスキップする。

    Args:
        dir_path: コマンド定義ディレクトリのパス。
        scope: コマンドのスコープ（"project" or "global"）。

    Returns:
        ロードに成功した CommandDefinition のリスト。
    """
    if not dir_path.is_dir():
        return []

    commands: list[CommandDefinition] = []
    for toml_path in sorted(dir_path.glob("*.toml")):
        cmd = load_command_file(toml_path, scope)
        if cmd is not None:
            commands.append(cmd)

    return commands


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _validate_and_build(
    data: dict[str, Any],
    path: Path,
    scope: Literal["project", "global"],
) -> CommandDefinition | None:
    """TOMLデータをバリデーションして CommandDefinition を構築する."""
    # 必須フィールドチェック
    name = data.get("name")
    description = data.get("description")
    prompt = data.get("prompt")

    if not name:
        logger.warning("コマンド定義に必須フィールド 'name' がありません: %s", path)
        return None
    if not description:
        logger.warning(
            "コマンド定義に必須フィールド 'description' がありません: %s", path
        )
        return None
    if not prompt:
        logger.warning(
            "コマンド定義に必須フィールド 'prompt' がありません: %s", path
        )
        return None

    name = str(name).strip()
    description = str(description).strip()
    prompt = str(prompt).strip()

    # 命名規則バリデーション
    if len(name) > _MAX_NAME_LEN or not _NAME_PATTERN.match(name):
        logger.warning(
            "コマンド名が命名規則に違反しています"
            "（小文字英数字+ハイフンのみ）: %r (%s)",
            name,
            path,
        )
        return None

    # ファイル名（拡張子なし）と name の一致確認
    stem = path.stem
    if name != stem:
        logger.warning(
            "コマンド名 (%r) がファイル名 (%r) と一致しません: %s",
            name,
            stem,
            path,
        )
        return None

    # [arguments] セクションのパース
    arguments: dict[str, CommandArgument] = {}
    raw_args = data.get("arguments", {})
    if isinstance(raw_args, dict):
        for arg_name, arg_data in raw_args.items():
            if isinstance(arg_data, dict):
                arg_description = str(arg_data.get("description", "")).strip()
                arg_default = arg_data.get("default")
                arguments[arg_name] = CommandArgument(
                    description=arg_description,
                    default=str(arg_default) if arg_default is not None else None,
                )
            else:
                logger.warning(
                    "引数定義が不正です: %r in %s", arg_name, path
                )

    return CommandDefinition(
        name=name,
        description=description,
        prompt=prompt,
        arguments=arguments,
        scope=scope,
    )
