"""plugins/manager.py のユニットテスト."""

from __future__ import annotations

import json
from pathlib import Path

from myagent.plugins.manager import PluginManager


def _create_plugin(cache_dir: Path, name: str, has_skills: bool = False, has_mcp: bool = False) -> Path:
    """テスト用プラグインをキャッシュに作成する."""
    plugin_root = cache_dir / name
    plugin_root.mkdir(parents=True)
    (plugin_root / "plugin.json").write_text(
        json.dumps({"name": name, "description": f"{name} plugin"}),
        encoding="utf-8",
    )
    if has_skills:
        (plugin_root / "skills").mkdir()
    if has_mcp:
        (plugin_root / ".mcp.json").write_text("{}", encoding="utf-8")
    return plugin_root


class TestPluginManagerLoadAll:
    """PluginManager.load_all のテスト."""

    def test_load_empty_cache(self, tmp_path: Path) -> None:
        """空のキャッシュは空リストを返すこと."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = PluginManager(plugin_cache_dir=cache_dir)

        result = manager.load_all()

        assert result == []

    def test_load_nonexistent_cache(self, tmp_path: Path) -> None:
        """存在しないキャッシュは空リストを返すこと."""
        manager = PluginManager(plugin_cache_dir=tmp_path / "nonexistent")

        result = manager.load_all()

        assert result == []

    def test_load_single_plugin(self, tmp_path: Path) -> None:
        """単一プラグインを正常にロードすること."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "my-plugin")
        manager = PluginManager(plugin_cache_dir=cache_dir)

        result = manager.load_all()

        assert len(result) == 1
        assert result[0].name == "my-plugin"

    def test_load_multiple_plugins(self, tmp_path: Path) -> None:
        """複数プラグインをロードすること."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "plugin-a")
        _create_plugin(cache_dir, "plugin-b")
        manager = PluginManager(plugin_cache_dir=cache_dir)

        result = manager.load_all()

        names = {m.name for m in result}
        assert names == {"plugin-a", "plugin-b"}

    def test_invalid_plugin_does_not_affect_others(self, tmp_path: Path) -> None:
        """無効なプラグインが他のプラグインのロードに影響しないこと."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "good-plugin")
        # 不正なプラグイン（命名規則違反のディレクトリ名で plugin.json なし）
        bad_dir = cache_dir / "BadPlugin"
        bad_dir.mkdir()
        manager = PluginManager(plugin_cache_dir=cache_dir)

        result = manager.load_all()

        assert len(result) == 1
        assert result[0].name == "good-plugin"

    def test_enabled_plugins_filter(self, tmp_path: Path) -> None:
        """enabled_plugins リストで有効化状態が制御されること."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "plugin-a")
        _create_plugin(cache_dir, "plugin-b")
        manager = PluginManager(
            plugin_cache_dir=cache_dir,
            enabled_plugins=["plugin-a"],
        )

        result = manager.load_all()

        enabled = [m for m in result if m.enabled]
        disabled = [m for m in result if not m.enabled]
        assert len(enabled) == 1
        assert enabled[0].name == "plugin-a"
        assert len(disabled) == 1
        assert disabled[0].name == "plugin-b"

    def test_all_enabled_when_none_specified(self, tmp_path: Path) -> None:
        """enabled_plugins が None の場合は全プラグインが有効."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "plugin-a")
        _create_plugin(cache_dir, "plugin-b")
        manager = PluginManager(plugin_cache_dir=cache_dir, enabled_plugins=None)

        result = manager.load_all()

        assert all(m.enabled for m in result)


class TestPluginManagerGetters:
    """PluginManager のゲッターメソッドのテスト."""

    def test_get_metadata_found(self, tmp_path: Path) -> None:
        """名前でプラグインを取得できること."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "my-plugin")
        manager = PluginManager(plugin_cache_dir=cache_dir)

        meta = manager.get_metadata("my-plugin")

        assert meta is not None
        assert meta.name == "my-plugin"

    def test_get_metadata_not_found(self, tmp_path: Path) -> None:
        """存在しないプラグインは None を返すこと."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = PluginManager(plugin_cache_dir=cache_dir)

        meta = manager.get_metadata("nonexistent")

        assert meta is None

    def test_get_skill_dirs_enabled_only(self, tmp_path: Path) -> None:
        """有効プラグインのスキルディレクトリのみ返すこと."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "plugin-with-skills", has_skills=True)
        _create_plugin(cache_dir, "plugin-disabled", has_skills=True)
        manager = PluginManager(
            plugin_cache_dir=cache_dir,
            enabled_plugins=["plugin-with-skills"],
        )
        manager.load_all()

        dirs = manager.get_skill_dirs()

        assert len(dirs) == 1
        assert dirs[0].parent.name == "plugin-with-skills"

    def test_get_mcp_configs_enabled_only(self, tmp_path: Path) -> None:
        """有効プラグインの MCP 設定のみ返すこと."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "plugin-with-mcp", has_mcp=True)
        _create_plugin(cache_dir, "plugin-disabled", has_mcp=True)
        manager = PluginManager(
            plugin_cache_dir=cache_dir,
            enabled_plugins=["plugin-with-mcp"],
        )
        manager.load_all()

        configs = manager.get_mcp_configs()

        assert len(configs) == 1
        assert configs[0].parent.name == "plugin-with-mcp"


class TestPluginManagerEnableDisable:
    """PluginManager の enable/disable のテスト."""

    def test_enable_plugin(self, tmp_path: Path) -> None:
        """プラグインを有効化できること."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "my-plugin")
        manager = PluginManager(
            plugin_cache_dir=cache_dir,
            enabled_plugins=[],
        )
        manager.load_all()

        result = manager.enable("my-plugin")

        assert result is True
        meta = manager.get_metadata("my-plugin")
        assert meta is not None
        assert meta.enabled is True

    def test_disable_plugin(self, tmp_path: Path) -> None:
        """プラグインを無効化できること."""
        cache_dir = tmp_path / "cache"
        _create_plugin(cache_dir, "my-plugin")
        manager = PluginManager(plugin_cache_dir=cache_dir, enabled_plugins=None)
        manager.load_all()

        result = manager.disable("my-plugin")

        assert result is True
        meta = manager.get_metadata("my-plugin")
        assert meta is not None
        assert meta.enabled is False

    def test_enable_nonexistent_returns_false(self, tmp_path: Path) -> None:
        """存在しないプラグインを有効化しようとすると False を返すこと."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = PluginManager(plugin_cache_dir=cache_dir)

        result = manager.enable("nonexistent")

        assert result is False

    def test_disable_nonexistent_returns_false(self, tmp_path: Path) -> None:
        """存在しないプラグインを無効化しようとすると False を返すこと."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        manager = PluginManager(plugin_cache_dir=cache_dir)

        result = manager.disable("nonexistent")

        assert result is False
