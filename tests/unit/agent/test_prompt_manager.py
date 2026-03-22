"""PromptManager のユニットテスト."""

from __future__ import annotations

from pathlib import Path

from myagent.agent.prompt_manager import PromptManager


class TestPromptManager:
    """PromptManager のテスト."""

    def test_ベーステンプレートが読み込まれる(self, tmp_path: Path) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベースプロンプト", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt()

        assert "ベースプロンプト" in result

    def test_codingタスクで追加テンプレートが結合される(
        self, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベース", encoding="utf-8")
        (prompts_dir / "coding.txt").write_text("コーディング指示", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt(task_type="coding")

        assert "ベース" in result
        assert "コーディング指示" in result

    def test_researchタスクで追加テンプレートが結合される(
        self, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベース", encoding="utf-8")
        (prompts_dir / "research.txt").write_text("調査指示", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt(task_type="research")

        assert "ベース" in result
        assert "調査指示" in result

    def test_refactoringタスクで追加テンプレートが結合される(
        self, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベース", encoding="utf-8")
        (prompts_dir / "refactoring.txt").write_text(
            "リファクタリング指示", encoding="utf-8"
        )

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt(task_type="refactoring")

        assert "ベース" in result
        assert "リファクタリング指示" in result

    def test_generalタスクではベーステンプレートのみ(
        self, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベースのみ", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt(task_type="general")

        assert result == "ベースのみ"

    def test_project_indexが結合される(self, tmp_path: Path) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベース", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt(project_index="src/\n├── main.py")

        assert "ベース" in result
        assert "プロジェクト構造" in result
        assert "src/" in result

    def test_テンプレート不在時にフォールバックプロンプトが使用される(
        self, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "empty"
        prompts_dir.mkdir()

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt()

        assert "AIアシスタント" in result

    def test_タスク別テンプレート不在時にベースのみ使用される(
        self, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベースのみ", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt(task_type="coding")

        assert result == "ベースのみ"

    def test_デフォルトプロンプトディレクトリが使用される(self) -> None:
        manager = PromptManager()
        result = manager.build_prompt()

        # デフォルトのbase.txtが読み込まれる
        assert "AIコーディングアシスタント" in result

    def test_load_templateでファイルが読み込まれる(
        self, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.txt").write_text("テスト内容", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager._load_template("test.txt")

        assert result == "テスト内容"

    def test_load_templateで存在しないファイルは空文字列を返す(
        self, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager._load_template("nonexistent.txt")

        assert result == ""
