"""CLIコマンド定義.

clickを使用したコマンドラインインターフェースを定義する。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

import click

from myagent.cli.display import print_error, print_success, render_markdown
from myagent.infra.config import AppConfig, load_config, save_config

if TYPE_CHECKING:
    from myagent.plugins.manager import PluginManager
    from myagent.skills.manager import SkillManager


def _get_version() -> str:
    """パッケージバージョンを取得する.

    Returns:
        パッケージバージョン文字列。取得に失敗した場合は "unknown"。
    """
    try:
        from importlib.metadata import version

        return version("myagent")
    except Exception:
        return "unknown"


@click.group(invoke_without_command=True)
@click.version_option(version=_get_version(), prog_name="myagent")
@click.option(
    "-r",
    "--run",
    "instruction",
    default=None,
    help="ワンショット実行する指示テキスト",
)
@click.option(
    "-c",
    "--command",
    "command_name",
    default=None,
    help="カスタムコマンドをワンショット実行する（コマンド名を指定）",
)
@click.option(
    "--command-args",
    "command_args_str",
    default=None,
    help="カスタムコマンドへの引数（例: '--target src/ --cmd pytest'）",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False),
    default=None,
    help="設定ファイルパス",
)
@click.option(
    "--working-dir",
    "working_dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=None,
    help="作業ディレクトリを明示的に指定する",
)
@click.pass_context
def cli(
    ctx: click.Context,
    instruction: str | None,
    command_name: str | None,
    command_args_str: str | None,
    config_path: str | None,
    working_dir: str | None,
) -> None:
    """myagent - AI コーディングアシスタント CLI."""
    ctx.ensure_object(dict)

    # カレントディレクトリの取得とアクセス権チェック
    cwd = Path(working_dir) if working_dir else Path.cwd()
    if not os.access(cwd, os.R_OK):
        print_error(
            f"作業ディレクトリへの読み取り権限がありません: {cwd}"
        )
        ctx.exit(1)
        return

    # 設定ファイルの読み込み（階層マージ対応）
    explicit_config_path = Path(config_path) if config_path else None
    try:
        config = load_config(
            config_path=explicit_config_path,
            project_config_dir=cwd if explicit_config_path is None else None,
        )
    except Exception as e:
        print_error(f"設定読み込みエラー: {e}")
        ctx.exit(1)
        return

    # 作業ディレクトリの決定: --working-dir > cwd（configの値は使わない）
    if working_dir:
        config.tool.working_directory = working_dir
    else:
        config.tool.working_directory = str(cwd)

    # cwdベースのコマンド・スキルディレクトリを設定
    cwd_commands = cwd / ".myagent" / "commands"
    cwd_skills = cwd / ".myagent" / "skills"
    if cwd_commands.is_dir():
        config.command.project_commands_dir = str(cwd_commands)
    if cwd_skills.is_dir():
        config.skill.project_skills_dir = str(cwd_skills)

    ctx.obj["config"] = config

    if ctx.invoked_subcommand is not None:
        return

    if command_name:
        # カスタムコマンドのワンショット実行
        _run_command(config, command_name, command_args_str or "")
    elif instruction:
        # ワンショット実行
        _run_oneshot(config, instruction)
    else:
        # REPL モード
        from myagent.cli.app import run_repl

        asyncio.run(run_repl(config))


@cli.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """現在の設定を表示する."""
    app_config: AppConfig = ctx.obj["config"]

    config_text = f"""## 現在の設定

### LLM
- プロバイダ: {app_config.llm.provider}
- モデル: {app_config.llm.model}
- フォールバック: {app_config.llm.fallback_provider or "なし"} \
/ {app_config.llm.fallback_model or "なし"}
- 最大リトライ: {app_config.llm.max_retries}
- Temperature: {app_config.llm.temperature}

### ツール
- 確認レベル: {app_config.tool.confirmation_level}
- 最大出力行数: {app_config.tool.max_output_lines}

### エージェント
- 最大ループ回数: {app_config.agent.max_loops}

