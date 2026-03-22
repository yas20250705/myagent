"""plugins/installer.py のユニットテスト."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from myagent.plugins.installer import install_from_git, install_from_path, uninstall


def _create_plugin_src(base: Path, name: str) -> Path:
    """テスト用プラグインソースを作成する."""
    plugin_dir = base / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": name, "description": f"{name} plugin"}),
        encoding="utf-8",
    )
    return plugin_dir


class TestInstallFromPath:
    """install_from_path のテスト."""

    def test_install_valid_plugin(self, tmp_path: Path) -> None:
        """正常なプラグインをインストールできること."""
        src_dir = tmp_path / "src"
        src = _create_plugin_src(src_dir, "my-plugin")
        cache_dir = tmp_path / "cache"

        meta = install_from_path(src, cache_dir)

        assert meta.name == "my-plugin"
        assert (cache_dir / "my-plugin").is_dir()

    def test_install_creates_cache_dir(self, tmp_path: Path) -> None:
        """キャッシュディレクトリが自動作成されること."""
        src_dir = tmp_path / "src"
        src = _create_plugin_src(src_dir, "my-plugin")
        cache_dir = tmp_path / "nonexistent" / "cache"

        install_from_path(src, cache_dir)

        assert cache_dir.is_dir()

    def test_install_overwrites_existing(self, tmp_path: Path) -> None:
        """既存プラグインを上書きできること."""
        src_dir = tmp_path / "src"
        src = _create_plugin_src(src_dir, "my-plugin")
        cache_dir = tmp_path / "cache"

        # 1回目
        install_from_path(src, cache_dir)
        # 2回目（上書き）
        meta = install_from_path(src, cache_dir)

        assert meta.name == "my-plugin"

    def test_install_nonexistent_src(self, tmp_path: Path) -> None:
        """存在しないソースは ValueError を発生させること."""
        with pytest.raises(ValueError, match="ソースディレクトリが存在しません"):
            install_from_path(tmp_path / "nonexistent", tmp_path / "cache")

    def test_install_invalid_plugin(self, tmp_path: Path) -> None:
        """不正なプラグイン（命名規則違反）は ValueError を発生させること."""
        src = tmp_path / "BadPlugin"
        src.mkdir()
        (src / "plugin.json").write_text(
            json.dumps({"name": "BadPlugin"}), encoding="utf-8"
        )

        with pytest.raises(ValueError, match="バリデーション"):
            install_from_path(src, tmp_path / "cache")

    def test_installed_plugin_has_correct_root(self, tmp_path: Path) -> None:
        """インストール後のプラグインルートがキャッシュ内を指すこと."""
        src_dir = tmp_path / "src"
        src = _create_plugin_src(src_dir, "test-plugin")
        cache_dir = tmp_path / "cache"

        meta = install_from_path(src, cache_dir)

        assert meta.plugin_root == cache_dir / "test-plugin"


class TestUninstall:
    """uninstall のテスト."""

    def test_uninstall_existing_plugin(self, tmp_path: Path) -> None:
        """インストール済みプラグインをアンインストールできること."""
        src_dir = tmp_path / "src"
        src = _create_plugin_src(src_dir, "my-plugin")
        cache_dir = tmp_path / "cache"
        install_from_path(src, cache_dir)

        result = uninstall("my-plugin", cache_dir)

        assert result is True
        assert not (cache_dir / "my-plugin").exists()

    def test_uninstall_nonexistent_plugin(self, tmp_path: Path) -> None:
        """存在しないプラグインのアンインストールは False を返すこと."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        result = uninstall("nonexistent", cache_dir)

        assert result is False

    def test_uninstall_removes_data_by_default(self, tmp_path: Path) -> None:
        """デフォルトでデータも削除されること."""
        src_dir = tmp_path / "src"
        src = _create_plugin_src(src_dir, "my-plugin")
        cache_dir = tmp_path / "cache"
        data_dir = tmp_path / "data"
        install_from_path(src, cache_dir)
        # データディレクトリを作成
        (data_dir / "my-plugin").mkdir(parents=True)

        result = uninstall("my-plugin", cache_dir, data_dir, keep_data=False)

        assert result is True
        assert not (data_dir / "my-plugin").exists()

    def test_uninstall_keep_data(self, tmp_path: Path) -> None:
        """--keep-data でデータが保持されること."""
        src_dir = tmp_path / "src"
        src = _create_plugin_src(src_dir, "my-plugin")
        cache_dir = tmp_path / "cache"
        data_dir = tmp_path / "data"
        install_from_path(src, cache_dir)
        (data_dir / "my-plugin").mkdir(parents=True)

        result = uninstall("my-plugin", cache_dir, data_dir, keep_data=True)

        assert result is True
        assert (data_dir / "my-plugin").exists()


class TestInstallFromGit:
    """install_from_git のテスト（git コマンドをモック）."""

    def test_install_from_git_success(self, tmp_path: Path) -> None:
        """Git リポジトリからインストールできること."""
        cache_dir = tmp_path / "cache"

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "git" and cmd[1] == "--version":
                return MagicMock(returncode=0)
            if cmd[0] == "git" and cmd[1] == "clone":
                # clone 先にプラグインを作成
                dest = Path(cmd[-1])
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "plugin.json").write_text(
                    json.dumps({"name": "git-plugin"}), encoding="utf-8"
                )
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            meta = install_from_git("https://example.com/plugin.git", cache_dir)

        assert meta.name == "git-plugin"

    def test_install_from_git_clone_failure(self, tmp_path: Path) -> None:
        """git clone 失敗時に RuntimeError を発生させること."""
        cache_dir = tmp_path / "cache"

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "git" and cmd[1] == "--version":
                return MagicMock(returncode=0)
            raise subprocess.CalledProcessError(128, cmd, stderr="Connection refused")

        with patch("subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="git clone に失敗しました"):
                install_from_git("https://invalid.example.com/plugin.git", cache_dir)

    def test_install_from_git_no_plugin_found(self, tmp_path: Path) -> None:
        """リポジトリにプラグインが見つからない場合に ValueError を発生させること."""
        cache_dir = tmp_path / "cache"

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd[0] == "git" and cmd[1] == "--version":
                return MagicMock(returncode=0)
            if cmd[0] == "git" and cmd[1] == "clone":
                # plugin.json のない空のリポジトリ
                dest = Path(cmd[-1])
                dest.mkdir(parents=True, exist_ok=True)
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            with pytest.raises(ValueError, match="プラグインが見つかりません"):
                install_from_git("https://example.com/empty.git", cache_dir)

    def test_git_not_available(self, tmp_path: Path) -> None:
        """git コマンドが見つからない場合に RuntimeError を発生させること."""
        cache_dir = tmp_path / "cache"

        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            with pytest.raises(RuntimeError, match="git コマンドが見つかりません"):
                install_from_git("https://example.com/plugin.git", cache_dir)
