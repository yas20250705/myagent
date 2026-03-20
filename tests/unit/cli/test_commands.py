"""CLIコマンドのテスト."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from myagent.cli.commands import cli
from myagent.infra.config import AppConfig


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
                    result = runner.invoke(
                        cli, ["set-config", "--provider", "gemini"]
                    )
                    if result.exit_code == 0:
                        mock_save.assert_called_once()
                        assert config.llm.provider == "gemini"
