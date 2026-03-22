"""installer.py のユニットテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from myagent.skills.installer import install_from_path, uninstall


def _make_skill_dir(base: Path, name: str, description: str = "テストスキル") -> Path:
    """テスト用スキルディレクトリを作成する."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""\
---
name: {name}
description: {description}
---

# {name}
""",
        encoding="utf-8",
    )
    return skill_dir


class TestInstallFromPath:
    """install_from_path のテスト."""

    def test_install_copies_skill(self, tmp_path: Path) -> None:
        """ローカルパスからスキルをコピーできること."""
        src = tmp_path / "source"
        skill_src = _make_skill_dir(src, "my-skill")
        target = tmp_path / "target"

        meta = install_from_path(skill_src, target)

        assert meta.name == "my-skill"
        assert (target / "my-skill" / "SKILL.md").exists()

    def test_install_overwrites_existing(self, tmp_path: Path) -> None:
        """既存のスキルを上書きインストールできること."""
        src = tmp_path / "source"
        skill_src = _make_skill_dir(src, "my-skill")
        target = tmp_path / "target"

        # 1回目インストール
        install_from_path(skill_src, target)
        # 2回目インストール（上書き）
        meta = install_from_path(skill_src, target)

        assert meta.name == "my-skill"

    def test_install_no_skill_md_raises(self, tmp_path: Path) -> None:
        """SKILL.md がないディレクトリは ValueError を送出すること."""
        src = tmp_path / "no-skill"
        src.mkdir()

        with pytest.raises(ValueError, match="SKILL.md"):
            install_from_path(src, tmp_path / "target")

    def test_install_invalid_skill_raises(self, tmp_path: Path) -> None:
        """バリデーションエラーは ValueError を送出すること."""
        src = tmp_path / "bad-skill"
        src.mkdir()
        (src / "SKILL.md").write_text("フロントマターなし", encoding="utf-8")

        with pytest.raises(ValueError, match="バリデーション"):
            install_from_path(src, tmp_path / "target")

    def test_install_creates_subdirectories(self, tmp_path: Path) -> None:
        """スキルのサブディレクトリもコピーされること."""
        src = tmp_path / "source"
        skill_src = _make_skill_dir(src, "my-skill")
        (skill_src / "scripts").mkdir()
        (skill_src / "scripts" / "run.sh").write_text("#!/bin/bash", encoding="utf-8")
        target = tmp_path / "target"

        install_from_path(skill_src, target)

        assert (target / "my-skill" / "scripts" / "run.sh").exists()


class TestUninstall:
    """uninstall のテスト."""

    def test_uninstall_removes_skill(self, tmp_path: Path) -> None:
        """スキルを削除できること."""
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")

        result = uninstall("my-skill", skills_dir)

        assert result is True
        assert not skill_dir.exists()

    def test_uninstall_nonexistent_returns_false(self, tmp_path: Path) -> None:
        """存在しないスキルの削除は False を返すこと."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        result = uninstall("not-exist", skills_dir)

        assert result is False
