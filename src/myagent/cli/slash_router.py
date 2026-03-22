"""REPL内スラッシュコマンドルーター.

REPL対話ループ内で /plugin, /skill, /command, /config, /set-config, /mcp
等の管理コマンドをインプロセスで実行する。
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

if TYPE_CHECKING:
    from myagent.plugins.manager import PluginManager
    from myagent.skills.manager import SkillManager
from rich.table import Table

from myagent.cli.display import print_error, print_success, render_markdown
from myagent.infra.config import AppConfig, save_config

console = Console()

# ルーターが処理する組み込み管理コマンド名
_BUILTIN_COMMANDS: set[str] = {
    "plugin",
    "skill",
    "command",
    "config",
    "set-config",
    "mcp",
}

# コマンド名のエイリアス（ハイフンなし表記など）→正規名へのマッピング
_COMMAND_ALIASES: dict[str, str] = {
    "setconfig": "set-config",
}


def _parse_flags(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    """位置引数とフラグオプションを分離する.

    Args:
        tokens: 分割済みトークンリスト。

    Returns:
        (positional_args, flags) のタプル。
        flags は ``--key value`` 形式のみ対応する。
        ``--flag`` 単体はキーのみ(値は空文字)。
    """
    positional: list[str] = []
    flags: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            key = token.lstrip("-")
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                flags[key] = tokens[i + 1]
                i += 2
            else:
                flags[key] = ""
                i += 1
        else:
            positional.append(token)
            i += 1
    return positional, flags


class SlashCommandRouter:
    """REPL内スラッシュコマンドのルーター.

    ``try_handle`` にユーザー入力を渡すと、管理コマンドとして処理できた場合に
    ``True`` を返す。処理できなかった場合は ``False`` を返し、呼び出し元は
    カスタムコマンドやスキル解決に進む。
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def try_handle(self, user_input: str) -> bool:
        """スラッシュコマンドとして処理を試みる.

        Args:
            user_input: ユーザーの入力文字列（先頭 ``/`` 付き）。

        Returns:
            管理コマンドとして処理できた場合 True。
        """
        if not user_input.startswith("/") or user_input.startswith("//"):
            return False

        try:
            tokens = shlex.split(user_input[1:])
        except ValueError:
            tokens = user_input[1:].split()

        if not tokens:
            return False

        command_name = _COMMAND_ALIASES.get(tokens[0], tokens[0])
        if command_name not in _BUILTIN_COMMANDS:
            return False

        rest = tokens[1:]
        positional, flags = _parse_flags(rest)
        sub = positional[0] if positional else ""
        args = positional[1:]

        try:
            await self._dispatch(command_name, sub, args, flags)
        except Exception as exc:
            print_error(str(exc))
        return True

    def get_help_text(self) -> str:
        """管理コマンドのヘルプ Markdown テキストを返す."""
        return """## 管理コマンド

- `/plugin list|install|uninstall|enable|disable|validate` - プラグイン管理
- `/skill list|info|validate|install|uninstall` - スキル管理
- `/command list|init` - カスタムコマンド管理
- `/config` - 現在の設定を表示
- `/set-config (または /setconfig) --provider|--model|--fallback-provider|--fallback-model|--confirmation-level <value>` - 設定を変更
- `/mcp list|test` - MCPサーバー管理"""

    # ------------------------------------------------------------------
    # dispatcher
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        command: str,
        sub: str,
        args: list[str],
        flags: dict[str, str],
    ) -> None:
        handler_map: dict[str, Any] = {
            "plugin": self._handle_plugin,
            "skill": self._handle_skill,
            "command": self._handle_command,
            "config": self._handle_config,
            "set-config": self._handle_set_config,
            "mcp": self._handle_mcp,
        }
        handler = handler_map[command]
        await handler(sub, args, flags)

    # ------------------------------------------------------------------
    # /plugin
    # ------------------------------------------------------------------

    async def _handle_plugin(
        self, sub: str, args: list[str], flags: dict[str, str]
    ) -> None:
        valid_subs = {
            "list",
            "install",
            "uninstall",
            "enable",
            "disable",
            "validate",
        }
        if not sub or sub not in valid_subs:
            self._show_subcommand_help("plugin", valid_subs)
            return

        if sub == "list":
            self._plugin_list()
        elif sub == "install":
            if not args:
                print_error("使用方法: /plugin install <git-url-or-path>")
                return
            self._plugin_install(args[0])
        elif sub == "uninstall":
            if not args:
                print_error("使用方法: /plugin uninstall <name>")
                return
            self._plugin_uninstall(args[0])
        elif sub == "enable":
            if not args:
                print_error("使用方法: /plugin enable <name>")
                return
            self._plugin_enable(args[0])
        elif sub == "disable":
            if not args:
                print_error("使用方法: /plugin disable <name>")
                return
            self._plugin_disable(args[0])
        elif sub == "validate":
            path = args[0] if args else "."
            self._plugin_validate(path)

    def _plugin_list(self) -> None:
        manager = self._build_plugin_manager()
        plugins = manager.load_all()
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

    def _plugin_install(self, source: str) -> None:
        from myagent.plugins.installer import install_from_git, install_from_path

        cache_dir = self._get_plugin_cache_dir()
        src_path = Path(source)
        try:
            if src_path.exists():
                meta = install_from_path(src_path, cache_dir)
            else:
                meta = install_from_git(source, cache_dir)

            if meta.name not in self._config.plugin.enabled_plugins:
                self._config.plugin.enabled_plugins.append(meta.name)
                save_config(self._config)

            print_success(
                f"プラグインをインストールしました: {meta.name} -> {meta.plugin_root}"
            )
        except (ValueError, RuntimeError, OSError) as e:
            print_error(f"インストールに失敗しました: {e}")

    def _plugin_uninstall(self, name: str) -> None:
        from myagent.plugins.installer import uninstall

        cache_dir = self._get_plugin_cache_dir()
        data_dir_str = self._config.plugin.data_dir
        data_dir = Path(data_dir_str) if data_dir_str else None

        try:
            success = uninstall(name, cache_dir, data_dir, keep_data=False)
            if success:
                if name in self._config.plugin.enabled_plugins:
                    self._config.plugin.enabled_plugins.remove(name)
                    save_config(self._config)
                print_success(f"プラグインを削除しました: {name}")
            else:
                print_error(f"プラグインが見つかりません: {name}")
        except OSError as e:
            print_error(f"アンインストールに失敗しました: {e}")

    def _plugin_enable(self, name: str) -> None:
        manager = self._build_plugin_manager()
        success = manager.enable(name)
        if success:
            if name not in self._config.plugin.enabled_plugins:
                self._config.plugin.enabled_plugins.append(name)
                save_config(self._config)
            print_success(f"プラグインを有効化しました: {name}")
        else:
            print_error(f"プラグインが見つかりません: {name}")

    def _plugin_disable(self, name: str) -> None:
        manager = self._build_plugin_manager()
        success = manager.disable(name)
        if success:
            if name in self._config.plugin.enabled_plugins:
                self._config.plugin.enabled_plugins.remove(name)
                save_config(self._config)
            print_success(f"プラグインを無効化しました: {name}")
        else:
            print_error(f"プラグインが見つかりません: {name}")

    def _plugin_validate(self, path: str) -> None:
        from myagent.plugins.loader import validate_plugin_dir

        plugin_root = Path(path)
        errors = validate_plugin_dir(plugin_root)
        if not errors:
            print_success(f"バリデーション成功: {plugin_root}")
        else:
            console.print(f"[red]バリデーションエラー ({len(errors)} 件):[/red]")
            for err in errors:
                console.print(f"  [red]• {err}[/red]")

    # ------------------------------------------------------------------
    # /skill
    # ------------------------------------------------------------------

    async def _handle_skill(
        self, sub: str, args: list[str], flags: dict[str, str]
    ) -> None:
        valid_subs = {"list", "info", "validate", "install", "uninstall"}
        if not sub or sub not in valid_subs:
            self._show_subcommand_help("skill", valid_subs)
            return

        if sub == "list":
            self._skill_list()
        elif sub == "info":
            if not args:
                print_error("使用方法: /skill info <skill-name>")
                return
            self._skill_info(args[0])
        elif sub == "validate":
            if not args:
                print_error("使用方法: /skill validate <path>")
                return
            self._skill_validate(args[0])
        elif sub == "install":
            if not args:
                print_error("使用方法: /skill install <git-url-or-path>")
                return
            is_global = "global" in flags
            self._skill_install(args[0], is_global)
        elif sub == "uninstall":
            if not args:
                print_error("使用方法: /skill uninstall <skill-name>")
                return
            is_global = "global" in flags
            self._skill_uninstall(args[0], is_global)

    def _skill_list(self) -> None:
        manager = self._build_skill_manager()
        skills = manager.load_all()
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

    def _skill_info(self, skill_name: str) -> None:
        manager = self._build_skill_manager()
        manager.load_all()
        meta = manager.get_metadata(skill_name)
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

        files = [
            p.relative_to(meta.skill_dir)
            for p in meta.skill_dir.rglob("*")
            if p.is_file()
        ]
        if files:
            console.print("\nファイル構成:")
            for f in sorted(files):
                console.print(f"  {f}")

    def _skill_validate(self, path: str) -> None:
        from myagent.skills.loader import validate_skill_dir

        skill_dir = Path(path)
        errors = validate_skill_dir(skill_dir)
        if not errors:
            print_success(f"バリデーション成功: {skill_dir}")
        else:
            console.print(f"[red]バリデーションエラー ({len(errors)} 件):[/red]")
            for err in errors:
                console.print(f"  [red]• {err}[/red]")

    def _skill_install(self, source: str, is_global: bool) -> None:
        from myagent.skills.installer import install_from_git, install_from_path

        if is_global or not self._config.skill.project_skills_dir:
            skills_dir = Path.home() / ".myagent" / "skills"
        else:
            skills_dir = Path(self._config.skill.project_skills_dir)

        src_path = Path(source)
        try:
            if src_path.exists():
                meta = install_from_path(src_path, skills_dir)
            else:
                meta = install_from_git(source, skills_dir)
            print_success(
                f"スキルをインストールしました: {meta.name} -> {meta.skill_dir}"
            )
        except (ValueError, RuntimeError, OSError) as e:
            print_error(f"インストールに失敗しました: {e}")

    def _skill_uninstall(self, skill_name: str, is_global: bool) -> None:
        from myagent.skills.installer import uninstall

        manager = self._build_skill_manager()
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

    # ------------------------------------------------------------------
    # /command
    # ------------------------------------------------------------------

    async def _handle_command(
        self, sub: str, args: list[str], flags: dict[str, str]
    ) -> None:
        valid_subs = {"list", "init"}
        if not sub or sub not in valid_subs:
            self._show_subcommand_help("command", valid_subs)
            return

        if sub == "list":
            self._command_list()
        elif sub == "init":
            if not args:
                print_error("使用方法: /command init <name> [--global]")
                return
            is_global = "global" in flags
            self._command_init(args[0], is_global)

    def _command_list(self) -> None:
        from myagent.commands.manager import build_command_manager

        manager = build_command_manager(
            project_commands_dir_str=self._config.command.project_commands_dir,
            global_commands_dir_str=self._config.command.global_commands_dir,
        )
        commands = manager.load_all()
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

    def _command_init(self, command_name: str, is_global: bool) -> None:
        from myagent.commands.loader import _NAME_PATTERN as _CMD_NAME_PATTERN

        if not _CMD_NAME_PATTERN.match(command_name) or len(command_name) > 64:
            print_error(
                f"コマンド名が命名規則に違反しています: {command_name!r}\n"
                "小文字英数字とハイフンのみ使用可能です（先頭・末尾はハイフン不可）"
            )
            return

        if is_global:
            commands_dir = Path.home() / ".myagent" / "commands"
        else:
            commands_dir = Path(self._config.command.project_commands_dir)

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

    # ------------------------------------------------------------------
    # /config
    # ------------------------------------------------------------------

    async def _handle_config(
        self, sub: str, args: list[str], flags: dict[str, str]
    ) -> None:
        config = self._config
        wd = config.tool.working_directory or "(未設定)"

        config_text = f"""## 現在の設定

### 作業ディレクトリ
- {wd}

### LLM
- プロバイダ: {config.llm.provider}
- モデル: {config.llm.model}
- フォールバック: {config.llm.fallback_provider or "なし"} \
/ {config.llm.fallback_model or "なし"}
- 最大リトライ: {config.llm.max_retries}
- Temperature: {config.llm.temperature}

### ツール
- 確認レベル: {config.tool.confirmation_level}
- 最大出力行数: {config.tool.max_output_lines}

### エージェント
- 最大ループ回数: {config.agent.max_loops}

### APIキー
- OpenAI: {"設定済み" if config.openai_api_key else "未設定"}
- Google: {"設定済み" if config.google_api_key else "未設定"}
- Exa (Web検索): {"設定済み" if config.exa_api_key else "未設定"}
"""
        render_markdown(config_text)

    # ------------------------------------------------------------------
    # /set-config
    # ------------------------------------------------------------------

    async def _handle_set_config(
        self, sub: str, args: list[str], flags: dict[str, str]
    ) -> None:
        provider = flags.get("provider")
        model = flags.get("model")
        fallback_provider = flags.get("fallback-provider")
        fallback_model = flags.get("fallback-model")
        confirmation_level = flags.get("confirmation-level")

        if not any([provider, model, fallback_provider, fallback_model, confirmation_level]):
            print_error(
                "使用方法: /set-config [--provider <name>] [--model <name>] "
                "[--fallback-provider <name>] [--fallback-model <name>] "
                "[--confirmation-level <level>]"
            )
            return

        if provider:
            if provider not in ("openai", "gemini"):
                print_error(f"無効なプロバイダ: {provider}（openai または gemini）")
                return
            self._config.llm.provider = provider  # type: ignore[assignment]
        if model:
            self._config.llm.model = model
        if fallback_provider:
            if fallback_provider not in ("openai", "gemini"):
                print_error(
                    f"無効なフォールバックプロバイダ: {fallback_provider}（openai または gemini）"
                )
                return
            self._config.llm.fallback_provider = fallback_provider  # type: ignore[assignment]
        if fallback_model:
            self._config.llm.fallback_model = fallback_model
        if confirmation_level:
            if confirmation_level not in ("strict", "normal", "autonomous"):
                print_error(
                    f"無効な確認レベル: {confirmation_level}"
                    "（strict, normal, autonomous）"
                )
                return
            self._config.tool.confirmation_level = confirmation_level  # type: ignore[assignment]

        try:
            save_config(self._config)
            print_success("設定を保存しました")
        except Exception as e:
            print_error(f"設定保存エラー: {e}")

    # ------------------------------------------------------------------
    # /mcp
    # ------------------------------------------------------------------

    async def _handle_mcp(
        self, sub: str, args: list[str], flags: dict[str, str]
    ) -> None:
        valid_subs = {"list", "test"}
        if not sub or sub not in valid_subs:
            self._show_subcommand_help("mcp", valid_subs)
            return

        if sub == "list":
            await self._mcp_list()
        elif sub == "test":
            if not args:
                print_error("使用方法: /mcp test <server-name>")
                return
            await self._mcp_test(args[0])

    async def _mcp_list(self) -> None:
        from myagent.tools.mcp_tools import MCPManager
        from myagent.tools.registry import ToolRegistry

        manager = MCPManager(self._config.mcp)
        registry = ToolRegistry()
        await manager.connect_all(registry)
        statuses = manager.get_status()
        await manager.disconnect_all()

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

    async def _mcp_test(self, server_name: str) -> None:
        from myagent.tools.mcp_tools import MCPManager

        manager = MCPManager(self._config.mcp)
        result = await manager.test_server(server_name)
        if result.connected:
            console.print(
                f"[green]MCPサーバー '{server_name}' への接続に成功しました[/green]"
            )
            if result.tools:
                console.print(f"\n利用可能なツール ({len(result.tools)} 個):")
                for tool_name in result.tools:
                    console.print(f"  - {tool_name}")
            else:
                console.print("利用可能なツールがありません")
        else:
            console.print(
                f"[red]MCPサーバー '{server_name}' への接続に失敗しました[/red]"
            )
            if result.error:
                console.print(f"エラー: {result.error}")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _show_subcommand_help(self, command: str, valid_subs: set[str]) -> None:
        """有効なサブコマンド一覧を表示する."""
        subs = ", ".join(sorted(valid_subs))
        print_error(
            f"不明なサブコマンドです。"
            f"使用可能なサブコマンド: {subs}\n"
            f"使用方法: /{command} <サブコマンド>"
        )

    def _build_plugin_manager(self) -> PluginManager:
        from myagent.plugins.manager import PluginManager as _PluginManager

        cache_dir = self._get_plugin_cache_dir()
        return _PluginManager(
            plugin_cache_dir=cache_dir,
            enabled_plugins=self._config.plugin.enabled_plugins,
        )

    def _build_skill_manager(self) -> SkillManager:
        from myagent.plugins.manager import PluginManager as _PluginManager
        from myagent.skills.manager import SkillManager as _SkillManager

        proj_str = self._config.skill.project_skills_dir
        glob_str = self._config.skill.global_skills_dir
        project_dir = Path(proj_str) if proj_str else None
        global_dir = Path(glob_str) if glob_str else None

        plugin_manager = _PluginManager(
            enabled_plugins=self._config.plugin.enabled_plugins,
        )
        extra_dirs = plugin_manager.get_skill_dirs()

        return _SkillManager(
            project_skills_dir=project_dir,
            global_skills_dir=global_dir,
            extra_skill_dirs=extra_dirs if extra_dirs else None,
        )

    def _get_plugin_cache_dir(self) -> Path:
        cache_str = self._config.plugin.cache_dir
        if cache_str:
            return Path(cache_str)
        return Path.home() / ".myagent" / "plugins" / "cache"
