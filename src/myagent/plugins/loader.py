"""plugin.json のパース・バリデーション、コンポーネント検出."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from myagent.plugins.models import PluginAuthor, PluginManifest, PluginMetadata

logger = logging.getLogger(__name__)

# 命名規則: 小文字英数字 + ハイフン（先頭・末尾はハイフン不可、連続ハイフン不可）
_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_NAME_LEN = 64

# デフォルトコンポーネントパス
_DEFAULT_SKILLS_DIR = "skills"
_DEFAULT_AGENTS_DIR = "agents"
_DEFAULT_HOOKS_FILE = "hooks/hooks.json"
_DEFAULT_MCP_FILE = ".mcp.json"
_MANIFEST_DIR = ".claude-plugin"
_MANIFEST_FILE = "plugin.json"


def parse_plugin_manifest(plugin_root: Path) -> PluginManifest | None:
    """プラグインルートから plugin.json をパースして PluginManifest を返す.

    検索順序:
    1. `<plugin_root>/.claude-plugin/plugin.json`
    2. `<plugin_root>/plugin.json`
    3. 不在の場合: ディレクトリ名から name を導出し最小マニフェストを返す

    Args:
        plugin_root: プラグインのルートディレクトリ。

    Returns:
        パース済みの PluginManifest。バリデーションエラー時は None。
    """
    # 1. .claude-plugin/plugin.json を優先
    manifest_path = plugin_root / _MANIFEST_DIR / _MANIFEST_FILE
    if not manifest_path.exists():
        # 2. プラグインルート直下の plugin.json
        manifest_path = plugin_root / _MANIFEST_FILE

    if manifest_path.exists():
        return _parse_manifest_file(manifest_path, plugin_root)

    # 3. plugin.json 不在: ディレクトリ名から name を導出
    dir_name = plugin_root.name
    name_errors = _validate_name(dir_name)
    if name_errors:
        logger.warning(
            "プラグインディレクトリ名が命名規則に違反しています: %s: %s",
            plugin_root,
            ", ".join(name_errors),
        )
        return None

    logger.debug(
        "plugin.json が見つかりません。ディレクトリ名 %r を使用します: %s",
        dir_name,
        plugin_root,
    )
    return PluginManifest(name=dir_name)


def detect_components(plugin_root: Path, manifest: PluginManifest) -> PluginMetadata:
    """プラグインのコンポーネントを検出して PluginMetadata を返す.

    デフォルトパスとマニフェストのカスタムパスを組み合わせて検出する。
    カスタムパスはデフォルトを置換せず補足する。

    Args:
        plugin_root: プラグインのルートディレクトリ。
        manifest: パース済みの PluginManifest。

    Returns:
        コンポーネントパスを含む PluginMetadata。
    """
    skill_dirs: list[Path] = []
    agent_files: list[Path] = []
    hook_files: list[Path] = []
    mcp_config_file: Path | None = None

    # スキルディレクトリ（デフォルト: skills/）
    default_skills = plugin_root / _DEFAULT_SKILLS_DIR
    if default_skills.is_dir():
        skill_dirs.append(default_skills)
    for custom_path in manifest.skills:
        p = _resolve_plugin_path(plugin_root, custom_path)
        if p is not None and p.is_dir() and p not in skill_dirs:
            skill_dirs.append(p)

    # エージェントファイル（デフォルト: agents/*.md）
    default_agents = plugin_root / _DEFAULT_AGENTS_DIR
    if default_agents.is_dir():
        agent_files.extend(sorted(default_agents.glob("*.md")))
    for custom_path in manifest.agents:
        p = _resolve_plugin_path(plugin_root, custom_path)
        if p is not None and p.is_file() and p not in agent_files:
            agent_files.append(p)

    # フックファイル（デフォルト: hooks/hooks.json）
    default_hooks = plugin_root / _DEFAULT_HOOKS_FILE
    if default_hooks.exists():
        hook_files.append(default_hooks)
    for custom_path in manifest.hooks:
        p = _resolve_plugin_path(plugin_root, custom_path)
        if p is not None and p.is_file() and p not in hook_files:
            hook_files.append(p)

    # MCP設定ファイル（デフォルト: .mcp.json）
    default_mcp = plugin_root / _DEFAULT_MCP_FILE
    if default_mcp.exists():
        mcp_config_file = default_mcp
    elif manifest.mcp_servers:
        for custom_path in manifest.mcp_servers:
            p = _resolve_plugin_path(plugin_root, custom_path)
            if p is not None and p.is_file():
                mcp_config_file = p
                break

    return PluginMetadata(
        manifest=manifest,
        plugin_root=plugin_root,
        skill_dirs=skill_dirs,
        agent_files=agent_files,
        hook_files=hook_files,
        mcp_config_file=mcp_config_file,
    )


def validate_plugin_dir(plugin_root: Path) -> list[str]:
    """プラグインディレクトリを検証し、エラーメッセージのリストを返す.

    Args:
        plugin_root: 検証するプラグインディレクトリ。

    Returns:
        エラーメッセージのリスト（空なら検証OK）。
    """
    errors: list[str] = []

    if not plugin_root.is_dir():
        errors.append(f"ディレクトリが存在しません: {plugin_root}")
        return errors

    manifest = parse_plugin_manifest(plugin_root)
    if manifest is None:
        errors.append("マニフェストのパース・バリデーションに失敗しました")
        return errors

    # name の追加バリデーション
    name_errors = _validate_name(manifest.name)
    errors.extend(name_errors)

    return errors


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _parse_manifest_file(
    manifest_path: Path, plugin_root: Path
) -> PluginManifest | None:
    """plugin.json ファイルをパースして PluginManifest を返す."""
    try:
        content = manifest_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("plugin.json の読み込みに失敗しました: %s: %s", manifest_path, e)
        return None

    try:
        data: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(
            "plugin.json の JSON パースに失敗しました: %s: %s", manifest_path, e
        )
        return None

    if not isinstance(data, dict):
        logger.warning(
            "plugin.json の形式が不正です（オブジェクトが必要）: %s", manifest_path
        )
        return None

    # name フィールド（必須 or ディレクトリ名から導出）
    raw_name = data.get("name")
    if raw_name:
        name = str(raw_name).strip()
    else:
        name = plugin_root.name

    name_errors = _validate_name(name)
    if name_errors:
        for err in name_errors:
            logger.warning("plugin.json 命名規則違反 (%s): %s", manifest_path, err)
        return None

    # author フィールド（文字列またはオブジェクト）
    author: PluginAuthor | None = None
    raw_author = data.get("author")
    if isinstance(raw_author, str):
        author = PluginAuthor(name=raw_author)
    elif isinstance(raw_author, dict):
        author = PluginAuthor(
            name=str(raw_author.get("name", "")),
            email=raw_author.get("email"),
            url=raw_author.get("url"),
        )

    # keywords
    raw_keywords = data.get("keywords", [])
    keywords = [str(k) for k in raw_keywords] if isinstance(raw_keywords, list) else []

    # カスタムパス（リスト形式）
    def _str_list(key: str) -> list[str]:
        val = data.get(key, [])
        return [str(v) for v in val] if isinstance(val, list) else []

    return PluginManifest(
        name=name,
        version=_opt_str(data.get("version")),
        description=_opt_str(data.get("description")),
        author=author,
        homepage=_opt_str(data.get("homepage")),
        repository=_opt_str(data.get("repository")),
        license=_opt_str(data.get("license")),
        keywords=keywords,
        skills=_str_list("skills"),
        commands=_str_list("commands"),
        agents=_str_list("agents"),
        hooks=_str_list("hooks"),
        mcp_servers=_str_list("mcpServers"),
    )


def _validate_name(name: str) -> list[str]:
    """name フィールドの命名規則を検証する."""
    errors: list[str] = []
    if not name:
        errors.append("'name' が空です")
        return errors
    if len(name) > _MAX_NAME_LEN:
        errors.append(f"'name' が最大文字数 ({_MAX_NAME_LEN}) を超えています: {name!r}")
    if not _NAME_PATTERN.match(name):
        errors.append(
            f"'name' 命名規則違反（小文字英数字+ハイフンのみ）: {name!r}"
        )
    return errors


def _resolve_plugin_path(plugin_root: Path, relative: str) -> Path | None:
    """プラグインルートからの相対パスを解決し、パストラバーサルを防止する."""
    try:
        resolved = (plugin_root / relative).resolve()
        plugin_root_resolved = plugin_root.resolve()
        resolved.relative_to(plugin_root_resolved)
        return resolved
    except ValueError:
        logger.warning(
            "プラグインルート外のパスは許可されていません: %s (plugin_root=%s)",
            relative,
            plugin_root,
        )
        return None
    except OSError:
        return None


def _opt_str(val: Any) -> str | None:
    """値を str に変換する（None/空文字は None を返す）."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None