### APIキー
- OpenAI: {"設定済み" if app_config.openai_api_key else "未設定"}
- Google: {"設定済み" if app_config.google_api_key else "未設定"}
- Exa (Web検索): {"設定済み" if app_config.exa_api_key else "未設定"}
"""
    render_markdown(config_text)


@cli.command()
@click.option(
    "--provider",
    type=click.Choice(["openai", "gemini"]),
    help="プライマリLLMプロバイダ",
)
@click.option("--model", help="プライマリモデル名")
@click.option(
    "--fallback-provider",
    type=click.Choice(["openai", "gemini"]),
    help="フォールバックLLMプロバイダ",
)
@click.option("--fallback-model", help="フォールバックモデル名")
@click.option(
    "--confirmation-level",
    type=click.Choice(["strict", "normal", "autonomous"]),
    help="確認レベル",
)
@click.pass_context
def set_config(
    ctx: click.Context,
    provider: str | None,
    model: str | None,
    fallback_provider: str | None,
    fallback_model: str | None,
    confirmation_level: str | None,
) -> None:
    """設定を変更して保存する."""
    app_config: AppConfig = ctx.obj["config"]

    if provider:
        app_config.llm.provider = provider  # type: ignore[assignment]
    if model:
        app_config.llm.model = model
    if fallback_provider:
        app_config.llm.fallback_provider = fallback_provider  # type: ignore[assignment]
    if fallback_model:
        app_config.llm.fallback_model = fallback_model
    if confirmation_level:
        app_config.tool.confirmation_level = confirmation_level  # type: ignore[assignment]

    try:
        save_config(app_config)
        print_success("設定を保存しました")
    except Exception as e:
        print_error(f"設定保存エラー: {e}")


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """直近セッションのエージェント精度メトリクスを表示する."""
    from rich.console import Console

    console = Console()
    # 注意: ワンショット実行ではセッションメトリクスは保持されない。
    # REPL内で `/stats` として使用することを想定。
    # ここではサンプル表示として空のメトリクスを表示する。
    console.print(
        "[yellow]セッションメトリクスはREPL実行中にのみ利用可能です。[/yellow]"
    )
    console.print(
        "REPL内で実行後にメトリクスが蓄積されます。\n"
    )
    console.print("使用例: REPLモードで `myagent` を起動し、タスク実行後に確認")


def _run_oneshot(config: AppConfig, instruction: str) -> None:
    """ワンショット実行."""
    from myagent.cli.app import run_oneshot

    asyncio.run(run_oneshot(config, instruction))


def _run_command(config: AppConfig, command_name: str, args_str: str) -> None:
    """カスタムコマンドをワンショット実行する."""
    from myagent.cli.app import run_oneshot
    from myagent.commands.manager import build_command_manager, parse_cli_args
    from myagent.infra.errors import CommandNotFoundError

    manager = build_command_manager(
        project_commands_dir_str=config.command.project_commands_dir,
        global_commands_dir_str=config.command.global_commands_dir,
    )
    cmd = manager.get(command_name)
    if cmd is None:
        similar = manager.find_similar(command_name)
        try:
            raise CommandNotFoundError(command_name, similar)
        except CommandNotFoundError as e:
            print_error(str(e))
            return

    parsed = parse_cli_args(args_str)
    try:
        expanded = cmd.render(parsed)
    except ValueError as e:
        print_error(str(e))
        return

    asyncio.run(run_oneshot(config, expanded))


@cli.group()
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """MCP（Model Context Protocol）サーバー管理コマンド."""
    ctx.ensure_object(dict)


@mcp.command(name="list")
@click.pass_context
def mcp_list(ctx: click.Context) -> None:
    """接続中のMCPサーバー一覧を表示する."""
    from rich.console import Console
    from rich.table import Table

    from myagent.tools.mcp_tools import MCPManager

    app_config: AppConfig = ctx.obj["config"]
    manager = MCPManager(app_config.mcp)

    async def _list() -> None:
        from myagent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        await manager.connect_all(registry)
        statuses = manager.get_status()
        await manager.disconnect_all()

        console = Console()
        if not statuses:
            console.print("[yellow]設定済みのMCPサーバーがありません[/yellow]")
            return

        table = Table(title="MCPサーバー一覧")
        table.add_column("サーバー名", style="cyan")
        table.add_column("ステータス")
        table.add_column("ツール数", justify="right")
        table.add_column("備考")

        for status in statuses:
            status_str = (
                "[green]接続中[/green]" if status.connected else "[red]切断[/red]"
            )
            table.add_row(
                status.name,
                status_str,
                str(status.tool_count),
                status.error or "",
            )

        console.print(table)

    asyncio.run(_list())


@mcp.command(name="test")
@click.argument("server_name")
@click.pass_context
def mcp_test(ctx: click.Context, server_name: str) -> None:
    """指定したMCPサーバーへの接続テストを実行する."""
    from rich.console import Console

    from myagent.tools.mcp_tools import MCPManager

    app_config: AppConfig = ctx.obj["config"]
    manager = MCPManager(app_config.mcp)
    console = Console()

    async def _test() -> None:
        result = await manager.test_server(server_name)
        if result.connected:
            console.print(
                f"[green]✓ MCPサーバー '{server_name}' への接続に成功しました[/green]"
            )
            if result.tools:
                console.print(f"\n利用可能なツール ({len(result.tools)} 個):")
                for tool_name in result.tools:
                    console.print(f"  - {tool_name}")
            else:
                console.print("利用可能なツールがありません")
        else:
            console.print(
                f"[red]✗ MCPサーバー '{server_name}' への接続に失敗しました[/red]"
            )
            if result.error:
                console.print(f"エラー: {result.error}")

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# skill コマンドグループ
# ---------------------------------------------------------------------------


@cli.group()
@click.pass_context
def skill(ctx: click.Context) -> None:
    """スキル（Agent Skills Standard 準拠）管理コマンド."""
    ctx.ensure_object(dict)


@skill.command(name="list")
@click.pass_context
def skill_list(ctx: click.Context) -> None:
    """ロード済みスキル一覧を表示する."""
    from rich.console import Console
    from rich.table import Table

    app_config: AppConfig = ctx.obj["config"]
    manager = _build_skill_manager(app_config)
    skills = manager.load_all()

    console = Console()
    if not skills:
        console.print("[yellow]利用可能なスキルがありません[/yellow]")
        return

    table = Table(title="スキル一覧")
    table.add_column("名前", style="cyan")
    table.add_column("スコープ")
    table.add_column("説明")

    for meta in sorted(skills, key=lambda m: m.name):
        scope_str = (
            "[green]プロジェクト[/green]"
            if meta.scope == "project"
            else "[blue]グローバル[/blue]"
        )
        desc = meta.description
        description = desc[:80] + "..." if len(desc) > 80 else desc
        table.add_row(meta.name, scope_str, description)

    console.print(table)


@skill.command(name="info")
@click.argument("skill_name")
@click.pass_context
def skill_info(ctx: click.Context, skill_name: str) -> None:
    """スキルの詳細を表示する."""
    from rich.console import Console

    app_config: AppConfig = ctx.obj["config"]
    manager = _build_skill_manager(app_config)
    manager.load_all()

    meta = manager.get_metadata(skill_name)
    console = Console()

    if meta is None:
        print_error(f"スキルが見つかりません: {skill_name}")
        return

    console.print(f"\n[bold cyan]{meta.name}[/bold cyan]")
    scope_label = "プロジェクト" if meta.scope == "project" else "グローバル"
    console.print(f"スコープ: {scope_label}")
    console.print(f"説明:\n  {meta.description}")
    if meta.license:
        console.print(f"ライセンス: {meta.license}")
    if meta.compatibility:
        console.print(f"互換性要件: {meta.compatibility}")
    if meta.allowed_tools:
        console.print(f"事前承認ツール: {', '.join(meta.allowed_tools)}")
    if meta.metadata:
        console.print("メタデータ:")
        for k, v in meta.metadata.items():
            console.print(f"  {k}: {v}")
    console.print(f"\nパス: {meta.skill_dir}")

    # ファイル構成を表示
    files = [
        p.relative_to(meta.skill_dir)
        for p in meta.skill_dir.rglob("*")
        if p.is_file()
    ]
    if files:
        console.print("\nファイル構成:")
        for f in sorted(files):
            console.print(f"  {f}")


@skill.command(name="init")
@click.argument("skill_name")
@click.option(
    "--global",
    "is_global",
    is_flag=True,
    default=False,
    help="グローバルスキルとして作成する",
)
@click.pass_context
def skill_init(ctx: click.Context, skill_name: str, is_global: bool) -> None:
    """Agent Skills Standard 準拠のスキル雛形を生成する."""
    from rich.console import Console

    from myagent.skills.loader import _NAME_PATTERN

    console = Console()

    if not _NAME_PATTERN.match(skill_name) or len(skill_name) > 64:
        print_error(
            f"スキル名が命名規則に違反しています: {skill_name!r}\n"
            "小文字英数字とハイフンのみ使用可能です（先頭・末尾はハイフン不可）"
        )
        return

    from pathlib import Path

    app_config: AppConfig = ctx.obj["config"]

    if is_global:
        skills_dir = Path.home() / ".myagent" / "skills"
    else:
        skills_dir = Path(app_config.skill.project_skills_dir)

    skill_dir = skills_dir / skill_name
    if skill_dir.exists():
        print_error(f"スキルディレクトリが既に存在します: {skill_dir}")
        return

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"""---
name: {skill_name}
description: >
  このスキルの説明を記述してください。
  エージェントがユーザーの指示とマッチングする際に使用されます。
