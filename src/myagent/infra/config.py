"""設定管理モジュール.

config.toml の読み書きと環境変数からのAPIキー読み込みを提供する。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import tomli_w
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from myagent.infra.errors import ConfigError

ConfirmationLevel = Literal["strict", "normal", "autonomous"]
MCPTransport = Literal["stdio", "http"]

DEFAULT_CONFIG_DIR = Path.home() / ".myagent"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"


class WebSearchConfig(BaseModel):
    """Web検索ツール設定."""

    endpoint: str = "https://api.exa.ai/search"
    timeout: int = Field(default=25, ge=1, le=120)
    default_num_results: int = Field(default=5, ge=1, le=50)
    fallback_enabled: bool = True
    search_backends: list[str] = Field(default_factory=lambda: ["duckduckgo"])


class WebFetchConfig(BaseModel):
    """Webページ取得ツール設定."""

    timeout: int = Field(default=30, ge=1, le=120)
    max_size_bytes: int = Field(default=5 * 1024 * 1024, ge=1)


class MCPServerConfig(BaseModel):
    """MCPサーバー設定."""

    name: str
    transport: MCPTransport = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout: int = Field(default=30, ge=1, le=600)


class MCPConfig(BaseModel):
    """MCP設定."""

    servers: list[MCPServerConfig] = Field(default_factory=list)


class LLMConfig(BaseModel):
    """LLMプロバイダ設定."""

    provider: Literal["openai", "gemini"] = "openai"
    model: str = "gpt-5-nano"
    fallback_provider: Literal["openai", "gemini"] | None = "gemini"
    fallback_model: str | None = "gemini-3.1-flash-lite-preview"
    max_retries: int = Field(default=3, ge=1, le=10)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class ToolConfig(BaseModel):
    """ツール設定."""

    confirmation_level: ConfirmationLevel = "normal"
    max_output_lines: int = Field(default=200, ge=1)
    allowed_directories: list[str] = Field(default_factory=list)
    working_directory: str = ""


class AgentConfig(BaseModel):
    """エージェント設定."""

    max_loops: int = Field(default=20, ge=1, le=100)
    context_window_tokens: int = Field(default=128_000, ge=1_000)
    max_parallel_workers: int = Field(default=3, ge=1, le=10)
    max_parallel_tool_calls: int = Field(default=5, ge=1, le=20)
    max_recovery_attempts: int = Field(default=2, ge=0, le=10)


class SkillConfig(BaseModel):
    """スキル拡張設定."""

    project_skills_dir: str = ".myagent/skills"
    global_skills_dir: str = ""  # 空の場合は ~/.myagent/skills を使用


class PluginConfig(BaseModel):
    """プラグイン拡張設定."""

    cache_dir: str = ""  # 空の場合は ~/.myagent/plugins/cache を使用
    data_dir: str = ""  # 空の場合は ~/.myagent/plugins/data を使用
    enabled_plugins: list[str] = Field(default_factory=list)
    plugin_dirs: list[str] = Field(default_factory=list)  # 開発用追加ディレクトリ


class CommandConfig(BaseModel):
    """カスタムコマンド設定."""

    project_commands_dir: str = ".myagent/commands"
    global_commands_dir: str = ""  # 空の場合は ~/.myagent/commands を使用


class AppConfig(BaseModel):
    """アプリケーション全体の設定."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    tool: ToolConfig = Field(default_factory=ToolConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    skill: SkillConfig = Field(default_factory=SkillConfig)
    plugin: PluginConfig = Field(default_factory=PluginConfig)
    command: CommandConfig = Field(default_factory=CommandConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    web_fetch: WebFetchConfig = Field(default_factory=WebFetchConfig)
    openai_api_key: str = ""
    google_api_key: str = ""
    exa_api_key: str = ""
    langchain_api_key: str = ""
    langchain_project: str = "myagent"
    langchain_tracing: bool = False
    langchain_endpoint: str = ""


def merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """2つの設定辞書を再帰的にマージする.

    ネストされた dict は再帰マージ、リストや単純な値は override で上書きする。

    Args:
        base: ベース設定（グローバル設定など）。
        override: 上書き設定（プロジェクトローカル設定など）。

    Returns:
        マージ済みの設定辞書。
    """
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_toml(path: Path) -> dict[str, Any]:
    """TOMLファイルを読み込んで辞書として返す.

    Args:
        path: TOMLファイルパス。

    Returns:
        パースされた辞書。ファイルが存在しない場合は空辞書。

    Raises:
        ConfigError: ファイルの読み込みまたはパースに失敗した場合。
    """
    if not path.exists():
        return {}
    try:
        import tomllib

        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        msg = f"設定ファイルの読み込みに失敗しました: {path}: {e}"
        raise ConfigError(msg) from e


def load_config(
    config_path: Path | None = None,
    project_config_dir: Path | None = None,
) -> AppConfig:
    """設定ファイルと環境変数から設定を読み込む.

    Args:
        config_path: 設定ファイルパス。Noneの場合はデフォルトパスを使用。
            指定された場合はプロジェクト設定マージをスキップする。
        project_config_dir: プロジェクトディレクトリ。
            このディレクトリの ``.myagent/config.toml`` が存在すれば
            グローバル設定にマージされる（プロジェクト設定が優先）。

    Returns:
        読み込まれた AppConfig インスタンス。

    Raises:
        ConfigError: 設定ファイルの読み込みまたはパースに失敗した場合。
    """
    load_dotenv()
    load_dotenv(Path.home() / ".myagent" / ".env", override=False)

    if config_path is not None:
        # --config 明示指定: その設定ファイルのみ使用（マージなし）
        data = _load_toml(config_path)
    else:
        # グローバル設定を読み込み
        data = _load_toml(DEFAULT_CONFIG_PATH)

        # プロジェクトローカル設定をマージ
        if project_config_dir is not None:
            project_config_path = project_config_dir / ".myagent" / "config.toml"
            project_data = _load_toml(project_config_path)
            if project_data:
                data = merge_configs(data, project_data)

    try:
        config = AppConfig.model_validate(data)
    except Exception as e:
        msg = f"設定値のバリデーションに失敗しました: {e}"
        raise ConfigError(msg) from e

    # 環境変数でLLMモデル設定を上書き
    llm_provider = os.environ.get("MYAGENT_LLM_PROVIDER", "").strip()
    llm_model = os.environ.get("MYAGENT_LLM_MODEL", "").strip()
    llm_fallback_provider = os.environ.get("MYAGENT_LLM_FALLBACK_PROVIDER", "").strip()
    llm_fallback_model = os.environ.get("MYAGENT_LLM_FALLBACK_MODEL", "").strip()
    if llm_provider:
        config.llm.provider = llm_provider  # type: ignore[assignment]
    if llm_model:
        config.llm.model = llm_model
    if llm_fallback_provider:
        config.llm.fallback_provider = llm_fallback_provider  # type: ignore[assignment]
    if llm_fallback_model:
        config.llm.fallback_model = llm_fallback_model

    # 環境変数でAPIキーを上書き
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    exa_key = os.environ.get("EXA_API_KEY", "").strip()
    if openai_key:
        config.openai_api_key = openai_key
    if google_key:
        config.google_api_key = google_key
    if exa_key:
        config.exa_api_key = exa_key

    # LangSmith設定を環境変数から読み込み
    langchain_api_key = os.environ.get("LANGCHAIN_API_KEY", "").strip()
    langchain_project = os.environ.get("LANGCHAIN_PROJECT", "").strip()
    langchain_tracing = os.environ.get("LANGCHAIN_TRACING_V2", "").strip().lower()
    langchain_endpoint = os.environ.get("LANGCHAIN_ENDPOINT", "").strip()
    if langchain_api_key:
        config.langchain_api_key = langchain_api_key
    if langchain_project:
        config.langchain_project = langchain_project
    if langchain_tracing in ("true", "1"):
        config.langchain_tracing = True
        # LangChainが参照する環境変数を確実にセット
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = langchain_api_key
        if langchain_project:
            os.environ["LANGCHAIN_PROJECT"] = langchain_project
        if langchain_endpoint:
            os.environ["LANGCHAIN_ENDPOINT"] = langchain_endpoint
            config.langchain_endpoint = langchain_endpoint

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

    # TOMLはNullを表現できないため、None値を除外する
    # working_directory はセッション固有の状態のため保存しない
    data = config.model_dump(
        exclude={"openai_api_key", "google_api_key", "exa_api_key"}, exclude_none=True
    )
    data.get("tool", {}).pop("working_directory", None)

    try:
        with open(path, "wb") as f:
            tomli_w.dump(data, f)
    except Exception as e:
        msg = f"設定ファイルの書き込みに失敗しました: {path}: {e}"
        raise ConfigError(msg) from e
