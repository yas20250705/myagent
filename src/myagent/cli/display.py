"""CLI表示モジュール.

Richによるストリーミング出力、スピナー、確認プロンプト、Markdownレンダリングを提供する。
"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status

from myagent.agent.events import AgentEvent

console = Console()


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


def confirm_action(action: str, details: str) -> bool:
    """ユーザーに確認を求める.

    Args:
        action: 実行しようとしているアクション名。
        details: アクションの詳細。

    Returns:
        ユーザーが承認した場合True。
    """
    console.print(
        Panel(
            f"[bold yellow]確認が必要です[/bold yellow]\n\n"
            f"アクション: {action}\n"
            f"詳細: {details}",
            border_style="yellow",
        )
    )
    response = console.input("[bold]実行しますか？ (y/n): [/bold]")
    return response.strip().lower() in ("y", "yes")


def create_spinner(message: str = "処理中...") -> Status:
    """スピナーを作成する."""
    return console.status(message, spinner="dots")


def handle_event(event: AgentEvent) -> None:
    """AgentEventを受け取り適切な表示を行う."""
    if event.event_type == "stream_token":
        print_token(event.data.get("token", ""))
    elif event.event_type == "tool_start":
        print_tool_start(
            event.data.get("tool_name", ""),
            event.data.get("arguments", {}),
        )
    elif event.event_type == "tool_end":
        print_tool_end(
            event.data.get("tool_name", ""),
            event.data.get("result", ""),
            event.data.get("is_success", True),
        )
    elif event.event_type == "agent_complete":
        console.print()  # 改行
        print_success("完了しました")
    elif event.event_type == "agent_error":
        console.print()  # 改行
        print_error(event.data.get("error", "不明なエラー"))
