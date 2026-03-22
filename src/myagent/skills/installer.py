"""スキルのインストール・アンインストール."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from myagent.skills.loader import parse_skill_md
from myagent.skills.models import SkillMetadata

logger = logging.getLogger(__name__)


def install_from_path(src: Path, target_dir: Path) -> SkillMetadata:
    """ローカルディレクトリからスキルをインストールする.

    Args:
        src: コピー元のスキルディレクトリ（SKILL.md が存在すること）。
        target_dir: インストール先のスキルズディレクトリ（例: ~/.myagent/skills）。

    Returns:
        インストールされたスキルのメタデータ。

    Raises:
        ValueError: src に SKILL.md がない、またはバリデーションエラーの場合。
        OSError: コピーに失敗した場合。
    """
    skill_md = src / "SKILL.md"
    if not skill_md.exists():
        msg = f"SKILL.md が見つかりません: {skill_md}"
        raise ValueError(msg)

    meta = parse_skill_md(skill_md, "global")
    if meta is None:
        msg = f"スキルのバリデーションに失敗しました: {src}"
        raise ValueError(msg)

    dest = target_dir / meta.name
    if dest.exists():
        shutil.rmtree(dest)

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)

    # インストール先のパスでメタデータを再取得
    installed_meta = parse_skill_md(dest / "SKILL.md", "global")
    if installed_meta is None:
        msg = f"インストール後のバリデーションに失敗しました: {dest}"
        raise ValueError(msg)

    logger.info("スキルをインストールしました: %s -> %s", src, dest)
    return installed_meta


def install_from_git(url: str, target_dir: Path) -> SkillMetadata:
    """Git リポジトリからスキルをインストールする.

    Args:
        url: Git リポジトリの URL。
        target_dir: インストール先のスキルズディレクトリ（例: ~/.myagent/skills）。

    Returns:
        インストールされたスキルのメタデータ。

    Raises:
        ValueError: SKILL.md が見つからない、またはバリデーションエラーの場合。
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

        # リポジトリルートか、その直下に SKILL.md があるかを確認
        skill_src = _find_skill_root(tmp_path)
        if skill_src is None:
            msg = f"Git リポジトリ内に SKILL.md が見つかりません: {url}"
            raise ValueError(msg)

        return install_from_path(skill_src, target_dir)


def uninstall(name: str, skills_dir: Path) -> bool:
    """スキルをアンインストールする.

    Args:
        name: スキル名。
        skills_dir: スキルズディレクトリ（例: ~/.myagent/skills）。

    Returns:
        削除に成功した場合は True、スキルが存在しない場合は False。
    """
    skill_dir = skills_dir / name
    if not skill_dir.exists():
        logger.warning("スキルが見つかりません: %s", name)
        return False

    shutil.rmtree(skill_dir)
    logger.info("スキルを削除しました: %s", skill_dir)
    return True


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


def _find_skill_root(repo_path: Path) -> Path | None:
    """リポジトリ内でスキルルート（SKILL.md が存在するディレクトリ）を探す."""
    # 1. リポジトリルート直下に SKILL.md がある場合
    if (repo_path / "SKILL.md").exists():
        return repo_path

    # 2. リポジトリ直下のサブディレクトリに SKILL.md がある場合
    for subdir in sorted(repo_path.iterdir()):
        if subdir.is_dir() and (subdir / "SKILL.md").exists():
            return subdir

    return None
