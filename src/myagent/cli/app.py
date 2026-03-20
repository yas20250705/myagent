"""REPL対話ループとワンショット実行.

prompt_toolkitによる入力制御とエージェント実行を提供する。
"""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from myagent.agent.graph import AgentRunner
from myagent.cli.display import (
    console,
    handle_event,
    print_error,
    print_success,
    render_markdown,
)
from myagent.infra.config import AppConfig
from myagent.llm.router import LLMRouter
from myagent.tools.registry import create_default_registry


def _create_runner(config: AppConfig) -> AgentRunner:
    """設定からAgentRunnerを構築する."""
    router = LLMRouter(config=config.llm)
    model = router.get_model_for_bind_tools()
    registry = create_default_registry()
    tools = registry.list_tools()
    return AgentRunner(model=model, tools=tools, max_loops=config.agent.max_loops)


async def run_oneshot(config: AppConfig, instruction: str) -> None:
    """ワンショットでエージェントを実行する.

    Args:
        config: アプリケーション設定。
        instruction: ユーザーからの指示テキスト。
    """
    try:
        runner = _create_runner(config)
        async for event in runner.run_with_events(instruction):
            handle_event(event)
        console.print()  # 最終改行
    except KeyboardInterrupt:
        console.print("\n[yellow]中断しました[/yellow]")
    except Exception as e:
        print_error(str(e))


async def run_repl(config: AppConfig) -> None:
    """REPL対話ループを実行する.

    Args:
        config: アプリケーション設定。
    """
    render_markdown(
        "# myagent\nAIコーディングアシスタント\n\n"
        "`exit` で終了、`help` でヘルプを表示"
    )
    console.print()

    session: PromptSession[str] = PromptSession(history=InMemoryHistory())

    runner = _create_runner(config)

    while True:
        try:
            user_input = await session.prompt_async("myagent> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]終了します[/yellow]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print_success("終了します")
            break

        if user_input.lower() in ("help", "h", "?"):
            _show_help()
            continue

        try:
            async for event in runner.run_with_events(user_input):
                handle_event(event)
            console.print()  # 改行
        except KeyboardInterrupt:
            console.print("\n[yellow]中断しました[/yellow]")
        except Exception as e:
            print_error(str(e))


def _show_help() -> None:
    """ヘルプを表示する."""
    render_markdown("""## コマンド

- `exit` / `quit` / `q` - 終了
- `help` / `h` / `?` - このヘルプを表示

## 使い方

自然言語で指示を入力してください。例:

- `このディレクトリのPythonファイルを一覧表示して`
- `README.mdを読んで内容を要約して`
- `src/main.pyにhello関数を追加して`
""")
