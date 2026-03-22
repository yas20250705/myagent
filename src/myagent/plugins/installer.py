"""プラグインのインストール・アンインストール・更新."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from myagent.plugins.loader import detect_components, parse_plugin_manifest
from myagent.plugins.models import PluginMetadata

logger = logging.getLogger(__name__)

_DEFAULT_PLUGIN_CACHE_DIR = Path.home() / ".myagent" / "plugins" / "cache"
_DEFAULT_PLUGIN_DATA_DIR = Path.home() / ".myagent" / "plugins" / "data"


def install_from_path(src: Path, cache_dir: Path | None = None) -> PluginMetadata:
    """ローカルパスからプラグインをキャッシュへインストールする.

    Args:
        src: コピー元のプラグインディレクトリ。
        cache_dir: インストール先のキャッシュディレクトリ。
                   None の場合は ~/.myagent/plugins/cache を使用。

    Returns:
        インストールされたプラグインのメタデータ。

    Raises:
        ValueError: マニフェストのバリデーションエラーの場合。
        OSError: ファイルコピーに失敗した場合。
    """
    target = cache_dir or _DEFAULT_PLUGIN_CACHE_DIR

    if not src.is_dir():
        msg = f"ソースディレクトリが存在しません: {src}"
        raise ValueError(msg)

    manifest = parse_plugin_manifest(src)
    if manifest is None:
        msg = f"プラグインのバリデーションに失敗しました: {src}"
        raise ValueError(msg)

    dest = target / manifest.name
    if dest.exists():
        shutil.rmtree(dest)

    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)

    # インストール先のパスでメタデータを再取得
    installed_manifest = parse_plugin_manifest(dest)
    if installed_manifest is None:
        msg = f"インストール後のバリデーションに失敗しました: {dest}"
        raise ValueError(msg)

    meta = detect_components(dest, installed_manifest)
    logger.info("プラグインをインストールしました: %s -> %s", src, dest)
    return meta


def install_from_git(url: str, cache_dir: Path | None = None) -> PluginMetadata:
    """Git リポジトリからプラグインをインストールする.

    Args:
        url: Git リポジトリの URL。
        cache_dir: インストール先のキャッシュディレクトリ。
                   None の場合は ~/.myagent/plugins/cache を使用。

    Returns:
        インストールされたプラグインのメタデータ。

    Raises:
        ValueError: プラグインが見つからない、またはバリデーションエラーの場合。
        RuntimeError: git コマンドの実行に失敗した場合。
        OSError: ファイル操作に失敗した場合。
    """
    _check_git_available()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "repo"
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(tmp_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            msg = f"git clone に失敗しました: {url}\n{e.stderr}"
            raise RuntimeError(msg) from e

        plugin_src = _find_plugin_root(tmp_path)
        if plugin_src is None:
            msg = f"Git リポジトリ内にプラグインが見つかりません: {url}"
            raise ValueError(msg)

        return install_from_path(plugin_src, cache_dir)


def uninstall(
    name: str,
    cache_dir: Path | None = None,
    data_dir: Path | None = None,
    keep_data: bool = False,
) -> bool:
    """プラグインをアンインストールする.

    Args:
        name: アンインストールするプラグイン名。
        cache_dir: キャッシュディレクトリ。None の場合はデフォルトを使用。
        data_dir: データディレクトリ。None の場合はデフォルトを使用。
        keep_data: True の場合、プラグインデータを保持する。

    Returns:
        削除に成功した場合は True、プラグインが存在しない場合は False。
    """
    target = cache_dir or _DEFAULT_PLUGIN_CACHE_DIR
    plugin_cache = target / name

    if not plugin_cache.exists():
        logger.warning("プラグインが見つかりません: %s", name)
        return False

    shutil.rmtree(plugin_cache)
    logger.info("プラグインキャッシュを削除しました: %s", plugin_cache)

    if not keep_data:
        data_target = data_dir or _DEFAULT_PLUGIN_DATA_DIR
        plugin_data = data_target / name
        if plugin_data.exists():
            shutil.rmtree(plugin_data)
            logger.info("プラグインデータを削除しました: %s", plugin_data)

    return True


def update_from_git(
    name: str,
    url: str,
    cache_dir: Path | None = None,
) -> PluginMetadata:
    """Git プラグインを最新バージョンに更新する.

    既存プラグインをアンインストールせずに上書きインストールする。

    Args:
        name: 更新するプラグイン名。
        url: Git リポジトリの URL。
        cache_dir: キャッシュディレクトリ。None の場合はデフォルトを使用。

    Returns:
        更新後のプラグインメタデータ。

    Raises:
        ValueError: プラグインが見つからない、またはバリデーションエラーの場合。
        RuntimeError: git コマンドの実行に失敗した場合。
    """
    target = cache_dir or _DEFAULT_PLUGIN_CACHE_DIR
    plugin_cache = target / name

    if not plugin_cache.exists():
        msg = f"更新対象のプラグインが見つかりません: {name}"
        raise ValueError(msg)

    return install_from_git(url, cache_dir)


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _check_git_available() -> None:
    """git コマンドが使用可能か確認する."""
    try:
        subprocess.run(
            ["git", "--version"],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        msg = "git コマンドが見つかりません。git をインストールしてください。"
        raise RuntimeError(msg) from e


def _find_plugin_root(repo_path: Path) -> Path | None:
    """リポジトリ内でプラグインルートを探す.

    検索順序:
    1. リポジトリルート直下に .claude-plugin/plugin.json または plugin.json がある
    2. リポジトリ直下のサブディレクトリに同様のファイルがある
    """
    if _has_plugin_manifest(repo_path):
        return repo_path

    for subdir in sorted(repo_path.iterdir()):
        if subdir.is_dir() and _has_plugin_manifest(subdir):
            return subdir

    return None


def _has_plugin_manifest(path: Path) -> bool:
    """ディレクトリにプラグインマニフェストが存在するか確認する."""
    return (
        (path / ".claude-plugin" / "plugin.json").exists()
        or (path / "plugin.json").exists()
    )
