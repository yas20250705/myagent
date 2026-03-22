"""loader.py のユニットテスト."""

from __future__ import annotations

from pathlib import Path

from myagent.skills.loader import parse_skill_body, parse_skill_md, validate_skill_dir


def _write_skill_md(skill_dir: Path, content: str) -> Path:
    """テスト用 SKILL.md を作成する."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    return skill_md


class TestParseSkillMd:
    """parse_skill_md のテスト."""

    def test_valid_skill(self, tmp_path: Path) -> None:
        """正常な SKILL.md をパースできること."""
        skill_dir = tmp_path / "code-review"
        _write_skill_md(
            skill_dir,
            """\
---
name: code-review
description: コードレビューを実行するスキル
license: Apache-2.0
compatibility: Requires git
metadata:
  author: test
  version: "1.0"
allowed-tools: Bash Read
---

# コードレビュー

手順...
""",
        )

        meta = parse_skill_md(skill_dir / "SKILL.md", "project")

        assert meta is not None
        assert meta.name == "code-review"
        assert meta.description == "コードレビューを実行するスキル"
        assert meta.license == "Apache-2.0"
        assert meta.compatibility == "Requires git"
        assert meta.metadata == {"author": "test", "version": "1.0"}
        assert meta.allowed_tools == ["Bash", "Read"]
        assert meta.scope == "project"
        assert meta.skill_dir == skill_dir

    def test_minimal_skill(self, tmp_path: Path) -> None:
        """必須フィールドのみの SKILL.md をパースできること."""
        skill_dir = tmp_path / "my-skill"
        _write_skill_md(
            skill_dir,
            """\
---
name: my-skill
description: シンプルなスキル
---

ボディテキスト
""",
        )

        meta = parse_skill_md(skill_dir / "SKILL.md", "global")

        assert meta is not None
        assert meta.name == "my-skill"
        assert meta.description == "シンプルなスキル"
        assert meta.license is None
        assert meta.compatibility is None
        assert meta.metadata == {}
        assert meta.allowed_tools == []
        assert meta.scope == "global"

    def test_missing_name_returns_none(self, tmp_path: Path) -> None:
        """必須フィールド 'name' が欠落している場合は None を返すこと."""
        skill_dir = tmp_path / "some-skill"
        _write_skill_md(
            skill_dir,
            """\
---
description: 説明のみ
---
""",
        )

        meta = parse_skill_md(skill_dir / "SKILL.md", "project")

        assert meta is None

    def test_missing_description_returns_none(self, tmp_path: Path) -> None:
        """必須フィールド 'description' が欠落している場合は None を返すこと."""
        skill_dir = tmp_path / "no-desc"
        _write_skill_md(
            skill_dir,
            """\
---
name: no-desc
---
""",
        )

        meta = parse_skill_md(skill_dir / "SKILL.md", "project")

        assert meta is None

    def test_name_directory_mismatch_returns_none(self, tmp_path: Path) -> None:
        """name とディレクトリ名が一致しない場合は None を返すこと."""
        skill_dir = tmp_path / "actual-name"
        _write_skill_md(
            skill_dir,
            """\
---
name: different-name
description: テストスキル
---
""",
        )

        meta = parse_skill_md(skill_dir / "SKILL.md", "project")

        assert meta is None

    def test_invalid_name_uppercase_returns_none(self, tmp_path: Path) -> None:
        """大文字を含む name は無効として None を返すこと.

        ディレクトリ名も大文字を使い、name とディレクトリ名を一致させることで
        命名規則バリデーションが発動するかをテストする。
        """
        # Windows のファイルシステムは大文字小文字を区別しないため、
        # ディレクトリ名と name フィールドを同じ大文字表記にして
        # 「name は一致するが命名規則違反」のケースをテストする
        skill_dir = tmp_path / "my-Skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            """\
---
name: my-Skill
description: テストスキル
---
""",
            encoding="utf-8",
        )

        meta = parse_skill_md(skill_dir / "SKILL.md", "project")

        assert meta is None

    def test_yaml_parse_error_returns_none(self, tmp_path: Path) -> None:
        """不正な YAML のパースエラーは None を返すこと."""
        skill_dir = tmp_path / "bad-yaml"
        _write_skill_md(
            skill_dir,
            """\
---
name: bad-yaml
description: [unclosed bracket
---
""",
        )

        meta = parse_skill_md(skill_dir / "SKILL.md", "project")

        assert meta is None

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        """フロントマターのない SKILL.md は None を返すこと."""
        skill_dir = tmp_path / "no-front"
        _write_skill_md(skill_dir, "フロントマターなしのコンテンツ")

        meta = parse_skill_md(skill_dir / "SKILL.md", "project")

        assert meta is None

    def test_name_consecutive_hyphens_returns_none(self, tmp_path: Path) -> None:
        """連続ハイフンを含む name は無効として None を返すこと."""
        skill_dir = tmp_path / "my--skill"
        _write_skill_md(
            skill_dir,
            """\
---
name: my--skill
description: テストスキル
---
""",
        )

        meta = parse_skill_md(skill_dir / "SKILL.md", "project")

        assert meta is None


class TestParseSkillBody:
    """parse_skill_body のテスト."""

    def test_extracts_body(self, tmp_path: Path) -> None:
        """ボディテキストを正しく抽出できること."""
        skill_dir = tmp_path / "my-skill"
        _write_skill_md(
            skill_dir,
            """\
---
name: my-skill
description: テスト
---

# ボディ

ここがボディです。
""",
        )

        body = parse_skill_body(skill_dir / "SKILL.md")

        assert "# ボディ" in body
        assert "ここがボディです。" in body


class TestValidateSkillDir:
    """validate_skill_dir のテスト."""

    def test_valid_returns_empty(self, tmp_path: Path) -> None:
        """有効なスキルはエラーなしを返すこと."""
        skill_dir = tmp_path / "valid-skill"
        _write_skill_md(
            skill_dir,
            """\
---
name: valid-skill
description: 正常なスキル
---
ボディ
""",
        )

        errors = validate_skill_dir(skill_dir)

        assert errors == []

    def test_missing_skill_md(self, tmp_path: Path) -> None:
        """SKILL.md がないと errors が返ること."""
        skill_dir = tmp_path / "no-skill-md"
        skill_dir.mkdir()

        errors = validate_skill_dir(skill_dir)

        assert any("SKILL.md" in e for e in errors)

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        """存在しないディレクトリはエラーを返すこと."""
        skill_dir = tmp_path / "not-exist"

        errors = validate_skill_dir(skill_dir)

        assert errors

    def test_name_mismatch_is_error(self, tmp_path: Path) -> None:
        """name とディレクトリ名の不一致はエラーを返すこと."""
        skill_dir = tmp_path / "actual"
        _write_skill_md(
            skill_dir,
            """\
---
name: different
description: テスト
---
""",
        )

        errors = validate_skill_dir(skill_dir)

        assert any("一致" in e for e in errors)
