"""plugins/loader.py のユニットテスト."""

from __future__ import annotations

import json
from pathlib import Path

from myagent.plugins.loader import (
    detect_components,
    parse_plugin_manifest,
    validate_plugin_dir,
)


def _write_plugin_json(plugin_root: Path, data: dict, *, use_claude_dir: bool = False) -> Path:
    """テスト用 plugin.json を作成する."""
    plugin_root.mkdir(parents=True, exist_ok=True)
    if use_claude_dir:
        manifest_dir = plugin_root / ".claude-plugin"
        manifest_dir.mkdir(exist_ok=True)
        path = manifest_dir / "plugin.json"
    else:
        path = plugin_root / "plugin.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestParsePluginManifest:
    """parse_plugin_manifest のテスト."""

    def test_valid_manifest_claude_dir(self, tmp_path: Path) -> None:
        """.claude-plugin/plugin.json を正常にパースできること."""
        plugin_root = tmp_path / "my-plugin"
        _write_plugin_json(
            plugin_root,
            {
                "name": "my-plugin",
                "version": "1.0.0",
                "description": "テストプラグイン",
                "author": {"name": "Test User", "email": "test@example.com"},
                "license": "MIT",
                "keywords": ["test", "plugin"],
            },
            use_claude_dir=True,
        )

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is not None
        assert manifest.name == "my-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.description == "テストプラグイン"
        assert manifest.author is not None
        assert manifest.author.name == "Test User"
        assert manifest.author.email == "test@example.com"
        assert manifest.license == "MIT"
        assert manifest.keywords == ["test", "plugin"]

    def test_valid_manifest_root(self, tmp_path: Path) -> None:
        """プラグインルート直下の plugin.json を正常にパースできること."""
        plugin_root = tmp_path / "another-plugin"
        _write_plugin_json(plugin_root, {"name": "another-plugin"})

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is not None
        assert manifest.name == "another-plugin"

    def test_claude_dir_takes_priority(self, tmp_path: Path) -> None:
        """.claude-plugin/plugin.json が優先されること."""
        plugin_root = tmp_path / "priority-test"
        # 両方作成
        _write_plugin_json(plugin_root, {"name": "wrong-name"})
        _write_plugin_json(plugin_root, {"name": "priority-test"}, use_claude_dir=True)

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is not None
        assert manifest.name == "priority-test"

    def test_no_manifest_uses_dir_name(self, tmp_path: Path) -> None:
        """plugin.json 不在時にディレクトリ名を name として使用すること."""
        plugin_root = tmp_path / "auto-name"
        plugin_root.mkdir()

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is not None
        assert manifest.name == "auto-name"

    def test_no_manifest_invalid_dir_name(self, tmp_path: Path) -> None:
        """plugin.json 不在でディレクトリ名が不正な場合に None を返すこと."""
        plugin_root = tmp_path / "Invalid_Name"
        plugin_root.mkdir()

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is None

    def test_author_as_string(self, tmp_path: Path) -> None:
        """author が文字列の場合も正常にパースできること."""
        plugin_root = tmp_path / "str-author"
        _write_plugin_json(plugin_root, {"name": "str-author", "author": "Alice"})

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is not None
        assert manifest.author is not None
        assert manifest.author.name == "Alice"
        assert manifest.author.email is None

    def test_custom_paths(self, tmp_path: Path) -> None:
        """カスタムパスが正しくパースされること."""
        plugin_root = tmp_path / "custom-paths"
        _write_plugin_json(
            plugin_root,
            {
                "name": "custom-paths",
                "skills": ["./custom-skills"],
                "mcpServers": ["./my-mcp.json"],
            },
        )

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is not None
        assert manifest.skills == ["./custom-skills"]
        assert manifest.mcp_servers == ["./my-mcp.json"]

    def test_invalid_name_uppercase(self, tmp_path: Path) -> None:
        """大文字を含む name の場合に None を返すこと."""
        plugin_root = tmp_path / "bad-plugin"
        _write_plugin_json(plugin_root, {"name": "BadPlugin"})

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is None

    def test_invalid_name_double_hyphen(self, tmp_path: Path) -> None:
        """連続ハイフンを含む name の場合に None を返すこと."""
        plugin_root = tmp_path / "bad-plugin"
        _write_plugin_json(plugin_root, {"name": "bad--plugin"})

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is None

    def test_invalid_json(self, tmp_path: Path) -> None:
        """不正な JSON の場合に None を返すこと."""
        plugin_root = tmp_path / "bad-json"
        plugin_root.mkdir()
        (plugin_root / "plugin.json").write_text("{invalid json}", encoding="utf-8")

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is None

    def test_name_derived_from_dir_when_absent_in_json(self, tmp_path: Path) -> None:
        """plugin.json に name がない場合にディレクトリ名から導出すること."""
        plugin_root = tmp_path / "dir-name"
        _write_plugin_json(plugin_root, {"description": "no name"})

        manifest = parse_plugin_manifest(plugin_root)

        assert manifest is not None
        assert manifest.name == "dir-name"


