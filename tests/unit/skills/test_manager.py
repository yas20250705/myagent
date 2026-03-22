"""manager.py のユニットテスト."""

from __future__ import annotations

from pathlib import Path

from myagent.skills.manager import SkillManager


def _make_skill(skills_dir: Path, name: str, description: str) -> Path:
    """テスト用スキルを作成する."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""\
---
name: {name}
description: {description}
---

# {name}

ボディテキスト
""",
        encoding="utf-8",
    )
    return skill_dir


class TestSkillManagerLoadAll:
    """load_all のテスト."""

    def test_load_from_project_dir(self, tmp_path: Path) -> None:
        """プロジェクトローカルスキルをロードできること."""
        project_dir = tmp_path / "project" / "skills"
        _make_skill(project_dir, "my-skill", "テストスキル")

        manager = SkillManager(project_skills_dir=project_dir)
        skills = manager.load_all()

        assert len(skills) == 1
        assert skills[0].name == "my-skill"
        assert skills[0].scope == "project"

    def test_load_from_global_dir(self, tmp_path: Path) -> None:
        """グローバルスキルをロードできること."""
        global_dir = tmp_path / "global" / "skills"
        _make_skill(global_dir, "global-skill", "グローバルスキル")

        manager = SkillManager(global_skills_dir=global_dir)
        skills = manager.load_all()

        assert len(skills) == 1
        assert skills[0].name == "global-skill"
        assert skills[0].scope == "global"

    def test_project_overrides_global(self, tmp_path: Path) -> None:
        """同名スキルはプロジェクトローカルが優先されること."""
        project_dir = tmp_path / "project" / "skills"
        global_dir = tmp_path / "global" / "skills"
        _make_skill(project_dir, "common-skill", "プロジェクト版")
        _make_skill(global_dir, "common-skill", "グローバル版")

        manager = SkillManager(
            project_skills_dir=project_dir,
            global_skills_dir=global_dir,
        )
        skills = manager.load_all()

        assert len(skills) == 1
        assert skills[0].description == "プロジェクト版"
        assert skills[0].scope == "project"

    def test_load_multiple_skills(self, tmp_path: Path) -> None:
        """複数スキルをロードできること."""
        project_dir = tmp_path / "skills"
        _make_skill(project_dir, "skill-a", "スキルA")
        _make_skill(project_dir, "skill-b", "スキルB")

        manager = SkillManager(project_skills_dir=project_dir)
        skills = manager.load_all()

        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"skill-a", "skill-b"}

    def test_invalid_skill_skipped(self, tmp_path: Path) -> None:
        """無効なスキル（nameなど欠落）はスキップされること."""
        project_dir = tmp_path / "skills"
        _make_skill(project_dir, "valid-skill", "有効なスキル")
        # 無効なスキル（フロントマターなし）
        bad_dir = project_dir / "bad-skill"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_text("フロントマターなし", encoding="utf-8")

        manager = SkillManager(project_skills_dir=project_dir)
        skills = manager.load_all()

        assert len(skills) == 1
        assert skills[0].name == "valid-skill"

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        """スキルが存在しない場合は空リストを返すこと."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        manager = SkillManager(project_skills_dir=empty_dir)
        skills = manager.load_all()

        assert skills == []

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path) -> None:
        """存在しないディレクトリは空リストを返すこと."""
        manager = SkillManager(project_skills_dir=tmp_path / "not-exist")
        skills = manager.load_all()

        assert skills == []


class TestSkillManagerGetMetadata:
    """get_metadata のテスト."""

    def test_get_existing_skill(self, tmp_path: Path) -> None:
        """存在するスキルのメタデータを取得できること."""
        project_dir = tmp_path / "skills"
        _make_skill(project_dir, "my-skill", "テストスキル")

        manager = SkillManager(project_skills_dir=project_dir)
        meta = manager.get_metadata("my-skill")

        assert meta is not None
        assert meta.name == "my-skill"

    def test_get_nonexistent_skill_returns_none(self, tmp_path: Path) -> None:
        """存在しないスキルは None を返すこと."""
        manager = SkillManager(project_skills_dir=tmp_path / "empty")

        meta = manager.get_metadata("not-exist")

        assert meta is None


class TestSkillManagerActivate:
    """activate のテスト."""

    def test_activate_returns_skill_with_body(self, tmp_path: Path) -> None:
        """アクティベートでボディを含む Skill を返すこと."""
        project_dir = tmp_path / "skills"
        _make_skill(project_dir, "my-skill", "テストスキル")

        manager = SkillManager(project_skills_dir=project_dir)
        skill = manager.activate("my-skill")

        assert skill is not None
        assert skill.meta.name == "my-skill"
        assert "ボディテキスト" in skill.body

    def test_activate_nonexistent_returns_none(self, tmp_path: Path) -> None:
        """存在しないスキルのアクティベートは None を返すこと."""
        manager = SkillManager(project_skills_dir=tmp_path / "empty")

        skill = manager.activate("not-exist")

        assert skill is None


class TestSkillManagerFindMatching:
    """find_matching のテスト."""

    def test_matching_by_keyword(self, tmp_path: Path) -> None:
        """指示文のキーワードにマッチするスキルを返すこと."""
        project_dir = tmp_path / "skills"
        _make_skill(
            project_dir, "code-review", "コードレビューを実行するスキル"
        )
        _make_skill(project_dir, "deploy", "デプロイを実行するスキル")

        manager = SkillManager(project_skills_dir=project_dir)
        matches = manager.find_matching("コードレビューをお願いします")

        assert len(matches) >= 1
        assert matches[0].name == "code-review"

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        """マッチしない場合は空リストを返すこと."""
        project_dir = tmp_path / "skills"
        _make_skill(project_dir, "code-review", "コードレビューを実行するスキル")

        manager = SkillManager(project_skills_dir=project_dir)
        matches = manager.find_matching("全く関係ない指示xyz")

        assert matches == []
