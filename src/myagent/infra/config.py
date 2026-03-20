"""設定管理モジュール.

config.toml の読み書きと環境変数からのAPIキー読み込みを提供する。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import tomli_w
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from myagent.infra.errors import ConfigError

ConfirmationLevel = Literal["strict", "normal", "autonomous"]

DEFAULT_CONFIG_DIR = Path.home() / ".myagent"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"


class LLMConfig(BaseModel):
    """LLMプロバイダ設定."""

    provider: Literal["openai", "gemini"] = "openai"
    model: str = "gpt-5-nano"
    fallback_provider: Literal["openai", "gemini"] | None = "gemini"
    fallback_model: str | None = "gemini-2.5-flash"
    max_retries: int = Field(default=3, ge=1, le=10)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class ToolConfig(BaseModel):
    """ツール設定."""

    confirmation_level: ConfirmationLevel = "normal"
    max_output_lines: int = Field(default=200, ge=1)


class AgentConfig(BaseModel):
    """エージェント設定."""

    max_loops: int = Field(default=20, ge=1, le=100)


class AppConfig(BaseModel):
    """アプリケーション全体の設定."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    tool: ToolConfig = Field(default_factory=ToolConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    openai_api_key: str = ""
    google_api_key: str = ""


def load_config(config_path: Path | None = None) -> AppConfig:
    """設定ファイルと環境変数から設定を読み込む.

    Args:
        config_path: 設定ファイルパス。Noneの場合はデフォルトパスを使用。

    Returns:
        読み込まれた AppConfig インスタンス。

    Raises:
        ConfigError: 設定ファイルの読み込みまたはパースに失敗した場合。
    """
    load_dotenv()

    path = config_path or DEFAULT_CONFIG_PATH
    data: dict[str, object] = {}

    if path.exists():
        try:
            import tomllib

            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            msg = f"設定ファイルの読み込みに失敗しました: {path}: {e}"
            raise ConfigError(msg) from e

    try:
        config = AppConfig.model_validate(data)
    except Exception as e:
        msg = f"設定値のバリデーションに失敗しました: {e}"
        raise ConfigError(msg) from e

    # 環境変数でAPIキーを上書き
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    google_key = os.environ.get("GOOGLE_API_KEY", "")
    if openai_key:
        config.openai_api_key = openai_key
    if google_key:
        config.google_api_key = google_key

    return config


def save_config(config: AppConfig, config_path: Path | None = None) -> None:
    """設定をファイルに保存する.

    APIキーは保存しない（環境変数で管理するため）。

    Args:
        config: 保存する設定。
        config_path: 保存先パス。Noneの場合はデフォルトパスを使用。

    Raises:
        ConfigError: 設定ファイルの書き込みに失敗した場合。
    """
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(exclude={"openai_api_key", "google_api_key"})

    try:
        with open(path, "wb") as f:
            tomli_w.dump(data, f)
    except Exception as e:
        msg = f"設定ファイルの書き込みに失敗しました: {path}: {e}"
        raise ConfigError(msg) from e
