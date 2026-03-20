"""ファイル操作ツール群.

Read, Write, Edit, ListDirectory, GlobSearch, GrepSearch の6ツールを提供する。
すべてのファイルアクセスは許可ディレクトリに制限される。
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import ConfigDict

from myagent.infra.errors import SecurityError, ToolExecutionError
from myagent.tools.path_security import AllowedDirectories
from myagent.tools.shared_state import WorkingDirectory


def _resolve(path_str: str, working_dir: WorkingDirectory | None) -> Path:
    """パスをworking_dir基準で解決する.

    working_dirがある場合はそれを基準に、ない場合はPythonのos.getcwd()基準で解決する。
    """
    if working_dir is not None:
        return working_dir.resolve_path(path_str)
    p = Path(path_str)
    return p.resolve()


def _fix_pdf_encoding(text: str) -> str:
    """pypdf が latin-1 として読んだ Shift-JIS テキストを修正する.

    pypdf は一部の日本語 PDF を latin-1 (1:1 バイトマッピング) として
    デコードすることがある。各文字を ord() でバイト列に戻し cp932 で
    再デコードすることで正しい日本語テキストを得る。
    変換に失敗した場合は元の文字列を返す。
    """
    try:
        raw = bytes(ord(c) for c in text if ord(c) < 256)
        if len(raw) < len(text) * 0.5:
            # 半数以上が U+0100 以上の文字なら変換不要（UTF系PDF）
            return text
        return raw.decode("cp932")
    except (UnicodeDecodeError, ValueError):
        return text


def _read_pdf(path: Path) -> str:
    """PDFファイルからテキストを抽出する."""
    try:
        import pypdf
    except ImportError:
        return (
            "PDF読み取りには pypdf が必要です。"
            "`uv pip install pypdf` でインストールしてください。"
        )

    import logging
    import warnings

    try:
        # pypdf の "Advanced encoding not implemented" 警告を抑制
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        pages: list[str] = []
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message=".*Advanced encoding.*", module="pypdf.*"
            )
            warnings.filterwarnings("ignore", category=UserWarning, module="pypdf.*")
            reader = pypdf.PdfReader(str(path))
            for i, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                if not text.strip():
                    continue
                # Shift-JIS PDF を latin-1 として誤読した場合を修正
                text = _fix_pdf_encoding(text)
                pages.append(f"--- ページ {i} ---\n{text}")
        if not pages:
            return f"PDF内にテキストが見つかりませんでした: {path.name}"
        return "\n\n".join(pages)
    except Exception as e:
        return f"PDF読み取りに失敗しました: {e}"


def _is_binary(path: Path) -> bool:
    """ファイルがバイナリかどうかを先頭バイトで判定する."""
    try:
        chunk = path.read_bytes()[:8192]
        return b"\x00" in chunk
    except OSError:
        return False


class ReadFileTool(BaseTool):
    """ファイルの内容を読み取るツール."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "read_file"
    description: str = "ファイルの内容を読み取る。file_pathにファイルパスを指定する。"
    allowed_dirs: AllowedDirectories
    working_dir: WorkingDirectory | None = None

    def _run(self, file_path: str, **_kwargs: Any) -> str:
        try:
            resolved = self.allowed_dirs.validate_path(
                _resolve(file_path, self.working_dir)
            )
            if not resolved.exists():
                return f"エラー: ファイルが見つかりません: {file_path}"
            if not resolved.is_file():
                return f"エラー: ファイルではありません: {file_path}"

            # PDF は専用処理
            if resolved.suffix.lower() == ".pdf":
                return _read_pdf(resolved)

            # バイナリファイルは読み取り不可として返す
            if _is_binary(resolved):
                return (
                    f"バイナリファイルのため読み取れません: {resolved.name} "
                    f"({resolved.stat().st_size:,} バイト)"
                )

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

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "write_file"
    description: str = "ファイルにコンテンツを書き込む。file_pathとcontentを指定する。"
    allowed_dirs: AllowedDirectories
    working_dir: WorkingDirectory | None = None

    def _run(self, file_path: str, content: str, **_kwargs: Any) -> str:
        try:
            resolved = self.allowed_dirs.validate_path(
                _resolve(file_path, self.working_dir)
            )
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

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "edit_file"
    description: str = (
        "ファイル内のold_stringをnew_stringに置換する。"
        "file_path, old_string, new_stringを指定する。"
    )
    allowed_dirs: AllowedDirectories
    working_dir: WorkingDirectory | None = None

    def _run(
        self, file_path: str, old_string: str, new_string: str, **_kwargs: Any
    ) -> str:
        try:
            resolved = self.allowed_dirs.validate_path(
                _resolve(file_path, self.working_dir)
            )
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

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "list_directory"
    description: str = (
        "ディレクトリ内のファイルとサブディレクトリを一覧表示する。"
        "pathにディレクトリパスを指定する。"
    )
    allowed_dirs: AllowedDirectories
    working_dir: WorkingDirectory | None = None

    def _run(self, path: str = ".", **_kwargs: Any) -> str:
        try:
            resolved = self.allowed_dirs.validate_path(_resolve(path, self.working_dir))
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

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "glob_search"
    description: str = (
        "globパターンでファイルを検索する。patternにglobパターンを指定する。"
    )
    allowed_dirs: AllowedDirectories
    working_dir: WorkingDirectory | None = None

    def _run(self, pattern: str, **_kwargs: Any) -> str:
        try:
            root = (
                self.working_dir.path
                if self.working_dir is not None
                else self.allowed_dirs.project_root
            )
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

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "grep_search"
    description: str = (
        "正規表現パターンでファイル内容を検索する。"
        "patternに正規表現、pathに検索対象ディレクトリを指定する。"
    )
    allowed_dirs: AllowedDirectories
    working_dir: WorkingDirectory | None = None

    def _run(self, pattern: str, path: str = ".", **_kwargs: Any) -> str:
        try:
            resolved = self.allowed_dirs.validate_path(_resolve(path, self.working_dir))
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
                        rel = file_path.relative_to(self.allowed_dirs.project_root)
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