class TestDetectComponents:
    """detect_components のテスト."""

    def test_detect_default_skills_dir(self, tmp_path: Path) -> None:
        """デフォルトの skills/ ディレクトリを検出すること."""
        plugin_root = tmp_path / "my-plugin"
        skills_dir = plugin_root / "skills"
        skills_dir.mkdir(parents=True)

        from myagent.plugins.models import PluginManifest
        manifest = PluginManifest(name="my-plugin")
        meta = detect_components(plugin_root, manifest)

        assert skills_dir in meta.skill_dirs

    def test_detect_default_mcp_json(self, tmp_path: Path) -> None:
        """デフォルトの .mcp.json を検出すること."""
        plugin_root = tmp_path / "my-plugin"
        plugin_root.mkdir()
        mcp_file = plugin_root / ".mcp.json"
        mcp_file.write_text("{}", encoding="utf-8")

        from myagent.plugins.models import PluginManifest
        manifest = PluginManifest(name="my-plugin")
        meta = detect_components(plugin_root, manifest)

        assert meta.mcp_config_file == mcp_file

    def test_detect_default_hooks(self, tmp_path: Path) -> None:
        """デフォルトの hooks/hooks.json を検出すること."""
        plugin_root = tmp_path / "my-plugin"
        hooks_dir = plugin_root / "hooks"
        hooks_dir.mkdir(parents=True)
        hooks_file = hooks_dir / "hooks.json"
        hooks_file.write_text("{}", encoding="utf-8")

        from myagent.plugins.models import PluginManifest
        manifest = PluginManifest(name="my-plugin")
        meta = detect_components(plugin_root, manifest)

        assert hooks_file in meta.hook_files

    def test_detect_agent_files(self, tmp_path: Path) -> None:
        """agents/ 内の .md ファイルを検出すること."""
        plugin_root = tmp_path / "my-plugin"
        agents_dir = plugin_root / "agents"
        agents_dir.mkdir(parents=True)
        agent_file = agents_dir / "my-agent.md"
        agent_file.write_text("# Agent", encoding="utf-8")

        from myagent.plugins.models import PluginManifest
        manifest = PluginManifest(name="my-plugin")
        meta = detect_components(plugin_root, manifest)

        assert agent_file in meta.agent_files

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        """プラグインルート外のパスは無視されること."""
        plugin_root = tmp_path / "my-plugin"
        plugin_root.mkdir()

        from myagent.plugins.models import PluginManifest
        manifest = PluginManifest(name="my-plugin", skills=["../../outside"])
        meta = detect_components(plugin_root, manifest)

        assert not meta.skill_dirs


class TestValidatePluginDir:
    """validate_plugin_dir のテスト."""

    def test_valid_plugin(self, tmp_path: Path) -> None:
        """正常なプラグインディレクトリはエラーなし."""
        plugin_root = tmp_path / "valid-plugin"
        _write_plugin_json(plugin_root, {"name": "valid-plugin"})

        errors = validate_plugin_dir(plugin_root)

        assert errors == []

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        """存在しないディレクトリはエラーあり."""
        errors = validate_plugin_dir(tmp_path / "nonexistent")

        assert len(errors) > 0

    def test_invalid_name(self, tmp_path: Path) -> None:
        """不正な name はエラーあり."""
        plugin_root = tmp_path / "bad"
        _write_plugin_json(plugin_root, {"name": "Bad_Name"})

        errors = validate_plugin_dir(plugin_root)

        assert len(errors) > 0
