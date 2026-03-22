"""プラグインデータモデル定義."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class PluginAuthor:
    """プラグイン作者情報."""

    name: str
    email: str | None = None
    url: str | None = None


@dataclass
class PluginManifest:
    """plugin.json のデータモデル.

    name は kebab-case（小文字英数字+ハイフン）必須。
    その他のフィールドはオプション。
    """

    name: str
    version: str | None = None
    description: str | None = None
    author: PluginAuthor | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    keywords: list[str] = field(default_factory=list)
    # カスタムパス（プラグインルートからの相対パス、デフォルトパスを補足）
    skills: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)


@dataclass
class PluginMetadata:
    """ロード済みプラグインのメタデータ.

    起動時にロードされ、コンポーネントパスを保持する。
    """

    manifest: PluginManifest
    plugin_root: Path
    enabled: bool = True
    scope: Literal["user", "project", "local"] = "user"
    skill_dirs: list[Path] = field(default_factory=list)
    agent_files: list[Path] = field(default_factory=list)
    hook_files: list[Path] = field(default_factory=list)
    mcp_config_file: Path | None = None

    @property
    def name(self) -> str:
        """プラグイン名を返す."""
        return self.manifest.name

    @property
    def version(self) -> str | None:
        """バージョンを返す."""
        return self.manifest.version

    @property
    def description(self) -> str | None:
        """説明を返す."""
        return self.manifest.description
