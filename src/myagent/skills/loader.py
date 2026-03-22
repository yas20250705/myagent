"""SKILL.md のパースとバリデーション."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Literal

import yaml

from myagent.skills.models import SkillMetadata

logger = logging.getLogger(__name__)

# 命名規則: 小文字英数字 + ハイフン（先頭・末尾はハイフン不可、連続ハイフン不可）
# ハイフンは単語区切りのみ: ^[a-z0-9]+(-[a-z0-9]+)*$
_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_NAME_LEN = 64
_MAX_DESC_LEN = 1024


def parse_skill_md(
    skill_md_path: Path,
    scope: Literal["project", "global"],
) -> SkillMetadata | None:
    """SKILL.md をパースして SkillMetadata を返す.

    パース・バリデーションエラーが発生した場合は None を返し、警告ログを出力する。

    Args:
        skill_md_path: SKILL.md ファイルのパス。
        scope: スキルのスコープ（"project" or "global"）。

    Returns:
        バリデーション済みの SkillMetadata。エラー時は None。
    """
    skill_dir = skill_md_path.parent

    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning(  # noqa: E501
            "スキルファイルの読み込みに失敗しました: %s: %s", skill_md_path, e
        )
        return None

    frontmatter, _ = _split_frontmatter(content, skill_md_path)
    if frontmatter is None:
        return None

    meta = _validate_frontmatter(frontmatter, skill_dir, scope, skill_md_path)
    return meta


def parse_skill_body(skill_md_path: Path) -> str:
    """SKILL.md のボディ（Markdownコンテンツ）を返す.

    Args:
        skill_md_path: SKILL.md ファイルのパス。

    Returns:
        ボディのテキスト。フロントマターは含まない。
    """
    content = skill_md_path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(content, skill_md_path)
    return body or ""


def validate_skill_dir(skill_dir: Path) -> list[str]:
    """スキルディレクトリを検証し、エラーメッセージのリストを返す.

    エラーがない場合は空リストを返す。

    Args:
        skill_dir: 検証するスキルディレクトリ。

    Returns:
        エラーメッセージのリスト（空なら検証OK）。
    """
    errors: list[str] = []
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_dir.is_dir():
        errors.append(f"ディレクトリが存在しません: {skill_dir}")
        return errors

    if not skill_md_path.exists():
        errors.append(f"SKILL.md が存在しません: {skill_md_path}")
        return errors

    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except OSError as e:
        errors.append(f"ファイル読み込みエラー: {e}")
        return errors

    frontmatter, _ = _split_frontmatter(content, skill_md_path)
    if frontmatter is None:
        errors.append("フロントマターのパースに失敗しました")
        return errors

    # 必須フィールドチェック
    name: str | None = frontmatter.get("name")
    description: str | None = frontmatter.get("description")

    if not name:
        errors.append("必須フィールド 'name' がありません")
    else:
        name = str(name).strip()
        dir_name = skill_dir.name
        if name != dir_name:
            errors.append(
                f"'name' ({name!r}) がディレクトリ名 ({dir_name!r}) と一致しません"
            )
        name_errors = _validate_name(name)
        errors.extend(name_errors)

    if not description:
        errors.append("必須フィールド 'description' がありません")
    else:
        desc_str = str(description).strip()
        if len(desc_str) > _MAX_DESC_LEN:
            errors.append(
                f"'description' が最大文字数 ({_MAX_DESC_LEN}) を超えています"
            )

    return errors


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _split_frontmatter(
    content: str,
    skill_md_path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """SKILL.md の内容をフロントマターとボディに分割する."""
    stripped = content.lstrip()
    if not stripped.startswith("---"):
        logger.warning(
            "SKILL.md にフロントマターがありません: %s", skill_md_path
        )
        return None, None

    # 最初の --- 以降のコンテンツを取得
    rest = stripped[3:]
    end_idx = rest.find("\n---")
    if end_idx == -1:
        logger.warning(
            "SKILL.md のフロントマター終端 (---) が見つかりません: %s", skill_md_path
        )
        return None, None

    yaml_str = rest[:end_idx]
    body = rest[end_idx + 4:].lstrip("\n")

    try:
        frontmatter: dict[str, Any] = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError as e:
        logger.warning(
            "SKILL.md の YAML パースに失敗しました: %s: %s", skill_md_path, e
        )
        return None, None

    return frontmatter, body


def _validate_name(name: str) -> list[str]:
    """name フィールドの命名規則を検証する."""
    errors: list[str] = []
    if len(name) > _MAX_NAME_LEN:
        errors.append(f"'name' が最大文字数 ({_MAX_NAME_LEN}) を超えています: {name!r}")
    if not _NAME_PATTERN.match(name):
        errors.append(
            f"'name' 命名規則違反（小文字英数字+ハイフンのみ）: {name!r}"
        )
    return errors


def _validate_frontmatter(
    frontmatter: dict[str, Any],
    skill_dir: Path,
    scope: Literal["project", "global"],
    skill_md_path: Path,
) -> SkillMetadata | None:
    """フロントマターのバリデーションを行い SkillMetadata を返す."""
    # 必須フィールド
    name = frontmatter.get("name")
    description = frontmatter.get("description")

    if not name:
        logger.warning(
            "SKILL.md に必須フィールド 'name' がありません: %s", skill_md_path
        )
        return None
    if not description:
        logger.warning(
            "SKILL.md に必須フィールド 'description' がありません: %s", skill_md_path
        )
        return None

    name = str(name).strip()
    description = str(description).strip()

    # name のバリデーション
    name_errors = _validate_name(name)
    for err in name_errors:
        logger.warning("SKILL.md 命名規則違反 (%s): %s", skill_md_path, err)
    if name_errors:
        return None

    # name とディレクトリ名の一致確認
    dir_name = skill_dir.name
    if name != dir_name:
        logger.warning(
            "SKILL.md の 'name' (%r) がディレクトリ名 (%r) と一致しません: %s",
            name,
            dir_name,
            skill_md_path,
        )
        return None

    # description の長さチェック
    if len(description) > _MAX_DESC_LEN:
        logger.warning(
            "SKILL.md の 'description' が最大文字数 (%d) を超えています: %s",
            _MAX_DESC_LEN,
            skill_md_path,
        )
        return None

    # オプションフィールド
    license_val: str | None = frontmatter.get("license")
    compatibility: str | None = frontmatter.get("compatibility")
    raw_metadata = frontmatter.get("metadata", {})
    meta_dict: dict[str, str] = (
        {str(k): str(v) for k, v in raw_metadata.items()}
        if isinstance(raw_metadata, dict)
        else {}
    )

    # allowed-tools: スペース区切りのツール名リスト
    raw_tools = frontmatter.get("allowed-tools", "")
    allowed_tools: list[str] = (
        str(raw_tools).split() if raw_tools else []
    )

    return SkillMetadata(
        name=name,
        description=description,
        skill_dir=skill_dir,
        scope=scope,
        license=str(license_val).strip() if license_val else None,
        compatibility=str(compatibility).strip() if compatibility else None,
        metadata=meta_dict,
        allowed_tools=allowed_tools,
    )
