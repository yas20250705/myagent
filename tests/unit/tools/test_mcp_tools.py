"""MCPツールのテスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myagent.infra.config import MCPConfig, MCPServerConfig
from myagent.infra.errors import MCPConnectionError, MCPTimeoutError, MCPToolError
from myagent.tools.mcp_tools import (
    MCPClient,
    MCPManager,
    MCPToolWrapper,
    _expand_env_vars,
    _mask_env,
)
from myagent.tools.registry import ToolRegistry


class TestMCPServerConfigのバリデーション:
    """MCPServerConfig のバリデーションをテストする."""

    def test_stdioトランスポートの設定が作成できる(self) -> None:
        config = MCPServerConfig(
            name="github",
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
        )
        assert config.name == "github"
        assert config.transport == "stdio"
        assert config.command == "npx"
        assert config.args == ["-y", "@modelcontextprotocol/server-github"]

    def test_httpトランスポートの設定が作成できる(self) -> None:
        config = MCPServerConfig(
            name="remote",
            transport="http",
            url="http://localhost:8080/mcp",
        )
        assert config.transport == "http"
        assert config.url == "http://localhost:8080/mcp"

    def test_デフォルトtimeoutは30秒(self) -> None:
        config = MCPServerConfig(name="test", transport="stdio")
        assert config.timeout == 30

    def test_カスタムtimeoutを設定できる(self) -> None:
        config = MCPServerConfig(name="test", transport="stdio", timeout=60)
        assert config.timeout == 60

    def test_環境変数マップを設定できる(self) -> None:
        config = MCPServerConfig(
            name="test",
            transport="stdio",
            env={"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
        )
        assert config.env == {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}


class TestMCPConfig:
    """MCPConfig のテスト."""

    def test_デフォルトでserversは空リスト(self) -> None:
        config = MCPConfig()
        assert config.servers == []

    def test_複数のサーバーを設定できる(self) -> None:
        config = MCPConfig(
            servers=[
                MCPServerConfig(name="server1", transport="stdio", command="cmd1"),
                MCPServerConfig(name="server2", transport="http", url="http://x"),
            ]
        )
        assert len(config.servers) == 2
        assert config.servers[0].name == "server1"
        assert config.servers[1].name == "server2"


class Test環境変数展開:
    """環境変数展開のテスト."""

    def test_環境変数が展開される(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_TOKEN", "secret123")
        result = _expand_env_vars({"TOKEN": "${MY_TOKEN}"})
        assert result["TOKEN"] == "secret123"

    def test_未定義の環境変数はそのまま残る(self) -> None:
        result = _expand_env_vars({"TOKEN": "${UNDEFINED_VAR_XYZ}"})
        assert result["TOKEN"] == "${UNDEFINED_VAR_XYZ}"

    def test_環境変数なしはそのまま返る(self) -> None:
        result = _expand_env_vars({"KEY": "literal_value"})
        assert result["KEY"] == "literal_value"

    def test_envが空の場合は空を返す(self) -> None:
        result = _expand_env_vars({})
        assert result == {}


class Testマスク:
    """シークレットマスキングのテスト."""

    def test_全ての値がマスクされる(self) -> None:
        env = {"TOKEN": "secret", "KEY": "password"}
        masked = _mask_env(env)
        assert masked["TOKEN"] == "***"
        assert masked["KEY"] == "***"

    def test_キーはそのまま保持される(self) -> None:
        env = {"MY_TOKEN": "secret"}
        masked = _mask_env(env)
        assert "MY_TOKEN" in masked


class TestMCPClient:
    """MCPClient のテスト."""

    def _make_config(self) -> MCPServerConfig:
        return MCPServerConfig(
            name="test_server",
            transport="stdio",
            command="echo",
            timeout=5,
        )

    def test_初期状態では未接続(self) -> None:
        config = self._make_config()
        client = MCPClient(config)
        assert not client.connected

    def test_configプロパティが返る(self) -> None:
        config = self._make_config()
        client = MCPClient(config)
        assert client.config is config

    @pytest.mark.asyncio
    async def test_セッションなしでlist_toolsはエラー(self) -> None:
        config = self._make_config()
        client = MCPClient(config)
        with pytest.raises(MCPConnectionError):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_セッションなしでcall_toolはエラー(self) -> None:
        config = self._make_config()
        client = MCPClient(config)
        with pytest.raises(MCPConnectionError):
            await client.call_tool("some_tool", {})

    @pytest.mark.asyncio
    async def test_セッションなしでlist_resourcesはエラー(self) -> None:
        config = self._make_config()
        client = MCPClient(config)
        with pytest.raises(MCPConnectionError):
            await client.list_resources()

    @pytest.mark.asyncio
    async def test_stdioのcommandなしでconnectはエラー(self) -> None:
        config = MCPServerConfig(name="test", transport="stdio", command=None)
        client = MCPClient(config)
        with pytest.raises(MCPConnectionError):
            await client.connect()

    @pytest.mark.asyncio
    async def test_httpのurlなしでconnectはエラー(self) -> None:
        config = MCPServerConfig(name="test", transport="http", url=None)
        client = MCPClient(config)
        with pytest.raises(MCPConnectionError):
            await client.connect()

    @pytest.mark.asyncio
    async def test_call_toolのタイムアウトでMCPTimeoutErrorが発生する(self) -> None:
        config = self._make_config()
        client = MCPClient(config)

        # セッションをモック
        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = TimeoutError()
        client._session = mock_session
        client._connected = True

        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            with pytest.raises(MCPTimeoutError):
                await client.call_tool("some_tool", {})

    @pytest.mark.asyncio
    async def test_call_toolのツール実行エラーでMCPToolErrorが発生する(self) -> None:
        config = self._make_config()
        client = MCPClient(config)

        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = RuntimeError("tool failed")
        client._session = mock_session
        client._connected = True

        # wait_forが実際にcall_toolを呼び出すようにする
        async def fake_wait_for(coro: object, timeout: float) -> object:
            return await coro  # type: ignore[misc]

        with patch("asyncio.wait_for", side_effect=fake_wait_for):
            with pytest.raises(MCPToolError):
                await client.call_tool("some_tool", {})


class TestMCPToolWrapper:
    """MCPToolWrapper のテスト."""

    def _make_wrapper(self, mock_client: MCPClient) -> MCPToolWrapper:
        return MCPToolWrapper(
            name="mcp_test_my_tool",
            description="テスト用ツール",
            mcp_client=mock_client,
            mcp_tool_name="my_tool",
        )

    @pytest.mark.asyncio
    async def test_arunが正常に実行される(self) -> None:
        mock_client = MagicMock(spec=MCPClient)
        mock_client.call_tool = AsyncMock(return_value="ツール実行結果")
        mock_client.config = MCPServerConfig(name="test", transport="stdio")

        wrapper = self._make_wrapper(mock_client)
        result = await wrapper._arun(key="value")

        mock_client.call_tool.assert_called_once_with("my_tool", {"key": "value"})
        assert result == "ツール実行結果"

    @pytest.mark.asyncio
    async def test_接続切断時に再接続してリトライする(self) -> None:
        mock_client = MagicMock(spec=MCPClient)
        mock_client.config = MCPServerConfig(name="test", transport="stdio")
        # 1回目は切断エラー、再接続後は成功
        mock_client.call_tool = AsyncMock(
            side_effect=[
                MCPConnectionError("接続切断", "test"),
                "再接続後の結果",
            ]
        )
        mock_client.reconnect = AsyncMock(return_value=True)

        wrapper = self._make_wrapper(mock_client)
        result = await wrapper._arun()

        assert mock_client.reconnect.called
        assert result == "再接続後の結果"

    @pytest.mark.asyncio
    async def test_再接続失敗時はMCPConnectionErrorが発生する(self) -> None:
        mock_client = MagicMock(spec=MCPClient)
        mock_client.config = MCPServerConfig(name="test", transport="stdio")
        mock_client.call_tool = AsyncMock(
            side_effect=MCPConnectionError("接続切断", "test")
        )
        mock_client.reconnect = AsyncMock(return_value=False)

        wrapper = self._make_wrapper(mock_client)
        with pytest.raises(MCPConnectionError):
            await wrapper._arun()

    def test_is_mcp_toolフラグがTrueである(self) -> None:
        mock_client = MagicMock(spec=MCPClient)
        mock_client.config = MCPServerConfig(name="test", transport="stdio")
        wrapper = self._make_wrapper(mock_client)
        assert wrapper.is_mcp_tool is True


class TestMCPManager:
    """MCPManager のテスト."""

    def _make_mcp_tool(self, name: str, description: str = "desc") -> MagicMock:
        tool = MagicMock()
        tool.name = name
        tool.description = description
        return tool

    def test_初期状態でget_statusはサーバー設定数分のステータスを返す(self) -> None:
        config = MCPConfig(
            servers=[
                MCPServerConfig(name="server1", transport="stdio", command="cmd"),
                MCPServerConfig(name="server2", transport="stdio", command="cmd"),
            ]
        )
        manager = MCPManager(config)
        statuses = manager.get_status()
        assert len(statuses) == 2
        assert all(not s.connected for s in statuses)

    def test_サーバーなしのget_statusは空リストを返す(self) -> None:
        manager = MCPManager(MCPConfig())
        assert manager.get_status() == []

    @pytest.mark.asyncio
    async def test_connect_allで接続成功時にツールが登録される(self) -> None:
        server_config = MCPServerConfig(
            name="test_server", transport="stdio", command="cmd"
        )
        config = MCPConfig(servers=[server_config])
        manager = MCPManager(config)

        mock_tools = [
            self._make_mcp_tool("tool_a", "ツールA"),
            self._make_mcp_tool("tool_b", "ツールB"),
        ]

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.connected = True
        mock_client.config = server_config
        mock_client.list_tools = AsyncMock(return_value=mock_tools)

        registry = ToolRegistry()

        with patch(
            "myagent.tools.mcp_tools.MCPClient", return_value=mock_client
        ):
            await manager.connect_all(registry)

        # ToolRegistryにツールが登録されていることを確認
        registered = registry.list_tools()
        assert len(registered) == 2
        names = {t.name for t in registered}
        assert "mcp_test_server_tool_a" in names
        assert "mcp_test_server_tool_b" in names

    @pytest.mark.asyncio
    async def test_connect_allで接続失敗時はスキップする(self) -> None:
        server_config = MCPServerConfig(
            name="failing_server", transport="stdio", command="cmd"
        )
        config = MCPConfig(servers=[server_config])
        manager = MCPManager(config)

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.connected = False
        mock_client.config = server_config
        mock_client.connect = AsyncMock(
            side_effect=MCPConnectionError("接続失敗", "failing_server")
        )

        registry = ToolRegistry()

        with patch(
            "myagent.tools.mcp_tools.MCPClient", return_value=mock_client
        ):
            # エラーが発生してもグレースフルに処理される
            await manager.connect_all(registry)

        # ToolRegistryにツールが登録されていないことを確認
        assert len(registry.list_tools()) == 0

    @pytest.mark.asyncio
    async def test_disconnect_allで全サーバーが切断される(self) -> None:
        config = MCPConfig(
            servers=[
                MCPServerConfig(name="s1", transport="stdio", command="cmd"),
                MCPServerConfig(name="s2", transport="stdio", command="cmd"),
            ]
        )
        manager = MCPManager(config)

        mock_client1 = AsyncMock(spec=MCPClient)
        mock_client2 = AsyncMock(spec=MCPClient)
        manager._clients = {"s1": mock_client1, "s2": mock_client2}

        await manager.disconnect_all()

        mock_client1.disconnect.assert_called_once()
        mock_client2.disconnect.assert_called_once()
        assert len(manager._clients) == 0

    @pytest.mark.asyncio
    async def test_test_serverで接続成功時にMCPTestResultが返る(self) -> None:
        server_config = MCPServerConfig(
            name="test_server", transport="stdio", command="cmd"
        )
        config = MCPConfig(servers=[server_config])
        manager = MCPManager(config)

        mock_tools = [self._make_mcp_tool("tool_a")]
        mock_client = AsyncMock(spec=MCPClient)
        mock_client.list_tools = AsyncMock(return_value=mock_tools)

        with patch(
            "myagent.tools.mcp_tools.MCPClient", return_value=mock_client
        ):
            result = await manager.test_server("test_server")

        assert result.connected is True
        assert result.server_name == "test_server"
        assert "tool_a" in result.tools
        assert result.error is None

    @pytest.mark.asyncio
    async def test_test_serverで接続失敗時にエラーが返る(self) -> None:
        server_config = MCPServerConfig(
            name="test_server", transport="stdio", command="cmd"
        )
        config = MCPConfig(servers=[server_config])
        manager = MCPManager(config)

        mock_client = AsyncMock(spec=MCPClient)
        mock_client.connect = AsyncMock(
            side_effect=MCPConnectionError("接続失敗", "test_server")
        )

        with patch(
            "myagent.tools.mcp_tools.MCPClient", return_value=mock_client
        ):
            result = await manager.test_server("test_server")

        assert result.connected is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_test_serverで未設定のサーバー名はエラーを返す(self) -> None:
        manager = MCPManager(MCPConfig())
        result = await manager.test_server("nonexistent")
        assert result.connected is False
        assert result.error is not None
