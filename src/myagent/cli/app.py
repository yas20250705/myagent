"""REPL対話ループとワンショット実行.

prompt_toolkitによる入力制御とエージェント実行を提供する。
"""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from myagent.agent.executor import Executor
from myagent.agent.graph import AgentRunner
from myagent.cli.display import (
    confirm_action,
    console,
    handle_event,
    print_error,
    print_success,
    render_markdown,
)
from myagent.infra.config import AppConfig
from myagent.infra.context import ContextManager
from myagent.llm.router import LLMRouter
from myagent.tools.registry import create_default_registry


def _create_runner(config: AppConfig) -> AgentRunner:
    """設定からAgentRunnerを構築する."""
    from pathlib import Path

    router = LLMRouter(
        config=config.llm,
        openai_api_key=config.openai_api_key,
        google_api_key=config.google_api_key,
    )
    model = router.get_model_for_bind_tools()
    extra_dirs = [Path(d) for d in config.tool.allowed_directories]
    wd_str = config.tool.working_directory
    initial_cwd = Path(wd_str) if wd_str else None
    registry = create_default_registry(
        extra_allowed_dirs=extra_dirs or None,
        initial_cwd=initial_cwd,
    )
    tools = registry.list_tools()
    executor = Executor(confirmation_level=config.tool.confirmation_level)

    context_manager = ContextManager(
        max_context_tokens=config.agent.context_window_tokens,
        max_output_lines=config.tool.max_output_lines,
    )
    # working_directory が設定されている場合はプロジェクトインデックスを構築
    index_root = initial_cwd or Path.cwd()
    context_manager.build_project_index(index_root)

    return AgentRunner(
        model=model,
        tools=tools,
        max_loops=config.agent.max_loops,
        executor=executor,
        confirm_callback=confirm_action,
        context_manager=context_manager,
    )


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
        "# myagent\nAIコーディングアシスタント\n\n`exit` で終了、`help` でヘルプを表示"
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