license: Apache-2.0
compatibility: ""
metadata:
  author: ""
  version: "1.0"
allowed-tools: ""
---

# {skill_name}

## 概要

このスキルの目的と使い方を記述してください。

## 手順

1. ステップ1
2. ステップ2
3. ステップ3
""",
        encoding="utf-8",
    )

    print_success(f"スキル雛形を生成しました: {skill_dir}")
    console.print(f"SKILL.md を編集して内容を完成させてください: {skill_md}")


@skill.command(name="validate")
@click.argument("path", type=click.Path(exists=True))
def skill_validate(path: str) -> None:
    """SKILL.md フロントマターと命名規則を検証する."""
    from pathlib import Path

    from rich.console import Console

    from myagent.skills.loader import validate_skill_dir

    console = Console()
    skill_dir = Path(path)

    errors = validate_skill_dir(skill_dir)
    if not errors:
        print_success(f"バリデーション成功: {skill_dir}")
    else:
        console.print(f"[red]バリデーションエラー ({len(errors)} 件):[/red]")
        for err in errors:
            console.print(f"  [red]• {err}[/red]")


@skill.command(name="install")
@click.argument("source")
@click.option(
    "--global",
    "is_global",
    is_flag=True,
    default=False,
    help="グローバルスキルとしてインストールする（デフォルト）",
)
@click.pass_context
def skill_install(ctx: click.Context, source: str, is_global: bool) -> None:
    """スキルをインストールする（Git URL またはローカルパス）."""
    from pathlib import Path

    from myagent.skills.installer import install_from_git, install_from_path

    app_config: AppConfig = ctx.obj["config"]

    if is_global or not app_config.skill.project_skills_dir:
        skills_dir = Path.home() / ".myagent" / "skills"
    else:
        skills_dir = Path(app_config.skill.project_skills_dir)

    src_path = Path(source)
    try:
        if src_path.exists():
            meta = install_from_path(src_path, skills_dir)
        else:
            meta = install_from_git(source, skills_dir)
        print_success(f"スキルをインストールしました: {meta.name} -> {meta.skill_dir}")
    except (ValueError, RuntimeError, OSError) as e:
        print_error(f"インストールに失敗しました: {e}")


@skill.command(name="uninstall")
@click.argument("skill_name")
@click.option(
    "--global",
    "is_global",
    is_flag=True,
    default=False,
    help="グローバルスキルをアンインストールする",
)
@click.pass_context
def skill_uninstall(ctx: click.Context, skill_name: str, is_global: bool) -> None:
    """インストール済みスキルを削除する."""
    from pathlib import Path

    from myagent.skills.installer import uninstall

    app_config: AppConfig = ctx.obj["config"]

    # スキルがどこにあるかを確認
    manager = _build_skill_manager(app_config)
    manager.load_all()
    meta = manager.get_metadata(skill_name)

    if meta is None:
        print_error(f"スキルが見つかりません: {skill_name}")
        return

    if is_global:
        skills_dir = Path.home() / ".myagent" / "skills"
    else:
        skills_dir = meta.skill_dir.parent

    success = uninstall(skill_name, skills_dir)
    if success:
        print_success(f"スキルを削除しました: {skill_name}")
    else:
        print_error(f"スキルの削除に失敗しました: {skill_name}")


# ---------------------------------------------------------------------------
# command コマンドグループ
# ---------------------------------------------------------------------------


@cli.group()
@click.pass_context
def command(ctx: click.Context) -> None:
    """カスタムコマンド管理コマンド."""
    ctx.ensure_object(dict)


@command.command(name="list")
@click.pass_context
def command_list(ctx: click.Context) -> None:
    """ロード済みカスタムコマンド一覧を表示する."""
    from rich.console import Console
    from rich.table import Table

    from myagent.commands.manager import build_command_manager

    app_config: AppConfig = ctx.obj["config"]
    manager = build_command_manager(
        project_commands_dir_str=app_config.command.project_commands_dir,
        global_commands_dir_str=app_config.command.global_commands_dir,
    )
    commands = manager.load_all()

    console = Console()
    if not commands:
        console.print("[yellow]利用可能なカスタムコマンドがありません[/yellow]")
        return

    table = Table(title="カスタムコマンド一覧")
    table.add_column("コマンド名", style="cyan")
    table.add_column("スコープ")
    table.add_column("引数")
    table.add_column("説明")

    for cmd in sorted(commands, key=lambda c: c.name):
        scope_str = (
            "[green]プロジェクト[/green]"
            if cmd.scope == "project"
            else "[blue]グローバル[/blue]"
        )
        args_str = ", ".join(
            f"{name}{'*' if arg.required else ''}"
            for name, arg in cmd.arguments.items()
        )
        desc = (
            cmd.description[:80] + "..."
            if len(cmd.description) > 80
            else cmd.description
        )
        table.add_row(f"/{cmd.name}", scope_str, args_str or "-", desc)

    console.print(table)
    console.print("\n[dim]* = 必須引数[/dim]")


@command.command(name="init")
@click.argument("command_name")
@click.option(
    "--global",
    "is_global",
    is_flag=True,
    default=False,
    help="グローバルコマンドとして作成する",
)
@click.pass_context
def command_init(ctx: click.Context, command_name: str, is_global: bool) -> None:
    """カスタムコマンド定義の雛形TOMLファイルを生成する."""
    from rich.console import Console

    from myagent.commands.loader import _NAME_PATTERN as _CMD_NAME_PATTERN

    console = Console()

    if not _CMD_NAME_PATTERN.match(command_name) or len(command_name) > 64:
        print_error(
            f"コマンド名が命名規則に違反しています: {command_name!r}\n"
            "小文字英数字とハイフンのみ使用可能です（先頭・末尾はハイフン不可）"
        )
        return

    app_config: AppConfig = ctx.obj["config"]

    if is_global:
        commands_dir = Path.home() / ".myagent" / "commands"
    else:
        commands_dir = Path(app_config.command.project_commands_dir)

    commands_dir.mkdir(parents=True, exist_ok=True)
    toml_path = commands_dir / f"{command_name}.toml"

    if toml_path.exists():
        print_error(f"コマンド定義ファイルが既に存在します: {toml_path}")
        return

    toml_path.write_text(
        f'''name = "{command_name}"
description = "このコマンドの説明を記述してください"
prompt = """
以下の手順で作業してください:

