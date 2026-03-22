"""REPL対話ループとワンショット実行.

prompt_toolkitによる入力制御とエージェント実行を提供する。
"""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from myagent.agent.executor import Executor
from myagent.agent.graph import AgentRunner
from myagent.agent.prompt_manager import PromptManager
from myagent.cli.display import (
    confirm_action,
    console,
    handle_event,
    print_error,
    print_success,
    render_markdown,
)
from myagent.cli.slash_router import SlashCommandRouter
from myagent.commands.manager import (
    CommandManager,
    build_command_manager,
    parse_cli_args,
)
from myagent.infra.config import AppConfig
from myagent.infra.context import ContextManager
from myagent.llm.router import LLMRouter
from myagent.plugins.manager import PluginManager
from myagent.skills.manager import SkillManager
from myagent.tools.mcp_tools import MCPManager
from myagent.tools.registry import create_default_registry


def _build_command_manager(config: AppConfig) -> CommandManager:
    """設定から CommandManager を構築してコマンドをロードする."""
    return build_command_manager(
        project_commands_dir_str=config.command.project_commands_dir,
        global_commands_dir_str=config.command.global_commands_dir,
    )


def _build_skill_manager(config: AppConfig) -> SkillManager:
    """設定から SkillManager を構築してスキルをロードする."""
    project_dir_str = config.skill.project_skills_dir
    global_dir_str = config.skill.global_skills_dir

    project_dir = Path(project_dir_str) if project_dir_str else None
    global_dir = Path(global_dir_str) if global_dir_str else None

    # プラグインのスキルディレクトリを収集する
    plugin_manager = PluginManager(
        enabled_plugins=config.plugin.enabled_plugins,
    )
    extra_dirs = plugin_manager.get_skill_dirs()

    manager = SkillManager(
        project_skills_dir=project_dir,
        global_skills_dir=global_dir,
        extra_skill_dirs=extra_dirs if extra_dirs else None,
    )
    manager.load_all()
    return manager


def _resolve_skill_input(
    user_input: str,
    skill_manager: SkillManager,
) -> tuple[str, str | None]:
    """スキルアクティベーションを解決して実際の入力とスキル名を返す.

    スラッシュコマンド（/skill-name）または自動マッチングによってスキルを
    アクティベートする。スキル本文をメッセージに注入して返す。

    Args:
        user_input: ユーザーの元の入力。
        skill_manager: SkillManager インスタンス。

    Returns:
        (effective_input, activated_skill_name) のタプル。
        スキルが見つからない場合は (user_input, None)。
    """
    # 明示的スラッシュコマンド: /skill-name [追加指示]
    if user_input.startswith("/") and not user_input.startswith("//"):
        parts = user_input[1:].split(None, 1)
        skill_name = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        skill = skill_manager.activate(skill_name)
        if skill is not None:
            effective = f"## アクティブスキル: {skill.meta.name}\n\n{skill.body}"
            if rest:
                effective += f"\n\n## 指示\n\n{rest}"
            return effective, skill.meta.name

    # 自動キーワードマッチング
    matches = skill_manager.find_matching(user_input)
    if matches:
        skill = skill_manager.activate(matches[0].name)
        if skill is not None:
            effective = (
                f"## アクティブスキル: {skill.meta.name}\n\n{skill.body}"
                f"\n\n## 指示\n\n{user_input}"
            )
            return effective, skill.meta.name

    return user_input, None


def _resolve_command_input(
    user_input: str,
    command_manager: CommandManager,
) -> tuple[str, str | None]:
    """カスタムコマンドを解決して展開済みプロンプトとコマンド名を返す.

    スラッシュで始まる入力をカスタムコマンドとして解決する。
    コマンドが見つかった場合はテンプレートを展開して返す。

    Args:
        user_input: ユーザーの入力（スラッシュで始まるコマンド入力）。
        command_manager: CommandManager インスタンス。

    Returns:
        (effective_input, command_name) のタプル。
        コマンドが見つからない場合は (user_input, None)。
    """
    if not user_input.startswith("/") or user_input.startswith("//"):
        return user_input, None

    parts = user_input[1:].split(None, 1)
    command_name = parts[0]
    raw_args = parts[1] if len(parts) > 1 else ""

    cmd = command_manager.get(command_name)
    if cmd is None:
        return user_input, None

    args = parse_cli_args(raw_args)
    try:
        expanded = cmd.render(args)
        return expanded, command_name
    except ValueError as e:
        print_error(str(e))
        return user_input, None


