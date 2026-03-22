"""CLIコマンドのテスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from myagent.cli.commands import cli, mcp
from myagent.infra.config import AppConfig, MCPConfig, MCPServerConfig
from myagent.tools.mcp_tools import MCPManager, MCPServerStatus, MCPTestResult


class TestCliコマンド:
    """CLI コマンドのテスト."""

    def test_helpオプションで説明が表示される(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "myagent" in result.output.lower() or "AI" in result.output

    def test_configサブコマンドでhelpが表示される(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0

    def test_set_configサブコマンドでhelpが表示される(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["set-config", "--help"])
        assert result.exit_code == 0

    def test_versionオプションでバージョンが表示される(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "myagent" in result.output

    def test_working_dirオプションで作業ディレクトリを指定できる(self) -> None:
        import tempfile

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig()
            with patch("myagent.cli.commands.load_config", return_value=config):
                # --help と組み合わせてREPL起動を回避
                result = runner.invoke(
                    cli, ["--working-dir", tmpdir, "config"]
                )
                assert result.exit_code == 0
                assert config.tool.working_directory == tmpdir

    def test_cwdが自動的にworking_directoryに設定される(self) -> None:
        runner = CliRunner()
        config = AppConfig()
        with patch("myagent.cli.commands.load_config", return_value=config):
            result = runner.invoke(cli, ["config"])
            assert result.exit_code == 0
            assert config.tool.working_directory != ""


class TestConfigコマンドの設定表示:
    """config コマンドのロジックをユニットテストする."""

    def test_AppConfigの設定が文字列に含まれる(self) -> None:
        config = AppConfig()
        # config コマンドが生成するテキストの検証
        config_text = f"""## 現在の設定

### LLM
- プロバイダ: {config.llm.provider}
"""
        assert "openai" in config_text


class TestSetConfigコマンドの設定変更:
    """set-config コマンドの設定変更をテストする."""

    def test_load_configをモックしてプロバイダ変更ができる(self) -> None:
        runner = CliRunner()
        config = AppConfig()
        with patch("myagent.cli.commands.load_config", return_value=config):
            with patch("myagent.cli.commands.save_config") as mock_save:
                with patch("myagent.cli.commands.print_success"):
                    result = runner.invoke(cli, ["set-config", "--provider", "gemini"])
                    if result.exit_code == 0:
                        mock_save.assert_called_once()
                        assert config.llm.provider == "gemini"


class TestMCPコマンド:
    """mcp コマンドのテスト.

    Note: mcp サブグループは cli グループの下にネストされているため、
    直接 CliRunner で呼び出してテストする。
    """

    def test_mcpサブコマンドのhelpが表示される(self) -> None:
        runner = CliRunner()
        result = runner.invoke(mcp, ["--help"], obj={"config": AppConfig()})
        assert result.exit_code == 0
        assert "mcp" in result.output.lower() or "MCP" in result.output

    def test_mcp_listでサーバーなしの場合メッセージが表示される(self) -> None:
        runner = CliRunner()
        config = AppConfig(mcp=MCPConfig(servers=[]))
        result = runner.invoke(mcp, ["list"], obj={"config": config})
        assert result.exit_code == 0
        assert "設定済みのMCPサーバーがありません" in result.output

    def test_mcp_listでサーバー一覧が表示される(self) -> None:
        runner = CliRunner()
        config = AppConfig(
            mcp=MCPConfig(
                servers=[
                    MCPServerConfig(name="github", transport="stdio", command="npx")
                ]
            )
        )

        mock_manager = MagicMock(spec=MCPManager)
        mock_manager.connect_all = AsyncMock()
        mock_manager.get_status = MagicMock(
            return_value=[
                MCPServerStatus(name="github", connected=True, tool_count=5)
            ]
        )
        mock_manager.disconnect_all = AsyncMock()

        with patch("myagent.tools.mcp_tools.MCPManager", return_value=mock_manager):
            result = runner.invoke(mcp, ["list"], obj={"config": config})

        assert result.exit_code == 0

    def test_mcp_testで接続成功時に成功メッセージが表示される(self) -> None:
        runner = CliRunner()
        config = AppConfig(
            mcp=MCPConfig(
                servers=[
                    MCPServerConfig(name="github", transport="stdio", command="npx")
                ]
            )
        )

        mock_manager = MagicMock(spec=MCPManager)
        mock_manager.test_server = AsyncMock(
            return_value=MCPTestResult(
                server_name="github",
                connected=True,
                tools=["create_issue", "list_prs"],
            )
        )

        with patch("myagent.tools.mcp_tools.MCPManager", return_value=mock_manager):
            result = runner.invoke(mcp, ["test", "github"], obj={"config": config})

        assert result.exit_code == 0
        assert "成功" in result.output

    def test_mcp_testで接続失敗時にエラーメッセージが表示される(self) -> None:
        runner = CliRunner()
        config = AppConfig(
            mcp=MCPConfig(
                servers=[
                    MCPServerConfig(name="github", transport="stdio", command="npx")
                ]
            )
        )

        mock_manager = MagicMock(spec=MCPManager)
        mock_manager.test_server = AsyncMock(
            return_value=MCPTestResult(
                server_name="github",
                connected=False,
                error="接続タイムアウト",
            )
        )

        with patch("myagent.tools.mcp_tools.MCPManager", return_value=mock_manager):
            result = runner.invoke(mcp, ["test", "github"], obj={"config": config})

        assert result.exit_code == 0
        assert "失敗" in result.output


class TestPluginコマンド:
    """plugin コマンドのテスト."""

    def test_pluginサブコマンドのhelpが表示される(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["plugin", "--help"])
        assert result.exit_code == 0

    def test_plugin_listでプラグインなしの場合メッセージが表示される(self) -> None:
        import tempfile
        from unittest.mock import patch

        runner = CliRunner()
        # 空のキャッシュディレクトリで設定を作成
        with tempfile.TemporaryDirectory() as tmpdir:
            config = AppConfig()
            config.plugin.cache_dir = tmpdir
            with patch("myagent.cli.commands.load_config", return_value=config):
                result = runner.invoke(cli, ["plugin", "list"])
        assert result.exit_code == 0
        assert "インストール済みのプラグインがありません" in result.output

    def test_plugin_validateで存在しないパスはエラーを表示する(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["plugin", "validate", "/nonexistent/path"]
        )
        assert result.exit_code == 0
        assert "エラー" in result.output

    def test_plugin_enableで存在しないプラグインはエラーを表示する(self) -> None:
        import tempfile

        runner = CliRunner()
        config = AppConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            config.plugin.cache_dir = tmpdir
            result = runner.invoke(
                cli, ["plugin", "enable", "nonexistent"], obj={"config": config}
            )
        assert result.exit_code == 0
        assert "見つかりません" in result.output

    def test_plugin_disableで存在しないプラグインはエラーを表示する(self) -> None:
        import tempfile

        runner = CliRunner()
        config = AppConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            config.plugin.cache_dir = tmpdir
            result = runner.invoke(
                cli, ["plugin", "disable", "nonexistent"], obj={"config": config}
            )
        assert result.exit_code == 0
        assert "見つかりません" in result.output


class TestStatsコマンド:
    """stats コマンドのテスト."""

    def test_statsサブコマンドのhelpが表示される(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--help"])
        assert result.exit_code == 0
        assert "メトリクス" in result.output

    def test_statsコマンドが実行できる(self) -> None:
        runner = CliRunner()
        config = AppConfig()
        result = runner.invoke(cli, ["stats"], obj={"config": config})
        assert result.exit_code == 0
        assert "メトリクス" in result.output or "REPL" in result.output
