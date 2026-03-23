"""シェルコマンド実行ツール.

危険コマンドの検知とブロック機能、作業ディレクトリ追跡を提供する。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import ConfigDict, Field

from myagent.infra.errors import SecurityError, ToolExecutionError
from myagent.tools.path_security import AllowedDirectories
from myagent.tools.shared_state import WorkingDirectory

DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-rf\s+/"),
    re.compile(r"\brm\s+-rf\s+~"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r">\s*/dev/sd"),
    re.compile(r"\b:()\s*\{\s*:\|:\s*&\s*\}\s*;"),  # fork bomb
    re.compile(r"\bchmod\s+-R\s+777\s+/"),
    re.compile(r"\bchown\s+-R\s+.*\s+/\s*$"),
    re.compile(r"\bcurl\b.*\|\s*(bash|sh)\b"),
    re.compile(r"\bwget\b.*\|\s*(bash|sh)\b"),
    re.compile(r"\bgit\s+push\s+.*--force"),
    re.compile(r"\bgit\s+reset\s+--hard"),
]

_CWD_SENTINEL = "__MYAGENT_CWD__"

# Unix → Windows cmd.exe コマンド変換テーブル
_UNIX_TO_WINDOWS: dict[str, str] = {
    "pwd": "echo %CD%",
    "ls": "dir",
    "clear": "cls",
    "which": "where",
    "cat": "type",
    "cp": "copy",
    "mv": "move",
    "rm": "del",
    "mkdir -p": "mkdir",
    "touch": "type nul >",
}


def _translate_for_windows(command: str) -> str:
    """Unix系コマンドをWindows cmd.exe 互換コマンドに変換する.

    完全一致または先頭一致で変換する。
    """
    stripped = command.strip()
    # 完全一致
    if stripped in _UNIX_TO_WINDOWS:
        return _UNIX_TO_WINDOWS[stripped]
    # 先頭のコマンド部分が一致する場合（引数付き）
    for unix_cmd, win_cmd in _UNIX_TO_WINDOWS.items():
        if stripped.startswith(unix_cmd + " "):
            return win_cmd + stripped[len(unix_cmd) :]
    return command


def is_dangerous_command(command: str) -> bool:
    """コマンドが危険なパターンに一致するか判定する."""
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return True
    return False


def _wrap_with_cwd_capture(command: str) -> str:
    """コマンドの末尾にcwd取得コードを付加する (Unix用).

    実行後の作業ディレクトリをsentinelフォーマットで stdout に出力する。
    Windows ではバッチファイル方式を使用するため、この関数は呼ばれない。
    """
    return f"{command}\nprintf '\\n{_CWD_SENTINEL}:%s' \"$(pwd)\""


def _parse_cwd_from_output(output: str) -> tuple[str, str | None]:
    """stdout からsentinel行を抽出し、除去済み出力と新cwdを返す.

    Args:
        output: サブプロセスの stdout 文字列。

    Returns:
        (sentinel除去済み出力, 新cwd文字列 または None)
    """
    prefix = f"{_CWD_SENTINEL}:"
    lines = output.splitlines()
    cleaned: list[str] = []
    new_cwd: str | None = None
    for line in lines:
        if line.strip().startswith(prefix):
            new_cwd = line.strip()[len(prefix) :]
        else:
            cleaned.append(line)
    return "\n".join(cleaned), new_cwd


class RunCommandTool(BaseTool):
    """シェルコマンドを実行するツール."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "run_command"
    description: str = (
        "シェルコマンドを実行する。commandに実行するコマンド文字列を指定する。"
        "\n\n【重要: 専用ツール優先ルール】"
        "以下の操作には専用ツールを使い、run_commandを使ってはいけない:"
        "\n  ファイル読み取り（cat/head/tail/less/more） → read_file"
        "\n  ファイル書き込み（echo >/cat <<EOF/tee） → write_file"
        "\n  ファイル編集（sed/awk） → edit_file"
        "\n  ディレクトリ一覧（ls/dir） → list_directory"
        "\n  ファイル名検索（find） → glob_search"
        "\n  ファイル内容検索（grep/rg/ack） → grep_search"
        "\n\n【適切な使用場面】"
        "run_commandは専用ツールが存在しないシステムコマンドにのみ使用する:"
        "テスト実行（pytest, npm test等）、ビルド（make, npm run build等）、"
        "lint/フォーマッタ（ruff, eslint等）、Git操作（git status, git commit等）、"
        "パッケージ管理（pip, npm, uv等）、その他のシステムコマンド。"
        "\n\n【エッジケース】"
        "危険なコマンドは自動ブロックされSecurityErrorを返す。"
        "タイムアウト超過時はタイムアウトエラーを返す。"
        "存在しないコマンドの場合はシェルのエラーを返す。"
        "\n\n【タイムアウト】"
        "デフォルト120秒、最大600秒。長時間実行されるコマンドはタイムアウトで中断される。"
        "\n\n【作業ディレクトリ】"
        "cdコマンドで作業ディレクトリを変更できる。変更は次回以降のrun_command呼び出しにも引き継がれる。"
        "\n\n【安全性】"
        "rm -rf /、mkfs、dd of=/dev/ 等の危険なコマンドは自動的にブロックされる。"
        "破壊的な操作（rm -rf、git reset --hard等）を"
        "実行する前に、ユーザーに確認を取ること。"
        "\n\n【アンチパターン】"
        "上記の専用ツール優先ルールに該当する操作にrun_commandを使ってはいけない。"
        "危険なコマンドを実行しようとしてはいけない（自動ブロックされる）。"
    )
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    cwd: Path = Field(default_factory=Path.cwd)
    allowed_dirs: AllowedDirectories | None = None
    working_dir: WorkingDirectory | None = None

    def _run(self, command: str, **_kwargs: Any) -> str:
        if is_dangerous_command(command):
            msg = f"危険なコマンドが検出されました: {command}"
            raise SecurityError(msg)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, self._execute(command))
            return future.result()

    async def _execute(self, command: str) -> str:
        """コマンドを非同期で実行する."""
        if sys.platform == "win32":
            return await self._execute_windows(command)
        return await self._execute_unix(command)

    async def _execute_unix(self, command: str) -> str:
        """Unix系でコマンドを実行する."""
        wrapped = _wrap_with_cwd_capture(command)
        return await self._run_subprocess(wrapped)

    async def _execute_windows(self, command: str) -> str:
        """Windowsでバッチファイル経由でコマンドを実行する.

        バッチファイルにより:
        - 元コマンドの exit code を保持
        - %CD% で cd 後のディレクトリを正しく取得
        """
        command = _translate_for_windows(command)
        bat_path: str | None = None
        try:
            fd, bat_path = tempfile.mkstemp(suffix=".bat")
            bat_content = (
                f"@{command}\r\n"
                f"@set __EC=%ERRORLEVEL%\r\n"
                f"@echo {_CWD_SENTINEL}:%CD%\r\n"
                "@exit /b %__EC%\r\n"
            )
            os.write(fd, bat_content.encode("mbcs", errors="replace"))
            os.close(fd)
            return await self._run_subprocess(bat_path)
        finally:
            if bat_path and os.path.exists(bat_path):
                os.unlink(bat_path)

    async def _run_subprocess(self, shell_command: str) -> str:
        """サブプロセスを実行して結果を返す共通処理."""
        try:
            process = await asyncio.create_subprocess_shell(
                shell_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.cwd),
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as e:
            msg = f"コマンドがタイムアウトしました ({self.timeout_seconds}秒)"
            raise ToolExecutionError(msg) from e
        except Exception as e:
            msg = f"コマンド実行に失敗しました: {e}"
            raise ToolExecutionError(msg) from e

        # Windows はシステムコードページ(CP932等)のため mbcs を使用
        enc = "mbcs" if sys.platform == "win32" else "utf-8"

        output_parts: list[str] = []
        if stdout:
            raw_stdout, new_cwd = _parse_cwd_from_output(
                stdout.decode(enc, errors="replace")
            )
            if new_cwd:
                try:
                    candidate = Path(new_cwd.strip())
                    if candidate.is_dir():
                        if (
                            self.allowed_dirs
                            and not self.allowed_dirs.is_within_allowed(candidate)
                        ):
                            output_parts.append(
                                "[警告] 許可ディレクトリ外への移動は制限されています"
                            )
                        else:
                            self.cwd = candidate
                            if self.working_dir is not None:
                                self.working_dir.path = candidate
                except OSError:
                    pass
            if raw_stdout.strip():
                output_parts.append(raw_stdout)
        if stderr:
            stderr_text = stderr.decode(enc, errors="replace")
            output_parts.append(f"[stderr]\n{stderr_text}")
        if process.returncode != 0:
            output_parts.append(f"[exit code: {process.returncode}]")

        output = "\n".join(output_parts) if output_parts else "(出力なし)"

        # 出力のトランケーション
        lines = output.splitlines()
        if len(lines) > 200:
            output = "\n".join(lines[:200]) + f"\n... ({len(lines) - 200}行省略)"

        return output
