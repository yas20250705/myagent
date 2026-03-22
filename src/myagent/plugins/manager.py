"""プラグイン管理のコアクラス."""

from __future__ import annotations

import logging
from pathlib import Path

from myagent.plugins.loader import detect_components, parse_plugin_manifest
from myagent.plugins.models import PluginMetadata

logger = logging.getLogger(__name__)

_DEFAULT_PLUGIN_CACHE_DIR = Path.home() / ".myagent" / "plugins" / "cache"


class PluginManager:
    """プラグインの検出・ロード・有効化状態管理.

    起動時にキャッシュディレクトリを走査してメタデータをロードする。
    ロードエラーは警告ログのみで他のプラグインに影響しない。
    """

    def __init__(
        self,
        plugin_cache_dir: Path | None = None,
        enabled_plugins: list[str] | None = None,
    ) -> None:
        """初期化.

        Args:
            plugin_cache_dir: プラグインキャッシュディレクトリ。
                              None の場合は ~/.myagent/plugins/cache を使用。
            enabled_plugins: 有効なプラグイン名リスト。
                             None の場合は全プラグインを有効とみなす。
        """
        self._cache_dir = plugin_cache_dir or _DEFAULT_PLUGIN_CACHE_DIR
        self._enabled_plugins = (
            set(enabled_plugins) if enabled_plugins is not None else None
        )
        self._plugins: dict[str, PluginMetadata] = {}
        self._loaded = False

    def load_all(self) -> list[PluginMetadata]:
        """キャッシュ内の全プラグインをロードする.

        ロードエラーは警告ログのみで他のプラグインに影響しない。

        Returns:
            ロード済みプラグインのメタデータリスト。
        """
        self._plugins = {}

        if not self._cache_dir.is_dir():
            self._loaded = True
            return []

        for entry in sorted(self._cache_dir.iterdir()):
            if not entry.is_dir():
                continue
            try:
                manifest = parse_plugin_manifest(entry)
                if manifest is None:
                    logger.warning(
                        "プラグインのマニフェスト取得に失敗しました: %s", entry
                    )
                    continue
                meta = detect_components(entry, manifest)
                # 有効状態を設定
                if self._enabled_plugins is not None:
                    meta.enabled = manifest.name in self._enabled_plugins
                self._plugins[manifest.name] = meta
                logger.debug("プラグインをロードしました: %s", manifest.name)
            except Exception:
                logger.warning(
                    "プラグインのロード中にエラーが発生しました: %s",
                    entry,
                    exc_info=True,
                )

        self._loaded = True
        logger.debug("プラグインをロードしました: %d 個", len(self._plugins))
        return list(self._plugins.values())

    def get_all_metadata(self) -> list[PluginMetadata]:
        """ロード済み全プラグインのメタデータリストを返す."""
        if not self._loaded:
            self.load_all()
        return list(self._plugins.values())

    def get_metadata(self, name: str) -> PluginMetadata | None:
        """名前からプラグインのメタデータを取得する.

        Args:
            name: プラグイン名。

        Returns:
            見つかった場合は PluginMetadata、見つからない場合は None。
        """
        if not self._loaded:
            self.load_all()
        return self._plugins.get(name)

    def get_skill_dirs(self) -> list[Path]:
        """有効プラグインのスキルディレクトリリストを返す.

        Returns:
            有効プラグインが提供するスキルディレクトリのリスト。
        """
        if not self._loaded:
            self.load_all()
        dirs: list[Path] = []
        for meta in self._plugins.values():
            if meta.enabled:
                dirs.extend(meta.skill_dirs)
        return dirs

    def get_mcp_configs(self) -> list[Path]:
        """有効プラグインの MCP 設定ファイルリストを返す.

        Returns:
            有効プラグインが提供する .mcp.json ファイルのリスト。
        """
        if not self._loaded:
            self.load_all()
        configs: list[Path] = []
        for meta in self._plugins.values():
            if meta.enabled and meta.mcp_config_file is not None:
                configs.append(meta.mcp_config_file)
        return configs

    def enable(self, name: str) -> bool:
        """プラグインを有効化する.

        Args:
            name: プラグイン名。

        Returns:
            成功した場合は True、プラグインが見つからない場合は False。
        """
        if not self._loaded:
            self.load_all()
        meta = self._plugins.get(name)
        if meta is None:
            logger.warning("プラグインが見つかりません: %s", name)
            return False
        meta.enabled = True
        if self._enabled_plugins is not None:
            self._enabled_plugins.add(name)
        return True

    def disable(self, name: str) -> bool:
        """プラグインを無効化する.

        Args:
            name: プラグイン名。

        Returns:
            成功した場合は True、プラグインが見つからない場合は False。
        """
        if not self._loaded:
            self.load_all()
        meta = self._plugins.get(name)
        if meta is None:
            logger.warning("プラグインが見つかりません: %s", name)
            return False
        meta.enabled = False
        if self._enabled_plugins is not None:
            self._enabled_plugins.discard(name)
        return True
