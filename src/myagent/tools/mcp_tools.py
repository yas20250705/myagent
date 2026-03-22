"""MCP（Model Context Protocol）クライアントとツールラッパー.

MCPサーバーへの接続管理、ツール検出、LangChain BaseToolラッパーを提供する。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import anyio
from langchain_core.tools import BaseTool
from mcp import ClientSession
from mcp import Tool as MCPTool
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from pydantic import ConfigDict, create_model
from pydantic import fields as pydantic_fields

from myagent.infra.config import MCPConfig, MCPServerConfig
from myagent.infra.errors import MCPConnectionError, MCPTimeoutError, MCPToolError
from myagent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

# JSON Schema の type → Python型 マッピング
_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _build_args_schema(
    tool_name: str, tool: MCPTool
) -> type[Any] | None:
    """MCPツールの inputSchema から Pydantic モデルを動的生成する.

    LLM に正確な入力スキーマを渡すために使用する。
    スキーマが存在しない場合は None を返す。
    """
    input_schema = tool.inputSchema
    if not input_schema or not isinstance(input_schema, dict):
        return None

    properties: dict[str, Any] = input_schema.get("properties", {})
    required_fields: list[str] = input_schema.get("required", [])

    if not properties:
        return None

    field_definitions: dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        json_type = field_schema.get("type", "string")
        python_type = _JSON_TYPE_MAP.get(json_type, str)
        field_desc = field_schema.get("description", "")
        is_required = field_name in required_fields
        if is_required:
            field_definitions[field_name] = (
                python_type,
                pydantic_fields.Field(description=field_desc),
            )
        else:
            field_definitions[field_name] = (
                python_type | None,
                pydantic_fields.Field(default=None, description=field_desc),
            )

    try:
        model_name = f"{tool_name}_schema"
        result: type[Any] = create_model(model_name, **field_definitions)
        return result
    except Exception:
        logger.debug("MCPツール '%s' の args_schema 生成に失敗しました", tool_name)
        return None
_MAX_RECONNECT_ATTEMPTS = 3


def _expand_env_vars(env: dict[str, str]) -> dict[str, str]:
    """環境変数 `${VAR}` を os.environ の値に展開する."""

    def replace(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), match.group(0))

    return {k: _ENV_VAR_PATTERN.sub(replace, v) for k, v in env.items()}


def _mask_env(env: dict[str, str]) -> dict[str, str]:
    """env の全値を `***` でマスクしたコピーを返す（ログ用）."""
    return {k: "***" for k in env}


@dataclass
class MCPServerStatus:
    """MCPサーバーの接続状態."""

    name: str
    connected: bool
    tool_count: int = 0
    error: str | None = None


@dataclass
class MCPTestResult:
    """MCPサーバー接続テスト結果."""

    server_name: str
    connected: bool
    tools: list[str] = field(default_factory=list)
    error: str | None = None


class MCPClient:
    """1つのMCPサーバーへの接続を管理するクライアント."""

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._session: ClientSession | None = None
        self._connected = False
        self._exit_stack: asyncio.Task[None] | None = None
        self._cm_stack: Any | None = None

    @property
    def connected(self) -> bool:
        """接続状態を返す."""
        return self._connected

    @property
    def config(self) -> MCPServerConfig:
        """サーバー設定を返す."""
        return self._config

    def _build_env(self) -> dict[str, str]:
        """環境変数を展開して返す."""
        expanded = _expand_env_vars(self._config.env)
        if expanded:
            logger.debug(
                "MCPサーバー '%s' の環境変数: %s",
                self._config.name,
                _mask_env(expanded),
            )
        return expanded

    @asynccontextmanager
    async def _stdio_transport(self) -> AsyncIterator[tuple[Any, Any]]:
        """stdioトランスポートのコンテキストマネージャ."""
        if not self._config.command:
            msg = (
                f"MCPサーバー '{self._config.name}': "
                "stdio トランスポートには command が必要です"
            )
            raise MCPConnectionError(msg, self._config.name)

        env = self._build_env()
        params = StdioServerParameters(
            command=self._config.command,
            args=self._config.args,
            env=env if env else None,
        )
        async with stdio_client(params) as (read, write):
            yield read, write

    @asynccontextmanager
    async def _http_transport(self) -> AsyncIterator[tuple[Any, Any]]:
        """Streamable HTTPトランスポートのコンテキストマネージャ."""
        if not self._config.url:
            msg = (
                f"MCPサーバー '{self._config.name}': "
                "http トランスポートには url が必要です"
            )
            raise MCPConnectionError(msg, self._config.name)

        async with streamable_http_client(self._config.url) as (read, write, _):
            yield read, write

    async def connect(self) -> None:
        """MCPサーバーに接続し、セッションを初期化する."""
        try:
            if self._config.transport == "stdio":
                ctx = self._stdio_transport()
            else:
                ctx = self._http_transport()

            read, write = await ctx.__aenter__()
            self._cm_stack = ctx
            try:
                self._session = ClientSession(read, write)
                await self._session.__aenter__()
                await self._session.initialize()
            except Exception:
                # セッション初期化失敗時にトランスポートをクリーンアップ
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    pass
                self._cm_stack = None
                self._session = None
                raise

            self._connected = True
            logger.info("MCPサーバー '%s' に接続しました", self._config.name)
        except MCPConnectionError:
            raise
        except Exception as e:
            msg = f"MCPサーバー '{self._config.name}' への接続に失敗しました: {e}"
            raise MCPConnectionError(msg, self._config.name, cause=e) from e

    async def disconnect(self) -> None:
        """MCPサーバーとの接続を切断する."""
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(
                    "MCPサーバー '%s' のセッション切断中にエラー: %s",
                    self._config.name, e,
                )
            self._session = None

        if self._cm_stack is not None:
            try:
                await self._cm_stack.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(
                    "MCPサーバー '%s' のトランスポート切断中にエラー: %s",
                    self._config.name, e,
                )
            self._cm_stack = None

        self._connected = False
        logger.info("MCPサーバー '%s' から切断しました", self._config.name)

    async def list_tools(self) -> list[MCPTool]:
        """サーバーからツール一覧を取得する."""
        if self._session is None:
            msg = f"MCPサーバー '{self._config.name}' は接続されていません"
            raise MCPConnectionError(msg, self._config.name)
        result = await self._session.list_tools()
        return list(result.tools)

    async def list_resources(self) -> list[Any]:
        """サーバーからリソース一覧を取得する."""
        if self._session is None:
            msg = f"MCPサーバー '{self._config.name}' は接続されていません"
            raise MCPConnectionError(msg, self._config.name)
        result = await self._session.list_resources()
        return list(result.resources)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """タイムアウト付きでツールを実行する."""
        if self._session is None:
            msg = f"MCPサーバー '{self._config.name}' は接続されていません"
            raise MCPConnectionError(msg, self._config.name)

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments),
                timeout=self._config.timeout,
            )
        except TimeoutError as e:
            msg = (
                f"MCPツール '{tool_name}' の実行が "
                f"{self._config.timeout}秒 でタイムアウトしました"
            )
            raise MCPTimeoutError(
                msg, self._config.name, tool_name, cause=e
            ) from e
        except MCPConnectionError:
            raise
        except Exception as e:
            msg = f"MCPツール '{tool_name}' の実行に失敗しました: {e}"
            raise MCPToolError(msg, self._config.name, tool_name, cause=e) from e

        # 結果をテキストに変換
        parts: list[str] = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            else:
                parts.append(str(content))
        return "\n".join(parts)

    async def reconnect(self) -> bool:
        """切断時に再接続を試みる（最大 _MAX_RECONNECT_ATTEMPTS 回）."""
        await self.disconnect()
        for attempt in range(1, _MAX_RECONNECT_ATTEMPTS + 1):
            try:
                logger.info(
                    "MCPサーバー '%s' への再接続を試みます (%d/%d)",
                    self._config.name,
                    attempt,
                    _MAX_RECONNECT_ATTEMPTS,
                )
                await self.connect()
                return True
            except MCPConnectionError:
                if attempt < _MAX_RECONNECT_ATTEMPTS:
                    await asyncio.sleep(1.0 * attempt)
        return False


class MCPToolWrapper(BaseTool):
    """MCPサーバーの1ツールをLangChain BaseToolとしてラップするクラス."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    mcp_client: MCPClient
    mcp_tool_name: str
    is_mcp_tool: bool = True

    def _run(self, *args: Any, **kwargs: Any) -> str:
        """同期的にMCPツールを実行する."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 既存のイベントループがある場合はスレッドで実行
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, self._arun(*args, **kwargs)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._arun(*args, **kwargs))
        except Exception as e:
            return f"エラー: {e}"

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """非同期でMCPツールを実行する."""
        # kwargsをそのままargumentsとして渡す
        arguments: dict[str, Any] = {}
        if args:
            arguments["input"] = args[0] if len(args) == 1 else list(args)
        arguments.update(kwargs)

        try:
            return await self.mcp_client.call_tool(self.mcp_tool_name, arguments)
        except MCPConnectionError as e:
            # 接続切断の場合は再接続を試みる
            logger.warning(
                "MCPサーバー '%s' との接続が切断されました。再接続を試みます: %s",
                self.mcp_client.config.name,
                e,
            )
            reconnected = await self.mcp_client.reconnect()
            if not reconnected:
                raise
            return await self.mcp_client.call_tool(self.mcp_tool_name, arguments)


class MCPManager:
    """複数のMCPサーバーへの接続を管理するマネージャ."""

    def __init__(self, config: MCPConfig) -> None:
        self._config = config
        self._clients: dict[str, MCPClient] = {}
        self._registered_tools: dict[str, list[str]] = {}  # server_name -> tool names

    async def connect_all(self, registry: ToolRegistry) -> None:
        """全サーバーに並列接続してToolRegistryにツールを登録する."""
        if not self._config.servers:
            return

        async def _connect_server(server_config: MCPServerConfig) -> None:
            client = MCPClient(server_config)
            try:
                await client.connect()
                self._clients[server_config.name] = client
                tools = await client.list_tools()
                registered: list[str] = []
                for tool in tools:
                    wrapper = self._create_wrapper(client, server_config.name, tool)
                    registry.register(wrapper)
                    registered.append(tool.name)
                self._registered_tools[server_config.name] = registered
                logger.info(
                    "MCPサーバー '%s': %d 個のツールを登録しました",
                    server_config.name,
                    len(registered),
                )
            except MCPConnectionError as e:
                logger.warning(
                    "MCPサーバー '%s' への接続に失敗しました。スキップします: %s",
                    server_config.name,
                    e,
                )
                self._clients[server_config.name] = client  # 状態追跡のために保持

        async with anyio.create_task_group() as tg:
            for server_config in self._config.servers:
                tg.start_soon(_connect_server, server_config)

    async def disconnect_all(self) -> None:
        """全サーバーを切断する."""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()
        self._registered_tools.clear()

    def get_status(self) -> list[MCPServerStatus]:
        """全サーバーの接続状態を返す."""
        statuses: list[MCPServerStatus] = []
        for server_config in self._config.servers:
            client = self._clients.get(server_config.name)
            if client is None:
                statuses.append(
                    MCPServerStatus(
                        name=server_config.name,
                        connected=False,
                        error="未接続",
                    )
                )
            else:
                tool_count = len(self._registered_tools.get(server_config.name, []))
                statuses.append(
                    MCPServerStatus(
                        name=server_config.name,
                        connected=client.connected,
                        tool_count=tool_count,
                        error=None if client.connected else "接続失敗",
                    )
                )
        return statuses

    async def test_server(self, server_name: str) -> MCPTestResult:
        """特定サーバーへの接続テストを実行する."""
        server_config = next(
            (s for s in self._config.servers if s.name == server_name), None
        )
        if server_config is None:
            return MCPTestResult(
                server_name=server_name,
                connected=False,
                error=f"サーバー '{server_name}' が設定に見つかりません",
            )

        client = MCPClient(server_config)
        try:
            await client.connect()
            tools = await client.list_tools()
            await client.disconnect()
            return MCPTestResult(
                server_name=server_name,
                connected=True,
                tools=[t.name for t in tools],
            )
        except MCPConnectionError as e:
            return MCPTestResult(
                server_name=server_name,
                connected=False,
                error=str(e),
            )

    @staticmethod
    def _create_wrapper(
        client: MCPClient, server_name: str, tool: MCPTool
    ) -> MCPToolWrapper:
        """MCPToolをMCPToolWrapperにラップする."""
        tool_name = f"mcp_{server_name}_{tool.name}"
        description = tool.description or f"MCPツール: {tool.name} ({server_name})"
        args_schema = _build_args_schema(tool_name, tool)
        return MCPToolWrapper(
            name=tool_name,
            description=description,
            mcp_client=client,
            mcp_tool_name=tool.name,
            args_schema=args_schema,
        )
