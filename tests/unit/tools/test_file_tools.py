"""ファイルツールのテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from myagent.infra.errors import SecurityError
from myagent.tools.file_tools import (
    EditFileTool,
    GlobSearchTool,
    GrepSearchTool,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
)


class TestReadFileTool:
    """ReadFileTool のテスト."""

    def test_ファイルを行番号付きで読み取れる(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3", encoding="utf-8")
        tool = ReadFileTool(project_root=tmp_path)
        result = tool._run(file_path=str(test_file))
        assert "1\tline1" in result
        assert "3\tline3" in result

    def test_存在しないファイルでエラーメッセージを返す(self, tmp_path: Path) -> None:
        tool = ReadFileTool(project_root=tmp_path)
        result = tool._run(file_path=str(tmp_path / "nonexistent.txt"))
        assert "エラー" in result

    def test_プロジェクトルート外のアクセスでSecurityErrorが発生する(
        self, tmp_path: Path
    ) -> None:
        tool = ReadFileTool(project_root=tmp_path)
        with pytest.raises(SecurityError):
            tool._run(file_path="/etc/passwd")


class TestWriteFileTool:
    """WriteFileTool のテスト."""

    def test_ファイルを書き込める(self, tmp_path: Path) -> None:
        tool = WriteFileTool(project_root=tmp_path)
        result = tool._run(
            file_path=str(tmp_path / "output.txt"), content="hello world"
        )
        assert "書き込み" in result
        assert (tmp_path / "output.txt").read_text(encoding="utf-8") == "hello world"

    def test_サブディレクトリも自動作成される(self, tmp_path: Path) -> None:
        tool = WriteFileTool(project_root=tmp_path)
        tool._run(
            file_path=str(tmp_path / "sub" / "dir" / "file.txt"), content="nested"
        )
        assert (tmp_path / "sub" / "dir" / "file.txt").exists()


class TestEditFileTool:
    """EditFileTool のテスト."""

    def test_文字列を置換できる(self, tmp_path: Path) -> None:
        test_file = tmp_path / "edit.txt"
        test_file.write_text("hello world", encoding="utf-8")
        tool = EditFileTool(project_root=tmp_path)
        result = tool._run(
            file_path=str(test_file), old_string="world", new_string="python"
        )
        assert "編集" in result
        assert test_file.read_text(encoding="utf-8") == "hello python"

    def test_一致しない文字列でエラーメッセージを返す(self, tmp_path: Path) -> None:
        test_file = tmp_path / "edit.txt"
        test_file.write_text("hello world", encoding="utf-8")
        tool = EditFileTool(project_root=tmp_path)
        result = tool._run(
            file_path=str(test_file), old_string="notfound", new_string="replaced"
        )
        assert "見つかりません" in result

    def test_複数一致でエラーメッセージを返す(self, tmp_path: Path) -> None:
        test_file = tmp_path / "edit.txt"
        test_file.write_text("hello hello", encoding="utf-8")
        tool = EditFileTool(project_root=tmp_path)
        result = tool._run(
            file_path=str(test_file), old_string="hello", new_string="hi"
        )
        assert "2箇所" in result


class TestListDirectoryTool:
    """ListDirectoryTool のテスト."""

    def test_ディレクトリ内容を一覧表示する(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").touch()
        (tmp_path / "subdir").mkdir()
        tool = ListDirectoryTool(project_root=tmp_path)
        result = tool._run(path=str(tmp_path))
        assert "file.txt" in result
        assert "subdir/" in result


class TestGlobSearchTool:
    """GlobSearchTool のテスト."""

    def test_パターンに一致するファイルを検索する(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").touch()
        (tmp_path / "test.txt").touch()
        tool = GlobSearchTool(project_root=tmp_path)
        result = tool._run(pattern="*.py")
        assert "test.py" in result
        assert "test.txt" not in result


class TestGrepSearchTool:
    """GrepSearchTool のテスト."""

    def test_正規表現でファイル内容を検索する(self, tmp_path: Path) -> None:
        test_file = tmp_path / "search.py"
        test_file.write_text("def hello():\n    pass\ndef world():\n    pass", encoding="utf-8")
        tool = GrepSearchTool(project_root=tmp_path)
        result = tool._run(pattern=r"def \w+", path=str(tmp_path))
        assert "hello" in result
        assert "world" in result

    def test_一致なしで適切なメッセージを返す(self, tmp_path: Path) -> None:
        test_file = tmp_path / "empty.py"
        test_file.write_text("nothing here", encoding="utf-8")
        tool = GrepSearchTool(project_root=tmp_path)
        result = tool._run(pattern="notfound", path=str(tmp_path))
        assert "一致する行はありません" in result
