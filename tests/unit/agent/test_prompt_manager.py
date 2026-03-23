"""PromptManager のユニットテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

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

    def test_skills_contextが注入される(self, tmp_path: Path) -> None:
        """skills_context が指定された場合、プロンプトに含まれること."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベース", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        skills_ctx = "## 利用可能なスキル\n\n- **my-skill**: テストスキルの説明\n"
        result = manager.build_prompt(skills_context=skills_ctx)

        assert "利用可能なスキル" in result
        assert "my-skill" in result

    def test_skills_contextがNoneの場合は注入されない(self, tmp_path: Path) -> None:
        """skills_context が None の場合、プロンプトに含まれないこと."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベースのみ", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt(skills_context=None)

        assert result == "ベースのみ"

    def test_skills_contextはworking_directoryの後に来る(
        self, tmp_path: Path
    ) -> None:
        """skills_context は作業ディレクトリの後に配置されること."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "base.txt").write_text("ベース", encoding="utf-8")

        manager = PromptManager(prompts_dir=prompts_dir)
        result = manager.build_prompt(
            working_directory="/some/dir",
            skills_context="## スキル\n\n- **test**: 説明\n",
        )

        wd_pos = result.index("作業ディレクトリ")
        skills_pos = result.index("スキル")
        assert wd_pos < skills_pos


class TestPromptQuality:
    """プロンプトテンプレートの品質チェックテスト."""

    _PROMPTS_DIR = Path(__file__).resolve().parents[3] / "src" / "myagent" / "agent" / "prompts"

    def test_base_txtが200行以上である(self) -> None:
        content = (self._PROMPTS_DIR / "base.txt").read_text(encoding="utf-8")
        line_count = len(content.splitlines())
        assert line_count >= 200, f"base.txtは{line_count}行（200行以上必要）"

    def test_coding_txtが50行以上である(self) -> None:
        content = (self._PROMPTS_DIR / "coding.txt").read_text(encoding="utf-8")
        line_count = len(content.splitlines())
        assert line_count >= 50, f"coding.txtは{line_count}行（50行以上必要）"

    def test_research_txtが40行以上である(self) -> None:
        content = (self._PROMPTS_DIR / "research.txt").read_text(encoding="utf-8")
        line_count = len(content.splitlines())
        assert line_count >= 40, f"research.txtは{line_count}行（40行以上必要）"

    def test_refactoring_txtが50行以上である(self) -> None:
        content = (self._PROMPTS_DIR / "refactoring.txt").read_text(encoding="utf-8")
        line_count = len(content.splitlines())
        assert line_count >= 50, f"refactoring.txtは{line_count}行（50行以上必要）"

    def test_base_txtにツール使い分けマトリクスが含まれる(self) -> None:
        content = (self._PROMPTS_DIR / "base.txt").read_text(encoding="utf-8")
        assert "run_command" in content
        assert "read_file" in content
        assert "edit_file" in content
        assert "glob_search" in content
        assert "grep_search" in content

    def test_base_txtに安全性ガイドラインが含まれる(self) -> None:
        content = (self._PROMPTS_DIR / "base.txt").read_text(encoding="utf-8")
        assert "安全性ガイドライン" in content
        assert "破壊的" in content


