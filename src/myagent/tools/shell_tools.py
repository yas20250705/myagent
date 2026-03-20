"""シェルコマンド実行ツール.

危険コマンドの検知とブロック機能を提供する。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import re
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import Field

from myagent.infra.errors import SecurityError, ToolExecutionError

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


def is_dangerous_command(command: str) -> bool:
    """コマンドが危険なパターンに一致するか判定する."""
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return True
    return False


class RunCommandTool(BaseTool):
    """シェルコマンドを実行するツール."""

    name: str = "run_command"
    description: str = (
        "シェルコマンドを実行する。"
        "commandに実行するコマンド文字列を指定する。"
    )
    timeout_seconds: int = Field(default=120, ge=1, le=600)

    def _run(self, command: str, **_kwargs: Any) -> str:
        if is_dangerous_command(command):
            msg = f"危険なコマンドが検出されました: {command}"
            raise SecurityError(msg)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, self._execute(command))
            return future.result()

    async def _execute(self, command: str) -> str:
        """コマンドを非同期で実行する."""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as e:
            msg = (
                f"コマンドがタイムアウトしました"
                f" ({self.timeout_seconds}秒): {command}"
            )
            raise ToolExecutionError(msg) from e
        except Exception as e:
            msg = f"コマンド実行に失敗しました: {e}"
            raise ToolExecutionError(msg) from e

        output_parts: list[str] = []
        if stdout:
            output_parts.append(stdout.decode("utf-8", errors="replace"))
        if stderr:
            output_parts.append(f"[stderr]\n{stderr.decode('utf-8', errors='replace')}")
        if process.returncode != 0:
            output_parts.append(f"[exit code: {process.returncode}]")

        output = "\n".join(output_parts) if output_parts else "(出力なし)"

        # 出力のトランケーション
        lines = output.splitlines()
        if len(lines) > 200:
            output = "\n".join(lines[:200]) + f"\n... ({len(lines) - 200}行省略)"

        return output
