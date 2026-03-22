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

    # コピー前なのでディレクトリ名チェックをスキップ（インストール先は meta.name で決まる）
    meta = parse_skill_md(skill_md, "global", require_dir_match=False)
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

    リポジトリ内に複数のスキルがある場合、最初に見つかった1つをインストールする。
    全スキルをインストールするには install_all_from_git を使用すること。

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
        all_skills = _find_all_skill_roots(tmp_path)
        if not all_skills:
            msg = f"Git リポジトリ内に SKILL.md が見つかりません: {url}"
            raise ValueError(msg)

        if len(all_skills) > 1:
            names = [s.name for s in all_skills]
            logger.info(
                "リポジトリ内に複数のスキルが見つかりました: %s。"
                "最初のスキル (%s) をインストールします。"
                "全てインストールする場合は各スキルのパスを個別に指定してください。",
                names,
                names[0],
            )

        return install_from_path(all_skills[0], target_dir)


def install_all_from_git(url: str, target_dir: Path) -> list[SkillMetadata]:
    """Git リポジトリ内の全スキルをインストールする.

    Args:
        url: Git リポジトリの URL。
        target_dir: インストール先のスキルズディレクトリ（例: ~/.myagent/skills）。

    Returns:
        インストールされたスキルのメタデータリスト。

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

        all_skills = _find_all_skill_roots(tmp_path)
        if not all_skills:
            msg = f"Git リポジトリ内に SKILL.md が見つかりません: {url}"
            raise ValueError(msg)

        results: list[SkillMetadata] = []
        for skill_src in all_skills:
            try:
                meta = install_from_path(skill_src, target_dir)
                results.append(meta)
                logger.info("スキルをインストールしました: %s", meta.name)
            except (ValueError, OSError) as e:
                logger.warning("スキル '%s' のインストールに失敗しました: %s", skill_src.name, e)

        if not results:
            msg = f"全スキルのインストールに失敗しました: {url}"
            raise ValueError(msg)

        return results


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
    """リポジトリ内でスキルルート（SKILL.md が存在するディレクトリ）を探す.

    複数スキルが存在する場合は最初の1つを返す。
    全スキルを取得するには _find_all_skill_roots を使用すること。
    """
    results = _find_all_skill_roots(repo_path)
    return results[0] if results else None


def _find_all_skill_roots(repo_path: Path) -> list[Path]:
    """リポジトリ内の全スキルルート（SKILL.md が存在するディレクトリ）を返す.

    以下の構造を認識する:
    - 単一スキルリポジトリ: <root>/SKILL.md
    - コレクション（1階層）: <root>/<skill>/SKILL.md
    - コレクション（2階層）: <root>/<group>/<skill>/SKILL.md
      例: anthropics/skills の skills/<skill-name>/SKILL.md
    """
    # 1. リポジトリルート直下に SKILL.md がある場合（単一スキルリポジトリ）
    if (repo_path / "SKILL.md").exists():
        return [repo_path]

    results: list[Path] = []
    for subdir in sorted(repo_path.iterdir()):
        if not subdir.is_dir():
            continue
        if (subdir / "SKILL.md").exists():
            # 2. 1階層目に SKILL.md がある（例: template/SKILL.md）
            results.append(subdir)
        else:
            # 3. 2階層目に SKILL.md がある（例: skills/<name>/SKILL.md）
            for nested in sorted(subdir.iterdir()):
                if nested.is_dir() and (nested / "SKILL.md").exists():
                    results.append(nested)

    return results