class TestToolDescriptionQuality:
    """ツールdescriptionの品質チェックテスト."""

    @pytest.fixture()
    def file_tools(self) -> list[tuple[str, str]]:
        """file_tools のツール名とdescriptionペアを返す."""
        from myagent.tools.file_tools import (
            EditFileTool,
            GlobSearchTool,
            GrepSearchTool,
            ListDirectoryTool,
            ReadFileTool,
            WriteFileTool,
        )
        from myagent.tools.path_security import AllowedDirectories

        allowed = AllowedDirectories(Path.cwd())
        tools = [
            ReadFileTool(allowed_dirs=allowed),
            WriteFileTool(allowed_dirs=allowed),
            EditFileTool(allowed_dirs=allowed),
            ListDirectoryTool(allowed_dirs=allowed),
            GlobSearchTool(allowed_dirs=allowed),
            GrepSearchTool(allowed_dirs=allowed),
        ]
        return [(t.name, t.description) for t in tools]

    def test_file_toolsのdescriptionが150文字以上(
        self, file_tools: list[tuple[str, str]]
    ) -> None:
        for name, desc in file_tools:
            assert len(desc) >= 150, (
                f"{name}のdescriptionが短すぎます: {len(desc)}文字"
            )

    def test_run_commandのdescriptionが200文字以上(self) -> None:
        from myagent.tools.shell_tools import RunCommandTool

        tool = RunCommandTool()
        assert len(tool.description) >= 200, (
            f"run_commandのdescriptionが短すぎます: {len(tool.description)}文字"
        )

    def test_run_commandのdescriptionに専用ツール優先の指示がある(self) -> None:
        from myagent.tools.shell_tools import RunCommandTool

        tool = RunCommandTool()
        assert "専用ツール" in tool.description
        for keyword in ["read_file", "edit_file", "write_file", "glob_search", "grep_search"]:
            assert keyword in tool.description, (
                f"run_commandのdescriptionに'{keyword}'が含まれていません"
            )

    def test_web_toolsのdescriptionが150文字以上(self) -> None:
        from myagent.tools.web_tools import WebFetchTool, WebSearchTool

        for tool in [WebSearchTool(), WebFetchTool()]:
            assert len(tool.description) >= 150, (
                f"{tool.name}のdescriptionが短すぎます: {len(tool.description)}文字"
            )

    def test_websearchのdescriptionにプロジェクト内検索優先の指示がある(
        self,
    ) -> None:
        from myagent.tools.web_tools import WebSearchTool

        tool = WebSearchTool()
        assert "grep_search" in tool.description
        assert "プロジェクト内" in tool.description or "プロジェクト" in tool.description

    def test_read_fileのdescriptionに必須キーワードが含まれる(
        self, file_tools: list[tuple[str, str]]
    ) -> None:
        desc = next(d for n, d in file_tools if n == "read_file")
        for keyword in ["行番号", "PDF", "バイナリ", "cat"]:
            assert keyword in desc, (
                f"read_fileのdescriptionに'{keyword}'が含まれていません"
            )

    def test_write_fileのdescriptionに必須キーワードが含まれる(
        self, file_tools: list[tuple[str, str]]
    ) -> None:
        desc = next(d for n, d in file_tools if n == "write_file")
        for keyword in ["edit_file", "新規", "上書き", "echo"]:
            assert keyword in desc, (
                f"write_fileのdescriptionに'{keyword}'が含まれていません"
            )

    def test_edit_fileのdescriptionに必須キーワードが含まれる(
        self, file_tools: list[tuple[str, str]]
    ) -> None:
        desc = next(d for n, d in file_tools if n == "edit_file")
        for keyword in ["一意", "read_file", "インデント", "sed"]:
            assert keyword in desc, (
                f"edit_fileのdescriptionに'{keyword}'が含まれていません"
            )

    def test_list_directoryのdescriptionに必須キーワードが含まれる(
        self, file_tools: list[tuple[str, str]]
    ) -> None:
        desc = next(d for n, d in file_tools if n == "list_directory")
        for keyword in ["glob_search", "ls"]:
            assert keyword in desc, (
                f"list_directoryのdescriptionに'{keyword}'が含まれていません"
            )

    def test_glob_searchのdescriptionに必須キーワードが含まれる(
        self, file_tools: list[tuple[str, str]]
    ) -> None:
        desc = next(d for n, d in file_tools if n == "glob_search")
        for keyword in ["grep_search", "find", "**/*.py"]:
            assert keyword in desc, (
                f"glob_searchのdescriptionに'{keyword}'が含まれていません"
            )

    def test_grep_searchのdescriptionに必須キーワードが含まれる(
        self, file_tools: list[tuple[str, str]]
    ) -> None:
        desc = next(d for n, d in file_tools if n == "grep_search")
        for keyword in ["glob_search", "正規表現", "grep"]:
            assert keyword in desc, (
                f"grep_searchのdescriptionに'{keyword}'が含まれていません"
            )

    def test_websearchのdescriptionに必須キーワードが含まれる(self) -> None:
        from myagent.tools.web_tools import WebSearchTool

        tool = WebSearchTool()
        for keyword in ["grep_search", "クエリ"]:
            assert keyword in tool.description, (
                f"websearchのdescriptionに'{keyword}'が含まれていません"
            )

    def test_webfetchのdescriptionに必須キーワードが含まれる(self) -> None:
        from myagent.tools.web_tools import WebFetchTool

        tool = WebFetchTool()
        for keyword in ["URL", "推測", "format"]:
            assert keyword in tool.description, (
                f"webfetchのdescriptionに'{keyword}'が含まれていません"
            )
