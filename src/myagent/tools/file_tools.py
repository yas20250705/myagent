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
    description: str = (
        "ファイルの内容を読み取る。file_pathに読み取り対象のファイルパス（絶対パスまたは相対パス）を指定する。"
        "\n\n【出力形式】行番号付きで内容を返す（'  行番号\\tコンテンツ' の形式）。"
        "行番号を使って後続のedit_fileで正確な編集位置を特定できる。"
        "\n\n【対応ファイル形式】"
        "テキストファイル: UTF-8エンコーディングで読み取る。"
        "PDFファイル: .pdf拡張子を自動検知し、テキスト抽出して返す。"
        "バイナリファイル: 自動検知し、読み取り不可のメッセージとファイルサイズを返す。"
        "\n\n【エッジケース】"
        "存在しないファイルを指定した場合はエラーメッセージを返す。"
        "ディレクトリを指定した場合はエラーを返す（ディレクトリの内容確認にはlist_directoryを使うこと）。"
        "大きなファイルは全行を返すため、必要な部分が分かっている場合はgrep_searchで該当箇所を特定してから読むことを推奨する。"
        "\n\n【他ツールとの使い分け】"
        "run_commandでcat/head/tail/less/moreを使う代わりに、必ずこのツールを使うこと。"
        "ディレクトリの内容一覧 → list_directory。"
        "ファイル内の特定文字列を探す → grep_search。"
        "\n\n【アンチパターン】"
        "ディレクトリパスを指定してはいけない（エラーになる）。"
        "run_commandで cat/head/tail を実行してはいけない（このツールを使う）。"
    )
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
    description: str = (
        "ファイルにコンテンツを書き込む。file_pathに書き込み先のファイルパス、contentに書き込む内容を指定する。"
        "\n\n【動作】"
        "指定パスにファイルを作成し、contentの内容を書き込む。"
        "親ディレクトリが存在しない場合は自動的に作成する。"
        "既存ファイルがある場合は全内容を上書きする（部分変更はできない）。"
        "\n\n【edit_fileとの使い分け】"
        "新規ファイル作成 → write_file。"
        "ファイル全体の書き換え → write_file"
        "（ただし事前にread_fileで既存内容を確認すること）。"
        "既存ファイルの一部を変更 → edit_file（write_fileではなくedit_fileを使う）。"
        "\n\n【エッジケース】"
        "既存ファイルを上書きする場合、contentに全内容を指定する必要がある（差分ではなく完全な内容）。"
        "既存ファイルの内容を確認せずに上書きすると、元の内容が失われるため、事前にread_fileで確認すること。"
        "\n\n【アンチパターン】"
        "既存ファイルの一部だけを変更したい場合にwrite_fileを使ってはいけない（edit_fileを使う）。"
        "既存ファイルの内容をread_fileで確認せずに上書きしてはいけない。"
        "run_commandでecho/catリダイレクト"
        "（echo > file、cat << EOF > file）"
        "を使ってはいけない（このツールを使う）。"
    )
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
        "ファイル内の文字列を置換する。file_pathに対象ファイル、old_stringに置換前の文字列、new_stringに置換後の文字列を指定する。"
        "\n\n【前提条件】使用前に必ずread_fileでファイル内容を確認すること。"
        "ファイルを読まずにedit_fileを使うと、old_stringの指定を誤る原因になる。"
        "\n\n【old_stringの一意性】"
        "old_stringはファイル内で一意（1箇所のみ出現）でなければならない。"
        "一意でない場合はエラーになる。対処法: "
        "old_stringに前後の行を含めてコンテキストを追加し、一意にする。"
        "例: 'return result' が複数箇所にある場合、"
        "'def my_func():\\n    return result' のように"
        "関数定義を含める。"
        "\n\n【インデント保持】"
        "old_stringとnew_stringのインデント（タブ/スペース）は、ファイル内の実際のインデントと完全に一致させること。"
        "read_fileの出力で行番号の後のタブ以降がファイルの実際の内容。"
        "\n\n【エッジケース】"
        "存在しないファイルを指定した場合はエラーを返す。"
        "old_stringがファイル内に見つからない場合はエラーを返す。"
        "old_stringが複数箇所に出現する場合はエラーを返す"
        "（前後の行を含めて一意にすること）。"
        "\n\n【複数箇所の変更】"
        "複数箇所を変更する場合は、edit_fileを複数回呼び出すこと"
        "（1回の呼び出しで1箇所のみ置換）。"
        "\n\n【他ツールとの使い分け】"
        "既存ファイルの部分変更 → edit_file。"
        "新規ファイル作成またはファイル全体の書き換え → write_file。"
        "run_commandでsed/awkを使う代わりに、必ずこのツールを使うこと。"
        "\n\n【アンチパターン】"
        "read_fileでファイルを読まずにedit_fileを使ってはいけない。"
        "run_commandでsed/awkを実行してはいけない（このツールを使う）。"
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
        "ディレクトリ直下のファイルとサブディレクトリを一覧表示する。pathにディレクトリパスを指定する（省略時はカレントディレクトリ）。"
        "\n\n【出力形式】"
        "ファイル名を1行1件で表示する。ディレクトリ名には末尾に '/' が付く。"
        "空のディレクトリの場合は '(空のディレクトリ)' を返す。"
        "結果はアルファベット順にソートされる。"
        "\n\n【エッジケース】"
        "ディレクトリでないパスを指定した場合はエラーを返す。"
        "存在しないパスを指定した場合はエラーを返す。"
        "\n\n【glob_searchとの使い分け】"
        "ディレクトリ直下の内容を確認する → list_directory。"
        "特定パターンのファイルを再帰的に検索する"
        "（例: 全Pythonファイル） → glob_search。"
        "ファイル内容を検索する → grep_search。"
        "\n\n【アンチパターン】"
        "run_commandでls/dirを使う代わりに、このツールを使うこと。"
        "ファイルパスを指定してはいけない"
        "（ディレクトリパスのみ対応）。"
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
        "\n\n【パターン例】"
        "'**/*.py' → 全Pythonファイルを再帰的に検索。"
        "'src/**/test_*.py' → src以下のテストファイルを検索。"
        "'*.md' → カレントディレクトリ直下のMarkdownファイル。"
        "'docs/**/*.md' → docs以下の全Markdownファイル。"
        "'**/__init__.py' → 全パッケージの__init__.pyを検索。"
        "\n\n【出力形式】"
        "マッチしたファイルの相対パスを1行1件で返す。結果はアルファベット順にソートされる。"
        "マッチするファイルがない場合はその旨のメッセージを返す。"
        "結果は最大200件に制限される。"
        "\n\n【エッジケース】"
        "マッチするファイルがない場合はその旨のメッセージを返す。"
        "結果が200件を超える場合は先頭200件のみ返す。"
        "\n\n【grep_searchとの使い分け】"
        "ファイル名やパスのパターンで検索する → glob_search。"
        "ファイルの中身（コンテンツ）を検索する → grep_search。"
        "例: 'test_*.py'というファイルを探す → glob_search。"
        "例: 'class MyClass'という定義を探す → grep_search。"
        "\n\n【アンチパターン】"
        "run_commandでfind/lsを使う代わりに、"
        "必ずこのツールを使うこと。"
        "ファイル内容の検索にglob_searchを使ってはいけない"
        "（grep_searchを使う）。"
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
        "正規表現パターンでファイル内容を検索する。patternに正規表現パターン、pathに検索対象（ディレクトリまたは単一ファイル）を指定する。"
        "\n\n【パラメータ】"
        "pattern: 正規表現パターン（Python re モジュール準拠）。"
        "path: 検索対象のディレクトリまたはファイルパス"
        "（省略時はカレントディレクトリ）。"
        "ディレクトリを指定した場合、配下の全テキストファイルを再帰的に検索する。"
        "単一ファイルを指定した場合、そのファイル内のみ検索する。"
        "\n\n【パターン例】"
        "'class MyClass' → 特定クラスの定義を検索。"
        "'def test_' → テスト関数を検索。"
        "'import\\s+json' → json モジュールのインポートを検索。"
        "'TODO|FIXME|HACK' → コード内の注釈を検索。"
        "\n\n【出力形式】"
        "'ファイルパス:行番号: マッチした行の内容' の形式で返す。"
        "結果は最大200件に制限される。マッチがない場合はその旨のメッセージを返す。"
        "\n\n【エッジケース】"
        "マッチがない場合はその旨のメッセージを返す。"
        "結果が200件を超える場合は先頭200件のみ返す"
        "（パターンを絞り込んで再検索すること）。"
        "無効な正規表現パターンの場合はエラーを返す。"
        "\n\n【glob_searchとの使い分け】"
        "ファイルの中身（コンテンツ）を検索する → grep_search。"
        "ファイル名やパスのパターンで検索する → glob_search。"
        "例: 'class MyClass'の定義箇所を探す → grep_search。"
        "例: 'test_*.py'というファイルを探す → glob_search。"
        "\n\n【アンチパターン】"
        "run_commandでgrep/rg/ackを使う代わりに、"
        "必ずこのツールを使うこと。"
        "ファイル名パターン検索にgrep_searchを使ってはいけない"
        "（glob_searchを使う）。"
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
