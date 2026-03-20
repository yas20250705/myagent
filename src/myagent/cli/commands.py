"""CLIコマンド定義.

clickを使用したコマンドラインインターフェースを定義する。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from myagent.cli.display import print_error, print_success, render_markdown
from myagent.infra.config import AppConfig, load_config, save_config


@click.group(invoke_without_command=True)
@click.argument("instruction", required=False, default=None)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False),
    default=None,
    help="設定ファイルパス",
)
@click.pass_context
def cli(ctx: click.Context, instruction: str | None, config_path: str | None) -> None:
    """myagent - AI コーディングアシスタント CLI."""
    ctx.ensure_object(dict)

    path = Path(config_path) if config_path else None
    try:
        config = load_config(path)
    except Exception as e:
        print_error(f"設定読み込みエラー: {e}")
        ctx.exit(1)
        return

    ctx.obj["config"] = config

    if ctx.invoked_subcommand is not None:
        return

    if instruction:
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
- フォールバック: {app_config.llm.fallback_provider or 'なし'} \
/ {app_config.llm.fallback_model or 'なし'}
- 最大リトライ: {app_config.llm.max_retries}
- Temperature: {app_config.llm.temperature}

### ツール
- 確認レベル: {app_config.tool.confirmation_level}
- 最大出力行数: {app_config.tool.max_output_lines}

### エージェント
- 最大ループ回数: {app_config.agent.max_loops}

### APIキー
- OpenAI: {'設定済み' if app_config.openai_api_key else '未設定'}
- Google: {'設定済み' if app_config.google_api_key else '未設定'}
"""
    render_markdown(config_text)


@cli.command()
@click.option(
    "--provider",
    type=click.Choice(["openai", "gemini"]),
    help="LLMプロバイダ",
)
@click.option("--model", help="モデル名")
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
    confirmation_level: str | None,
) -> None:
    """設定を変更して保存する."""
    app_config: AppConfig = ctx.obj["config"]

    if provider:
        app_config.llm.provider = provider  # type: ignore[assignment]
    if model:
        app_config.llm.model = model
    if confirmation_level:
        app_config.tool.confirmation_level = confirmation_level  # type: ignore[assignment]

    try:
        save_config(app_config)
        print_success("設定を保存しました")
    except Exception as e:
        print_error(f"設定保存エラー: {e}")


def _run_oneshot(config: AppConfig, instruction: str) -> None:
    """ワンショット実行."""
    from myagent.cli.app import run_oneshot

    asyncio.run(run_oneshot(config, instruction))