1. {{{{target}}}} を確認する
2. 必要な変更を実施する
3. 結果を報告する
"""

[arguments]
target = {{ description = "対象ファイルまたはディレクトリ", default = "." }}
''',
        encoding="utf-8",
    )

    print_success(f"コマンド定義を生成しました: {toml_path}")
    console.print(f"TOMLファイルを編集して内容を完成させてください: {toml_path}")


def _build_skill_manager(config: AppConfig) -> SkillManager:
    """設定から SkillManager を構築する."""
    from pathlib import Path

    from myagent.skills.manager import SkillManager

    proj_str = config.skill.project_skills_dir
    glob_str = config.skill.global_skills_dir
    project_dir = Path(proj_str) if proj_str else None
    global_dir = Path(glob_str) if glob_str else None
    return SkillManager(project_skills_dir=project_dir, global_skills_dir=global_dir)


# ---------------------------------------------------------------------------
# plugin コマンドグループ
# ---------------------------------------------------------------------------


@cli.group()
@click.pass_context
def plugin(ctx: click.Context) -> None:
    """プラグイン（Claude Code Plugins Standard 準拠）管理コマンド."""
    ctx.ensure_object(dict)


@plugin.command(name="list")
@click.pass_context
def plugin_list(ctx: click.Context) -> None:
    """インストール済みプラグイン一覧を表示する."""
    from rich.console import Console
    from rich.table import Table

    app_config: AppConfig = ctx.obj["config"]
    manager = _build_plugin_manager(app_config)
    plugins = manager.load_all()

    console = Console()
    if not plugins:
        console.print("[yellow]インストール済みのプラグインがありません[/yellow]")
        return

    table = Table(title="プラグイン一覧")
    table.add_column("名前", style="cyan")
    table.add_column("バージョン")
    table.add_column("状態")
    table.add_column("スキル", justify="right")
    table.add_column("説明")

    for meta in sorted(plugins, key=lambda m: m.name):
        status_str = "[green]有効[/green]" if meta.enabled else "[red]無効[/red]"
        description = meta.description or ""
        desc = description[:60] + "..." if len(description) > 60 else description
        table.add_row(
            meta.name,
            meta.version or "-",
            status_str,
            str(len(meta.skill_dirs)),
            desc,
        )

    console.print(table)


@plugin.command(name="install")
@click.argument("source")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"]),
    default="user",
    help="インストールスコープ（現在はuserのみ有効）",
)
@click.pass_context
def plugin_install(ctx: click.Context, source: str, scope: str) -> None:
    """プラグインをインストールする（Git URL またはローカルパス）."""
    from pathlib import Path

    from rich.console import Console

    from myagent.plugins.installer import install_from_git, install_from_path

    if scope != "user":
        Console().print(
            f"[yellow]--scope {scope} は現在未実装です。"
            "userスコープでインストールします。[/yellow]"
        )

    app_config: AppConfig = ctx.obj["config"]
    cache_dir = _get_plugin_cache_dir(app_config)

    src_path = Path(source)
    try:
        if src_path.exists():
            meta = install_from_path(src_path, cache_dir)
        else:
            meta = install_from_git(source, cache_dir)

        # 有効プラグインリストに追加
        if meta.name not in app_config.plugin.enabled_plugins:
            app_config.plugin.enabled_plugins.append(meta.name)
            save_config(app_config)

        print_success(
            f"プラグインをインストールしました: {meta.name} -> {meta.plugin_root}"
        )
        if meta.skill_dirs:
            print_success(f"  スキルディレクトリ: {len(meta.skill_dirs)} 個")
        if meta.mcp_config_file:
            print_success(f"  MCP設定: {meta.mcp_config_file}")
    except (ValueError, RuntimeError, OSError) as e:
        print_error(f"インストールに失敗しました: {e}")


@plugin.command(name="uninstall")
@click.argument("plugin_name")
@click.option(
    "--keep-data",
    is_flag=True,
    default=False,
    help="プラグインデータを保持する",
)
@click.pass_context
def plugin_uninstall(ctx: click.Context, plugin_name: str, keep_data: bool) -> None:
    """プラグインをアンインストールする."""
    from pathlib import Path

    from myagent.plugins.installer import uninstall

    app_config: AppConfig = ctx.obj["config"]
    cache_dir = _get_plugin_cache_dir(app_config)
    data_dir_str = app_config.plugin.data_dir
    data_dir = Path(data_dir_str) if data_dir_str else None

    try:
        success = uninstall(plugin_name, cache_dir, data_dir, keep_data=keep_data)
        if success:
            # 有効プラグインリストから削除
            if plugin_name in app_config.plugin.enabled_plugins:
                app_config.plugin.enabled_plugins.remove(plugin_name)
                save_config(app_config)
            print_success(f"プラグインを削除しました: {plugin_name}")
        else:
            print_error(f"プラグインが見つかりません: {plugin_name}")
    except OSError as e:
        print_error(f"アンインストールに失敗しました: {e}")


@plugin.command(name="update")
@click.argument("plugin_name")
@click.argument("url")
@click.pass_context
def plugin_update(ctx: click.Context, plugin_name: str, url: str) -> None:
    """プラグインを最新バージョンに更新する."""
    from myagent.plugins.installer import update_from_git

    app_config: AppConfig = ctx.obj["config"]
    cache_dir = _get_plugin_cache_dir(app_config)

    try:
        meta = update_from_git(plugin_name, url, cache_dir)
        ver = meta.version or "バージョン不明"
        print_success(f"プラグインを更新しました: {meta.name} ({ver})")
    except (ValueError, RuntimeError, OSError) as e:
        print_error(f"更新に失敗しました: {e}")


@plugin.command(name="enable")
@click.argument("plugin_name")
@click.pass_context
def plugin_enable(ctx: click.Context, plugin_name: str) -> None:
    """プラグインを有効化する."""
    app_config: AppConfig = ctx.obj["config"]
    manager = _build_plugin_manager(app_config)

    success = manager.enable(plugin_name)
    if success:
        if plugin_name not in app_config.plugin.enabled_plugins:
            app_config.plugin.enabled_plugins.append(plugin_name)
            save_config(app_config)
        print_success(f"プラグインを有効化しました: {plugin_name}")
    else:
        print_error(f"プラグインが見つかりません: {plugin_name}")


@plugin.command(name="disable")
@click.argument("plugin_name")
@click.pass_context
def plugin_disable(ctx: click.Context, plugin_name: str) -> None:
    """プラグインを無効化する."""
    app_config: AppConfig = ctx.obj["config"]
    manager = _build_plugin_manager(app_config)

    success = manager.disable(plugin_name)
    if success:
        if plugin_name in app_config.plugin.enabled_plugins:
            app_config.plugin.enabled_plugins.remove(plugin_name)
            save_config(app_config)
        print_success(f"プラグインを無効化しました: {plugin_name}")
    else:
        print_error(f"プラグインが見つかりません: {plugin_name}")


@plugin.command(name="validate")
@click.argument("path", required=False, default=".")
def plugin_validate(path: str) -> None:
    """プラグインのマニフェストとコンポーネント構造を検証する."""
    from pathlib import Path

    from rich.console import Console

    from myagent.plugins.loader import validate_plugin_dir

    console = Console()
    plugin_root = Path(path)

    errors = validate_plugin_dir(plugin_root)
    if not errors:
        print_success(f"バリデーション成功: {plugin_root}")
    else:
        console.print(f"[red]バリデーションエラー ({len(errors)} 件):[/red]")
        for err in errors:
            console.print(f"  [red]• {err}[/red]")


def _build_plugin_manager(config: AppConfig) -> PluginManager:
    """設定から PluginManager を構築する."""
    from myagent.plugins.manager import PluginManager

    cache_dir = _get_plugin_cache_dir(config)
    return PluginManager(plugin_cache_dir=cache_dir, enabled_plugins=config.plugin.enabled_plugins)


def _get_plugin_cache_dir(config: AppConfig) -> Path:
    """設定からプラグインキャッシュディレクトリを取得する."""
    cache_str = config.plugin.cache_dir
    if cache_str:
        return Path(cache_str)
    return Path.home() / ".myagent" / "plugins" / "cache"
