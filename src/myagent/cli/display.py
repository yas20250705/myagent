"""CLI表示モジュール.

Richによるストリーミング出力、スピナー、確認プロンプト、Markdownレンダリングを提供する。
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.text import Text

from myagent.agent.events import AgentEvent

console = Console()

_active_spinner: Status | None = None


def _start_spinner(tool_name: str) -> None:
    """ツール実行中スピナーを開始する."""
    global _active_spinner
    _stop_spinner()
    message = f"[cyan]{tool_name}[/cyan] を実行中..."
    _active_spinner = console.status(message, spinner="dots")
    _active_spinner.__enter__()


def _stop_spinner() -> None:
    """アクティブなスピナーを停止する."""
    global _active_spinner
    if _active_spinner is not None:
        _active_spinner.__exit__(None, None, None)
        _active_spinner = None


def render_markdown(text: str) -> None:
    """Markdownテキストをレンダリングして表示する."""
    md = Markdown(text)
    console.print(md)


def print_token(token: str) -> None:
    """ストリーミングトークンをインラインで出力する."""
    console.print(token, end="", highlight=False)


def print_tool_start(tool_name: str, arguments: dict[str, object]) -> None:
    """ツール実行開始を表示する."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    console.print(
        Panel(
            f"[bold cyan]{tool_name}[/bold cyan]({args_str})",
            title="Tool",
            border_style="cyan",
        )
    )


def print_tool_end(tool_name: str, result: str, is_success: bool = True) -> None:
    """ツール実行結果を表示する."""
    style = "green" if is_success else "red"
    status = "OK" if is_success else "ERROR"
    # 結果が長い場合はトランケート
    display_result = result
    lines = result.splitlines()
    if len(lines) > 20:
        display_result = "\n".join(lines[:20]) + f"\n... ({len(lines) - 20}行省略)"
    console.print(
        Panel(
            display_result,
            title=f"{tool_name} [{status}]",
            border_style=style,
        )
    )


def print_error(message: str) -> None:
    """エラーメッセージを表示する."""
    console.print(f"[bold red]エラー:[/bold red] {message}")


def print_success(message: str) -> None:
    """成功メッセージを表示する."""
    console.print(f"[bold green]{message}[/bold green]")


def print_token_usage(
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    model_name: str = "",
) -> None:
    """トークン使用量と推定コストを表示する."""
    from myagent.llm.cost import estimate_cost_usd

    cost = estimate_cost_usd(model_name, prompt_tokens, completion_tokens)
    cost_str = f" / 推定コスト: ${cost:.6f}" if cost is not None else ""
    console.print(
        f"[dim]トークン使用量: プロンプト={prompt_tokens:,} "
        f"補完={completion_tokens:,} 合計={total_tokens:,}{cost_str}[/dim]"
    )


def _build_confirm_details(tool_name: str, tool_input: dict[str, Any]) -> Text:
    """確認プロンプト用の詳細テキストを構築する."""
    text = Text()

    if tool_name == "write_file":
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        lines = content.splitlines()
        preview = "\n".join(lines[:20])
        if len(lines) > 20:
            preview += f"\n... ({len(lines) - 20}行省略)"
        text.append(f"ファイル: {file_path}\n", style="bold")
        text.append("内容プレビュー:\n", style="dim")
        text.append(preview)

    elif tool_name == "edit_file":
        file_path = tool_input.get("file_path", "")
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        text.append(f"ファイル: {file_path}\n", style="bold")
        text.append("--- 変更前\n", style="red")
        text.append(old_string + "\n")
        text.append("+++ 変更後\n", style="green")
        text.append(new_string)

    else:
        text.append(f"ツール: {tool_name}\n", style="bold")
        for k, v in tool_input.items():
            v_str = str(v)
            if len(v_str) > 200:
                v_str = v_str[:200] + "..."
            text.append(f"  {k}: {v_str}\n")

    return text


def confirm_action(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """ユーザーにツール実行の確認を求める.

    Args:
        tool_name: 実行しようとしているツール名。
        tool_input: ツールへの入力パラメータ。

    Returns:
        ユーザーが承認した場合True。
    """
    while True:
        details = _build_confirm_details(tool_name, tool_input)
        console.print(
            Panel(
                Text.assemble(
                    Text("確認が必要です\n\n", style="bold yellow"),
                    details,
                ),
                border_style="yellow",
            )
        )
        raw = console.input("[bold]実行しますか？ (y/n/diff): [/bold]")
        response = raw.strip().lower()
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        if response == "diff":
            # diff を選んだ場合は詳細を再表示してもう一度尋ねる
            continue
        # 想定外の入力はもう一度尋ねる
        console.print("[yellow]y, n, diff のいずれかを入力してください[/yellow]")


def create_spinner(message: str = "処理中...") -> Status:
    """スピナーを作成する."""
    return console.status(message, spinner="dots")


def handle_event(event: AgentEvent) -> None:
    """AgentEventを受け取り適切な表示を行う."""
    if event.event_type == "stream_token":
        print_token(event.data.get("token", ""))
    elif event.event_type == "tool_start":
        tool_name = event.data.get("tool_name", "")
        _start_spinner(tool_name)
    elif event.event_type == "tool_end":
        _stop_spinner()
        print_tool_end(
            event.data.get("tool_name", ""),
            event.data.get("result", ""),
            event.data.get("is_success", True),
        )
    elif event.event_type == "agent_complete":
        console.print()  # 改行
        print_success("完了しました")
        total = event.data.get("total_tokens", 0)
        if total > 0:
            print_token_usage(
                event.data.get("prompt_tokens", 0),
                event.data.get("completion_tokens", 0),
                total,
                event.data.get("model_name", ""),
            )
    elif event.event_type == "agent_error":
        console.print()  # 改行
        print_error(event.data.get("error", "不明なエラー"))