async def _create_runner(config: AppConfig) -> tuple[AgentRunner, MCPManager]:
    """設定からAgentRunnerとMCPManagerを構築する.

    Returns:
        (AgentRunner, MCPManager) のタプル。
        MCPManagerはアプリ終了時に disconnect_all を呼ぶこと。
    """
    from pathlib import Path

    router = LLMRouter(
        config=config.llm,
        openai_api_key=config.openai_api_key,
        google_api_key=config.google_api_key,
    )
    model = router.get_model_for_bind_tools()
    extra_dirs = [Path(d) for d in config.tool.allowed_directories]

    # 有効プラグインのスキルディレクトリを許可リストに追加
    plugin_mgr = PluginManager(
        enabled_plugins=config.plugin.enabled_plugins,
    )
    extra_dirs.extend(plugin_mgr.get_skill_dirs())

    wd_str = config.tool.working_directory
    initial_cwd = Path(wd_str) if wd_str else None
    registry = create_default_registry(
        extra_allowed_dirs=extra_dirs or None,
        initial_cwd=initial_cwd,
        web_search_api_key=config.exa_api_key,
        web_search_timeout=config.web_search.timeout,
        web_search_default_num_results=(
            config.web_search.default_num_results
        ),
        web_fetch_timeout=config.web_fetch.timeout,
        web_fetch_max_size_bytes=config.web_fetch.max_size_bytes,
        web_search_fallback_enabled=(
            config.web_search.fallback_enabled
        ),
        web_search_backend_names=(
            config.web_search.search_backends
        ),
    )

    # MCPサーバーに接続してツールを動的登録する
    mcp_manager = MCPManager(config.mcp)
    if config.mcp.servers:
        await mcp_manager.connect_all(registry)

    tools = registry.list_tools()
    executor = Executor(confirmation_level=config.tool.confirmation_level)

    context_manager = ContextManager(
        max_context_tokens=config.agent.context_window_tokens,
        max_output_lines=config.tool.max_output_lines,
    )
    # working_directory が設定されている場合はプロジェクトインデックスを構築
    index_root = initial_cwd or Path.cwd()
    context_manager.build_project_index(index_root)

    prompt_manager = PromptManager()

    runner = AgentRunner(
        model=model,
        tools=tools,
        max_loops=config.agent.max_loops,
        executor=executor,
        confirm_callback=confirm_action,
        context_manager=context_manager,
        prompt_manager=prompt_manager,
        tool_registry=registry,
        max_parallel_workers=config.agent.max_parallel_workers,
        langsmith_project=config.langchain_project if config.langchain_tracing else "",
    )
    return runner, mcp_manager


async def run_oneshot(config: AppConfig, instruction: str) -> None:
    """ワンショットでエージェントを実行する.

    Args:
        config: アプリケーション設定。
        instruction: ユーザーからの指示テキスト。
    """
    mcp_manager = None
    try:
        runner, mcp_manager = await _create_runner(config)
        skill_manager = _build_skill_manager(config)
        command_manager = _build_command_manager(config)

        # カスタムコマンドの解決（スラッシュで始まる場合）
        effective_input = instruction
        if instruction.startswith("/") and not instruction.startswith("//"):
            cmd_input, cmd_name = _resolve_command_input(instruction, command_manager)
            if cmd_name:
                console.print(f"[cyan]コマンド '{cmd_name}' を実行[/cyan]")
                effective_input = cmd_input
            else:
                # スキルとして解決を試みる
                skill_input, skill_name = _resolve_skill_input(
                    instruction, skill_manager
                )
                if skill_name:
                    console.print(
                        f"[cyan]スキル '{skill_name}' をアクティベート[/cyan]"
                    )
                    effective_input = skill_input
        else:
            effective_input, skill_name = _resolve_skill_input(
                instruction, skill_manager
            )
            if skill_name:
                console.print(
                    f"[cyan]スキル '{skill_name}' をアクティベート[/cyan]"
                )

        async for event in runner.run_with_events(effective_input):
            handle_event(event)
        console.print()  # 最終改行
    except KeyboardInterrupt:
        console.print("\n[yellow]中断しました[/yellow]")
    except Exception as e:
        print_error(str(e))
    finally:
        if mcp_manager is not None:
            await mcp_manager.disconnect_all()


