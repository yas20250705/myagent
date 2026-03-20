"""ファイル操作ツール群.

Read, Write, Edit, ListDirectory, GlobSearch, GrepSearch の6ツールを提供する。
すべてのファイルアクセスはプロジェクトルートに制限される。
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import Field

from myagent.infra.errors import SecurityError, ToolExecutionError

_SEP = os.sep


def _resolve_and_validate(file_path: str, project_root: Path) -> Path:
    """パスを解決し、プロジェクトルート内であることを検証する."""
    resolved = Path(file_path).resolve()
    root = project_root.resolve()
    root_str = str(root)
    resolved_str = str(resolved)
    if not (resolved_str == root_str or resolved_str.startswith(root_str + _SEP)):
        msg = f"プロジェクトルート外へのアクセスは禁止されています: {file_path}"
        raise SecurityError(msg)
    return resolved


class ReadFileTool(BaseTool):
    """ファイルの内容を読み取るツール."""

    name: str = "read_file"
    description: str = "ファイルの内容を読み取る。file_pathにファイルパスを指定する。"
    project_root: Path = Field(default_factory=Path.cwd)

    def _run(self, file_path: str, **_kwargs: Any) -> str:
        try:
            resolved = _resolve_and_validate(file_path, self.project_root)
            if not resolved.exists():
                return f"エラー: ファイルが見つかりません: {file_path}"
            if not resolved.is_file():
                return f"エラー: ファイルではありません: {file_path}"
            content = resolved.read_text(encoding="utf-8")
            lines = content.splitlines()
            numbered = [f"{i + 1:>6}\t{line}" for i, line in enumerate(lines)]
            return "\n".join(numbered)
        except SecurityError:
            raise
        except Exception as e:
            msg = f"ファイル読み取りに失敗しました: {e}"
            raise ToolExecutionError(msg) from e


class WriteFileTool(BaseTool):
    """ファイルにコンテンツを書き込むツール."""

    name: str = "write_file"
    description: str = "ファイルにコンテンツを書き込む。file_pathとcontentを指定する。"
    project_root: Path = Field(default_factory=Path.cwd)

    def _run(self, file_path: str, content: str, **_kwargs: Any) -> str:
        try:
            resolved = _resolve_and_validate(file_path, self.project_root)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return f"ファイルを書き込みました: {file_path}"
        except SecurityError:
            raise
        except Exception as e:
            msg = f"ファイル書き込みに失敗しました: {e}"
            raise ToolExecutionError(msg) from e


class EditFileTool(BaseTool):
    """ファイル内の文字列を置換するツール."""

    name: str = "edit_file"
    description: str = (
        "ファイル内のold_stringをnew_stringに置換する。"
        "file_path, old_string, new_stringを指定する。"
    )
    project_root: Path = Field(default_factory=Path.cwd)

    def _run(
        self, file_path: str, old_string: str, new_string: str, **_kwargs: Any
    ) -> str:
        try:
            resolved = _resolve_and_validate(file_path, self.project_root)
            if not resolved.exists():
                return f"エラー: ファイルが見つかりません: {file_path}"
            content = resolved.read_text(encoding="utf-8")
            count = content.count(old_string)
            if count == 0:
                return "エラー: 置換対象の文字列が見つかりません"
            if count > 1:
                return (
                    f"エラー: 置換対象の文字列が{count}箇所"
                    "見つかりました。一意になるようコンテキストを追加してください"
                )
            new_content = content.replace(old_string, new_string, 1)
            resolved.write_text(new_content, encoding="utf-8")
            return f"ファイルを編集しました: {file_path}"
        except SecurityError:
            raise
        except Exception as e:
            msg = f"ファイル編集に失敗しました: {e}"
            raise ToolExecutionError(msg) from e


class ListDirectoryTool(BaseTool):
    """ディレクトリの内容を一覧表示するツール."""

    name: str = "list_directory"
    description: str = (
        "ディレクトリ内のファイルとサブディレクトリを一覧表示する。"
        "pathにディレクトリパスを指定する。"
    )
    project_root: Path = Field(default_factory=Path.cwd)

    def _run(self, path: str = ".", **_kwargs: Any) -> str:
        try:
            resolved = _resolve_and_validate(path, self.project_root)
            if not resolved.is_dir():
                return f"エラー: ディレクトリではありません: {path}"
            entries: list[str] = []
            for entry in sorted(resolved.iterdir()):
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")
            if not entries:
                return "(空のディレクトリ)"
            return "\n".join(entries)
        except SecurityError:
            raise
        except Exception as e:
            msg = f"ディレクトリ一覧取得に失敗しました: {e}"
            raise ToolExecutionError(msg) from e


class GlobSearchTool(BaseTool):
    """globパターンでファイルを検索するツール."""

    name: str = "glob_search"
    description: str = (
        "globパターンでファイルを検索する。"
        "patternにglobパターンを指定する。"
    )
    project_root: Path = Field(default_factory=Path.cwd)

    def _run(self, pattern: str, **_kwargs: Any) -> str:
        try:
            root = self.project_root.resolve()
            matches: list[str] = []
            for dirpath, _dirnames, filenames in os.walk(root):
                for filename in filenames:
                    full_path = Path(dirpath) / filename
                    rel_path = full_path.relative_to(root)
                    if fnmatch.fnmatch(str(rel_path), pattern):
                        matches.append(str(rel_path))
            matches.sort()
            if not matches:
                return f"パターン '{pattern}' に一致するファイルはありません"
            return "\n".join(matches[:200])
        except Exception as e:
            msg = f"glob検索に失敗しました: {e}"
            raise ToolExecutionError(msg) from e


class GrepSearchTool(BaseTool):
    """正規表現でファイル内容を検索するツール."""

    name: str = "grep_search"
    description: str = (
        "正規表現パターンでファイル内容を検索する。"
        "patternに正規表現、pathに検索対象ディレクトリを指定する。"
    )
    project_root: Path = Field(default_factory=Path.cwd)

    def _run(self, pattern: str, path: str = ".", **_kwargs: Any) -> str:
        try:
            resolved = _resolve_and_validate(path, self.project_root)
            regex = re.compile(pattern)
            results: list[str] = []
            max_results = 200

            if resolved.is_file():
                files = [resolved]
            else:
                files = [
                    p
                    for p in sorted(resolved.rglob("*"))
                    if p.is_file() and not p.name.startswith(".")
                ]

            for file_path in files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, PermissionError):
                    continue
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        rel = file_path.relative_to(self.project_root.resolve())
                        results.append(f"{rel}:{i}: {line.rstrip()}")
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break

            if not results:
                return f"パターン '{pattern}' に一致する行はありません"
            return "\n".join(results)
        except SecurityError:
            raise
        except re.error as e:
            return f"エラー: 無効な正規表現パターン: {e}"
        except Exception as e:
            msg = f"grep検索に失敗しました: {e}"
            raise ToolExecutionError(msg) from e