def _show_startup_info(config: AppConfig) -> None:
    """起動時の情報表示（作業ディレクトリ、APIキー案内）.

    Args:
        config: アプリケーション設定。
    """
    wd = config.tool.working_directory
    if wd:
        console.print(f"[dim]作業ディレクトリ: {wd}[/dim]")

    if config.langchain_tracing:
        console.print(
            f"[dim]LangSmith トレース有効 (project: {config.langchain_project})[/dim]"
        )

    if not config.openai_api_key and not config.google_api_key:
        console.print(
            "[yellow]⚠ APIキーが設定されていません。"
            "以下のいずれかで設定してください:[/yellow]\n"
            "  [dim]・環境変数: export OPENAI_API_KEY=sk-...[/dim]\n"
            "  [dim]・.env ファイル: OPENAI_API_KEY=sk-...[/dim]"
        )
        console.print()


async def run_repl(config: AppConfig) -> None:
    """REPL対話ループを実行する.

    Args:
        config: アプリケーション設定。
    """
    render_markdown(
        "# myagent\nAIコーディングアシスタント\n\n`exit` で終了、`/help` でヘルプを表示"
    )
    console.print()
    _show_startup_info(config)

    session: PromptSession[str] = PromptSession(history=InMemoryHistory())

    runner, mcp_manager = await _create_runner(config)
    skill_manager = _build_skill_manager(config)
    command_manager = _build_command_manager(config)
    slash_router = SlashCommandRouter(config)

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
            await mcp_manager.disconnect_all()
            break

        # 組み込みコマンド（優先度最高）
        if user_input.lower() in ("help", "h", "?", "/help"):
            _show_help(command_manager, slash_router)
            continue

        if user_input.lower() in ("/stats", "stats"):
            _show_stats(runner)
            continue

        if user_input.lower() in ("/status", "status"):
            _show_status(runner)
            continue

        if user_input.lower() in ("/clear", "clear"):
            runner.clear_history()
            print_success("会話履歴をクリアしました")
            continue

        # 管理コマンド（/plugin, /skill, /command, /config, /set-config, /mcp）
        # スラッシュなしでも受け付ける（例: "plugin list" → "/plugin list"）
        _slash_input = user_input if user_input.startswith("/") else f"/{user_input}"
        if not _slash_input.startswith("//"):
            handled = await slash_router.try_handle(_slash_input)
            if handled:
                continue

        # スラッシュで始まる入力の処理（カスタムコマンド → スキル の順）
        if user_input.startswith("/") and not user_input.startswith("//"):
            # 1. カスタムコマンドの解決を試みる
            cmd_input, cmd_name = _resolve_command_input(user_input, command_manager)
            if cmd_name:
                console.print(f"[cyan]コマンド '{cmd_name}' を実行[/cyan]")
                effective_input = cmd_input
            else:
                # 2. スキルとして解決を試みる
                skill_input, skill_name = _resolve_skill_input(
                    user_input, skill_manager
                )
                if skill_name:
                    console.print(
                        f"[cyan]スキル '{skill_name}' をアクティベート[/cyan]"
                    )
                    effective_input = skill_input
                else:
                    # 未定義コマンドの場合は類似コマンドを提案
                    from myagent.infra.errors import CommandNotFoundError

                    parts = user_input[1:].split(None, 1)
                    cmd_name_attempt = parts[0] if parts else ""
                    similar = command_manager.find_similar(cmd_name_attempt)
                    if similar:
                        try:
                            raise CommandNotFoundError(cmd_name_attempt, similar)
                        except CommandNotFoundError as e:
                            print_error(str(e))
                        continue
                    else:
                        # スラッシュで始まるが未定義 → 通常入力として処理
                        effective_input = user_input
        else:
            # スキルの自動キーワードマッチング → 通常指示
            effective_input, skill_name = _resolve_skill_input(
                user_input, skill_manager
            )
            if skill_name:
                console.print(
                    f"[cyan]スキル '{skill_name}' をアクティベート[/cyan]"
                )

        try:
            async for event in runner.run_with_events(effective_input):
                handle_event(event)
            console.print()  # 改行
        except KeyboardInterrupt:
            console.print("\n[yellow]中断しました[/yellow]")
        except Exception as e:
            print_error(str(e))


def _show_stats(runner: AgentRunner) -> None:
    """セッションメトリクスを表示する."""
    from rich.table import Table

    summary = runner.metrics.summary()
    success_pct = summary["success_rate"] * 100

    calls = summary["tool_calls"]
    ok = summary["tool_successes"]
    ng = summary["tool_failures"]
    render_markdown(f"""## セッションメトリクス

- **ステップ数**: {summary["steps"]}
- **ツール呼び出し**: {calls}回（成功: {ok}、失敗: {ng}）
- **ツール成功率**: {success_pct:.1f}%
""")

    tool_details = summary.get("tool_details", {})
    if tool_details:
        table = Table(title="ツール別メトリクス")
        table.add_column("ツール名", style="cyan")
        table.add_column("成功", justify="right", style="green")
        table.add_column("失敗", justify="right", style="red")
        table.add_column("合計", justify="right")
        table.add_column("成功率", justify="right")

        for name, detail in tool_details.items():
            rate_pct = detail["success_rate"] * 100
            table.add_row(
                name,
                str(detail["successes"]),
                str(detail["failures"]),
                str(detail["total"]),
                f"{rate_pct:.0f}%",
            )

        console.print(table)


def _show_status(runner: AgentRunner) -> None:
    """現在のセッション状態を表示する."""
    summary = runner.metrics.summary()
    ctx = runner._context_manager
    token_count = (
        ctx.messages_token_count(runner._history)
        if ctx is not None and runner._history
        else 0
    )

    render_markdown(f"""## セッション状態

- **ステップ数**: {summary["steps"]}
- **ツール呼び出し**: {summary["tool_calls"]}回
- **コンテキストトークン数**: {token_count:,}
""")


def _show_help(
    command_manager: CommandManager | None = None,
    slash_router: SlashCommandRouter | None = None,
) -> None:
    """ヘルプを表示する."""
    custom_cmds = ""
    if command_manager is not None:
        commands = command_manager.load_all()
        if commands:
            lines = ["\n## カスタムコマンド\n"]
            for cmd in sorted(commands, key=lambda c: c.name):
                scope_label = "プロジェクト" if cmd.scope == "project" else "グローバル"
                lines.append(f"- `/{cmd.name}` [{scope_label}] - {cmd.description}")
            custom_cmds = "\n".join(lines)

    mgmt_cmds = ""
    if slash_router is not None:
        mgmt_cmds = "\n" + slash_router.get_help_text() + "\n"

    render_markdown(f"""## 組み込みコマンド

- `exit` / `quit` / `q` - 終了
- `/help` / `help` / `h` / `?` - このヘルプを表示
- `/stats` - セッションメトリクスを表示
- `/status` - セッション状態（トークン使用量等）を表示
- `/clear` - 会話履歴をクリアする
{mgmt_cmds}{custom_cmds}
## 使い方

自然言語で指示を入力してください。例:

- `このディレクトリのPythonファイルを一覧表示して`
- `README.mdを読んで内容を要約して`
- `src/main.pyにhello関数を追加して`

カスタムコマンドは `/<command-name> [--arg value]` で実行できます。
""")
