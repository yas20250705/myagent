"""SlashCommandRouter のテスト."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myagent.cli.slash_router import SlashCommandRouter, _parse_flags
from myagent.infra.config import AppConfig

# ---------------------------------------------------------------------------
# _parse_flags のテスト
# ---------------------------------------------------------------------------


class TestParseFlags:
    """フラグパーサーのテスト."""

    def test_位置引数のみ(self) -> None:
        pos, flags = _parse_flags(["list"])
        assert pos == ["list"]
        assert flags == {}

    def test_フラグ引数のみ(self) -> None:
        pos, flags = _parse_flags(["--provider", "openai"])
        assert pos == []
        assert flags == {"provider": "openai"}

    def test_位置引数とフラグ混在(self) -> None:
        pos, flags = _parse_flags(["init", "my-cmd", "--global"])
        assert pos == ["init", "my-cmd"]
        assert flags == {"global": ""}

    def test_複数フラグ(self) -> None:
        pos, flags = _parse_flags(["--provider", "gemini", "--model", "gemini-pro"])
        assert pos == []
        assert flags == {"provider": "gemini", "model": "gemini-pro"}

    def test_空リスト(self) -> None:
        pos, flags = _parse_flags([])
        assert pos == []
        assert flags == {}


# ---------------------------------------------------------------------------
# SlashCommandRouter.try_handle のテスト
# ---------------------------------------------------------------------------


class TestSlashCommandRouterTryHandle:
    """try_handle の基本動作テスト."""

    @pytest.mark.asyncio
    async def test_スラッシュ以外の入力はFalseを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        result = await router.try_handle("hello world")
        assert result[0] is False

    @pytest.mark.asyncio
    async def test_ダブルスラッシュはFalseを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        result = await router.try_handle("//escaped")
        assert result[0] is False

    @pytest.mark.asyncio
    async def test_未知のコマンドはFalseを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        result = await router.try_handle("/unknown-command")
        assert result[0] is False

    @pytest.mark.asyncio
    async def test_pluginコマンドはTrueを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch.object(router, "_handle_plugin", new_callable=AsyncMock) as mock:
            result = await router.try_handle("/plugin list")
            assert result[0] is True
            mock.assert_called_once_with("list", [], {})

    @pytest.mark.asyncio
    async def test_configコマンドはTrueを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch.object(router, "_handle_config", new_callable=AsyncMock) as mock:
            result = await router.try_handle("/config")
            assert result[0] is True
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_configコマンドはTrueを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch.object(
            router, "_handle_set_config", new_callable=AsyncMock
        ) as mock:
            result = await router.try_handle("/set-config --provider openai")
            assert result[0] is True
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_mcpコマンドはTrueを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch.object(router, "_handle_mcp", new_callable=AsyncMock) as mock:
            result = await router.try_handle("/mcp list")
            assert result[0] is True
            mock.assert_called_once_with("list", [], {})

    @pytest.mark.asyncio
    async def test_skillコマンドはTrueを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch.object(router, "_handle_skill", new_callable=AsyncMock) as mock:
            result = await router.try_handle("/skill list")
            assert result[0] is True
            mock.assert_called_once_with("list", [], {})

    @pytest.mark.asyncio
    async def test_commandコマンドはTrueを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch.object(router, "_handle_command", new_callable=AsyncMock) as mock:
            result = await router.try_handle("/command list")
            assert result[0] is True
            mock.assert_called_once_with("list", [], {})

    @pytest.mark.asyncio
    async def test_ハンドラ例外時もTrueを返しエラー表示する(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch.object(
            router,
            "_handle_plugin",
            new_callable=AsyncMock,
            side_effect=RuntimeError("テストエラー"),
        ):
            with patch("myagent.cli.slash_router.print_error") as mock_err:
                result = await router.try_handle("/plugin list")
                assert result[0] is True
                mock_err.assert_called_once_with("テストエラー")

    @pytest.mark.asyncio
    async def test_不正なクォートでもパースできる(self) -> None:
        """shlex.split が失敗した場合のフォールバック."""
        router = SlashCommandRouter(AppConfig())
        with patch.object(router, "_handle_plugin", new_callable=AsyncMock) as mock:
            result = await router.try_handle('/plugin install "unclosed')
            assert result[0] is True
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_スラッシュのみの入力はFalseを返す(self) -> None:
        router = SlashCommandRouter(AppConfig())
        result = await router.try_handle("/")
        assert result[0] is False


# ---------------------------------------------------------------------------
# サブコマンドヘルプ
# ---------------------------------------------------------------------------


class TestSlashCommandRouterSubcommandHelp:
    """不明なサブコマンド時のヘルプ表示テスト."""

    @pytest.mark.asyncio
    async def test_不明なpluginサブコマンドでヘルプ表示(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            result = await router.try_handle("/plugin unknown-sub")
            assert result[0] is True
            mock_err.assert_called_once()
            msg = mock_err.call_args[0][0]
            assert "使用可能なサブコマンド" in msg

    @pytest.mark.asyncio
    async def test_サブコマンドなしでヘルプ表示(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            result = await router.try_handle("/skill")
            assert result[0] is True
            mock_err.assert_called_once()
            msg = mock_err.call_args[0][0]
            assert "使用可能なサブコマンド" in msg

    @pytest.mark.asyncio
    async def test_command不明サブコマンドでヘルプ表示(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/command bad")
            mock_err.assert_called_once()
            assert "使用可能なサブコマンド" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_mcp不明サブコマンドでヘルプ表示(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/mcp bad")
            mock_err.assert_called_once()
            assert "使用可能なサブコマンド" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# 引数不足のusage表示
# ---------------------------------------------------------------------------


class TestSlashCommandRouterUsage:
    """引数不足時のusage表示テスト."""

    @pytest.mark.asyncio
    async def test_plugin_install引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/plugin install")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_plugin_uninstall引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/plugin uninstall")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_plugin_enable引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/plugin enable")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_plugin_disable引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/plugin disable")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_skill_info引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/skill info")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_skill_validate引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/skill validate")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_skill_install引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/skill install")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_skill_uninstall引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/skill uninstall")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_mcp_test引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/mcp test")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_command_init引数不足(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/command init")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# /config 表示
# ---------------------------------------------------------------------------


class TestSlashCommandRouterConfig:
    """config コマンドの表示テスト."""

    @pytest.mark.asyncio
    async def test_config表示にプロバイダが含まれる(self) -> None:
        config = AppConfig()
        router = SlashCommandRouter(config)
        with patch("myagent.cli.slash_router.render_markdown") as mock_render:
            await router.try_handle("/config")
            mock_render.assert_called_once()
            text = mock_render.call_args[0][0]
            assert "openai" in text
            assert "作業ディレクトリ" in text

    @pytest.mark.asyncio
    async def test_config表示に作業ディレクトリ設定値が含まれる(self) -> None:
        config = AppConfig()
        config.tool.working_directory = "/tmp/test-project"
        router = SlashCommandRouter(config)
        with patch("myagent.cli.slash_router.render_markdown") as mock_render:
            await router.try_handle("/config")
            text = mock_render.call_args[0][0]
            assert "/tmp/test-project" in text

    @pytest.mark.asyncio
    async def test_config未設定時(self) -> None:
        config = AppConfig()
        config.tool.working_directory = ""
        router = SlashCommandRouter(config)
        with patch("myagent.cli.slash_router.render_markdown") as mock_render:
            await router.try_handle("/config")
            text = mock_render.call_args[0][0]
            assert "(未設定)" in text


# ---------------------------------------------------------------------------
# /set-config
# ---------------------------------------------------------------------------


class TestSlashCommandRouterSetConfig:
    """set-config コマンドのテスト."""

    @pytest.mark.asyncio
    async def test_set_config_provider変更(self) -> None:
        config = AppConfig()
        router = SlashCommandRouter(config)
        with patch("myagent.cli.slash_router.save_config") as mock_save:
            with patch("myagent.cli.slash_router.print_success"):
                await router.try_handle("/set-config --provider gemini")
                assert config.llm.provider == "gemini"
                mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_config_model変更(self) -> None:
        config = AppConfig()
        router = SlashCommandRouter(config)
        with patch("myagent.cli.slash_router.save_config"):
            with patch("myagent.cli.slash_router.print_success"):
                await router.try_handle("/set-config --model gpt-5")
                assert config.llm.model == "gpt-5"

    @pytest.mark.asyncio
    async def test_set_config_confirmation_level変更(self) -> None:
        config = AppConfig()
        router = SlashCommandRouter(config)
        with patch("myagent.cli.slash_router.save_config"):
            with patch("myagent.cli.slash_router.print_success"):
                await router.try_handle(
                    "/set-config --confirmation-level autonomous"
                )
                assert config.tool.confirmation_level == "autonomous"

    @pytest.mark.asyncio
    async def test_set_config引数なしでエラー表示(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/set-config")
            mock_err.assert_called_once()
            assert "使用方法" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_config無効プロバイダでエラー表示(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/set-config --provider invalid")
            mock_err.assert_called_once()
            assert "無効なプロバイダ" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_config無効確認レベルでエラー表示(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/set-config --confirmation-level invalid")
            mock_err.assert_called_once()
            assert "無効な確認レベル" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_config保存エラー時(self) -> None:
        config = AppConfig()
        router = SlashCommandRouter(config)
        with patch(
            "myagent.cli.slash_router.save_config",
            side_effect=OSError("書き込み失敗"),
        ):
            with patch("myagent.cli.slash_router.print_error") as mock_err:
                await router.try_handle("/set-config --model foo")
                mock_err.assert_called_once()
                assert "設定保存エラー" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# /plugin ハンドラ
# ---------------------------------------------------------------------------


class TestPluginHandlers:
    """/plugin サブコマンドのテスト."""

    @pytest.mark.asyncio
    async def test_plugin_list_プラグインなし(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = []
        with patch.object(router, "_build_plugin_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.console") as mock_console:
                await router.try_handle("/plugin list")
                mock_console.print.assert_called()
                call_text = str(mock_console.print.call_args_list[0])
                assert "プラグインがありません" in call_text

    @pytest.mark.asyncio
    async def test_plugin_list_プラグインあり(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_meta = MagicMock()
        mock_meta.name = "test-plugin"
        mock_meta.version = "1.0"
        mock_meta.enabled = True
        mock_meta.skill_dirs = []
        mock_meta.description = "テスト"
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = [mock_meta]
        with patch.object(router, "_build_plugin_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.console") as mock_console:
                await router.try_handle("/plugin list")
                mock_console.print.assert_called()

    @pytest.mark.asyncio
    async def test_plugin_enable(self) -> None:
        config = AppConfig()
        router = SlashCommandRouter(config)
        mock_manager = MagicMock()
        mock_manager.enable.return_value = True
        with patch.object(router, "_build_plugin_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.save_config"):
                with patch("myagent.cli.slash_router.print_success") as mock_ok:
                    await router.try_handle("/plugin enable my-plugin")
                    mock_ok.assert_called_once()
                    assert "my-plugin" in config.plugin.enabled_plugins

    @pytest.mark.asyncio
    async def test_plugin_enable_見つからない(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_manager = MagicMock()
        mock_manager.enable.return_value = False
        with patch.object(router, "_build_plugin_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.print_error") as mock_err:
                await router.try_handle("/plugin enable nonexistent")
                assert "見つかりません" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_plugin_disable(self) -> None:
        config = AppConfig()
        config.plugin.enabled_plugins = ["my-plugin"]
        router = SlashCommandRouter(config)
        mock_manager = MagicMock()
        mock_manager.disable.return_value = True
        with patch.object(router, "_build_plugin_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.save_config"):
                with patch("myagent.cli.slash_router.print_success"):
                    await router.try_handle("/plugin disable my-plugin")
                    assert "my-plugin" not in config.plugin.enabled_plugins

    @pytest.mark.asyncio
    async def test_plugin_validate_成功(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch(
            "myagent.plugins.loader.validate_plugin_dir", return_value=[]
        ):
            with patch("myagent.cli.slash_router.print_success") as mock_ok:
                await router.try_handle("/plugin validate .")
                mock_ok.assert_called_once()

    @pytest.mark.asyncio
    async def test_plugin_validate_エラーあり(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch(
            "myagent.plugins.loader.validate_plugin_dir",
            return_value=["missing manifest"],
        ):
            with patch("myagent.cli.slash_router.console") as mock_console:
                await router.try_handle("/plugin validate .")
                output = str(mock_console.print.call_args_list)
                assert "バリデーションエラー" in output

    @pytest.mark.asyncio
    async def test_plugin_validate_デフォルトパス(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch(
            "myagent.plugins.loader.validate_plugin_dir", return_value=[]
        ) as mock_validate:
            with patch("myagent.cli.slash_router.print_success"):
                await router.try_handle("/plugin validate")
                mock_validate.assert_called_once_with(Path("."))

    @pytest.mark.asyncio
    async def test_plugin_install_成功(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_meta = MagicMock()
        mock_meta.name = "new-plugin"
        mock_meta.plugin_root = "/path"
        with patch(
            "myagent.plugins.installer.install_from_git", return_value=mock_meta
        ):
            with patch("myagent.cli.slash_router.save_config"):
                with patch("myagent.cli.slash_router.print_success") as mock_ok:
                    await router.try_handle(
                        "/plugin install https://example.com/repo.git"
                    )
                    mock_ok.assert_called_once()

    @pytest.mark.asyncio
    async def test_plugin_install_失敗(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch(
            "myagent.plugins.installer.install_from_git",
            side_effect=RuntimeError("git clone failed"),
        ):
            with patch("myagent.cli.slash_router.print_error") as mock_err:
                await router.try_handle(
                    "/plugin install https://example.com/repo.git"
                )
                assert "インストールに失敗" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_plugin_uninstall_成功(self) -> None:
        config = AppConfig()
        config.plugin.enabled_plugins = ["old-plugin"]
        router = SlashCommandRouter(config)
        with patch(
            "myagent.plugins.installer.uninstall", return_value=True
        ):
            with patch("myagent.cli.slash_router.save_config"):
                with patch("myagent.cli.slash_router.print_success") as mock_ok:
                    await router.try_handle("/plugin uninstall old-plugin")
                    mock_ok.assert_called_once()
                    assert "old-plugin" not in config.plugin.enabled_plugins

    @pytest.mark.asyncio
    async def test_plugin_uninstall_見つからない(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch(
            "myagent.plugins.installer.uninstall", return_value=False
        ):
            with patch("myagent.cli.slash_router.print_error") as mock_err:
                await router.try_handle("/plugin uninstall nonexist")
                assert "見つかりません" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# /skill ハンドラ
# ---------------------------------------------------------------------------


class TestSkillHandlers:
    """/skill サブコマンドのテスト."""

    @pytest.mark.asyncio
    async def test_skill_list_スキルなし(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = []
        with patch.object(router, "_build_skill_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.console") as mock_console:
                await router.try_handle("/skill list")
                call_text = str(mock_console.print.call_args_list[0])
                assert "スキルがありません" in call_text

    @pytest.mark.asyncio
    async def test_skill_list_スキルあり(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_meta = MagicMock()
        mock_meta.name = "test-skill"
        mock_meta.scope = "project"
        mock_meta.description = "テストスキル"
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = [mock_meta]
        with patch.object(router, "_build_skill_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.console"):
                await router.try_handle("/skill list")

    @pytest.mark.asyncio
    async def test_skill_info_見つからない(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = []
        mock_manager.get_metadata.return_value = None
        with patch.object(router, "_build_skill_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.print_error") as mock_err:
                await router.try_handle("/skill info nonexist")
                assert "見つかりません" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_skill_info_成功(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_meta = MagicMock()
        mock_meta.name = "my-skill"
        mock_meta.scope = "global"
        mock_meta.description = "テスト"
        mock_meta.license = "MIT"
        mock_meta.compatibility = ""
        mock_meta.allowed_tools = []
        mock_meta.metadata = {}
        mock_skill_dir = MagicMock()
        mock_skill_dir.rglob.return_value = []
        mock_meta.skill_dir = mock_skill_dir
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = [mock_meta]
        mock_manager.get_metadata.return_value = mock_meta
        with patch.object(router, "_build_skill_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.console") as mock_console:
                await router.try_handle("/skill info my-skill")
                output = str(mock_console.print.call_args_list)
                assert "my-skill" in output

    @pytest.mark.asyncio
    async def test_skill_validate_成功(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch(
            "myagent.skills.loader.validate_skill_dir", return_value=[]
        ):
            with patch("myagent.cli.slash_router.print_success") as mock_ok:
                await router.try_handle("/skill validate /path/to/skill")
                mock_ok.assert_called_once()

    @pytest.mark.asyncio
    async def test_skill_install_成功(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_meta = MagicMock()
        mock_meta.name = "new-skill"
        mock_meta.skill_dir = Path("/tmp/skills/new-skill")
        with patch(
            "myagent.skills.installer.install_from_git", return_value=mock_meta
        ):
            with patch("myagent.cli.slash_router.print_success") as mock_ok:
                await router.try_handle(
                    "/skill install https://example.com/skill.git"
                )
                mock_ok.assert_called_once()

    @pytest.mark.asyncio
    async def test_skill_uninstall_成功(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_meta = MagicMock()
        mock_meta.name = "old-skill"
        mock_meta.skill_dir = Path("/tmp/skills/old-skill")
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = [mock_meta]
        mock_manager.get_metadata.return_value = mock_meta
        with patch.object(router, "_build_skill_manager", return_value=mock_manager):
            with patch(
                "myagent.skills.installer.uninstall", return_value=True
            ):
                with patch("myagent.cli.slash_router.print_success") as mock_ok:
                    await router.try_handle("/skill uninstall old-skill")
                    mock_ok.assert_called_once()

    @pytest.mark.asyncio
    async def test_skill_uninstall_見つからない(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = []
        mock_manager.get_metadata.return_value = None
        with patch.object(router, "_build_skill_manager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.print_error") as mock_err:
                await router.try_handle("/skill uninstall nonexist")
                assert "見つかりません" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# /command ハンドラ
# ---------------------------------------------------------------------------


class TestCommandHandlers:
    """/command サブコマンドのテスト."""

    @pytest.mark.asyncio
    async def test_command_list_コマンドなし(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = []
        with patch(
            "myagent.commands.manager.build_command_manager",
            return_value=mock_manager,
        ):
            with patch("myagent.cli.slash_router.console") as mock_console:
                await router.try_handle("/command list")
                call_text = str(mock_console.print.call_args_list[0])
                assert "コマンドがありません" in call_text

    @pytest.mark.asyncio
    async def test_command_list_コマンドあり(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_cmd = MagicMock()
        mock_cmd.name = "test-cmd"
        mock_cmd.scope = "project"
        mock_cmd.description = "テスト"
        mock_cmd.arguments = {}
        mock_manager = MagicMock()
        mock_manager.load_all.return_value = [mock_cmd]
        with patch(
            "myagent.commands.manager.build_command_manager",
            return_value=mock_manager,
        ):
            with patch("myagent.cli.slash_router.console"):
                await router.try_handle("/command list")

    @pytest.mark.asyncio
    async def test_command_init_無効な名前(self) -> None:
        router = SlashCommandRouter(AppConfig())
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/command init INVALID_NAME")
            mock_err.assert_called_once()
            assert "命名規則" in mock_err.call_args[0][0]

    @pytest.mark.asyncio
    async def test_command_init_成功(self, tmp_path: Path) -> None:
        config = AppConfig()
        config.command.project_commands_dir = str(tmp_path)
        router = SlashCommandRouter(config)
        with patch("myagent.cli.slash_router.print_success") as mock_ok:
            with patch("myagent.cli.slash_router.console"):
                await router.try_handle("/command init my-cmd")
                mock_ok.assert_called_once()
                assert (tmp_path / "my-cmd.toml").exists()

    @pytest.mark.asyncio
    async def test_command_init_既存ファイル(self, tmp_path: Path) -> None:
        config = AppConfig()
        config.command.project_commands_dir = str(tmp_path)
        (tmp_path / "my-cmd.toml").write_text("existing", encoding="utf-8")
        router = SlashCommandRouter(config)
        with patch("myagent.cli.slash_router.print_error") as mock_err:
            await router.try_handle("/command init my-cmd")
            assert "既に存在" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# /mcp ハンドラ
# ---------------------------------------------------------------------------


class TestMCPHandlers:
    """/mcp サブコマンドのテスト."""

    @pytest.mark.asyncio
    async def test_mcp_list_サーバーなし(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_manager = MagicMock()
        mock_manager.connect_all = AsyncMock()
        mock_manager.get_status.return_value = []
        mock_manager.disconnect_all = AsyncMock()
        with patch("myagent.tools.mcp_tools.MCPManager", return_value=mock_manager):
            with patch("myagent.tools.registry.ToolRegistry"):
                with patch("myagent.cli.slash_router.console") as mock_console:
                    await router.try_handle("/mcp list")
                    call_text = str(mock_console.print.call_args_list[0])
                    assert "MCPサーバーがありません" in call_text

    @pytest.mark.asyncio
    async def test_mcp_list_サーバーあり(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_status = MagicMock()
        mock_status.name = "test-server"
        mock_status.connected = True
        mock_status.tool_count = 3
        mock_status.error = None
        mock_manager = MagicMock()
        mock_manager.connect_all = AsyncMock()
        mock_manager.get_status.return_value = [mock_status]
        mock_manager.disconnect_all = AsyncMock()
        with patch("myagent.tools.mcp_tools.MCPManager", return_value=mock_manager):
            with patch("myagent.tools.registry.ToolRegistry"):
                with patch("myagent.cli.slash_router.console"):
                    await router.try_handle("/mcp list")

    @pytest.mark.asyncio
    async def test_mcp_test_成功(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_result = MagicMock()
        mock_result.connected = True
        mock_result.tools = ["tool1", "tool2"]
        mock_result.error = None
        mock_manager = AsyncMock()
        mock_manager.test_server = AsyncMock(return_value=mock_result)
        with patch("myagent.tools.mcp_tools.MCPManager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.console") as mock_console:
                await router.try_handle("/mcp test my-server")
                output = str(mock_console.print.call_args_list)
                assert "接続に成功" in output

    @pytest.mark.asyncio
    async def test_mcp_test_失敗(self) -> None:
        router = SlashCommandRouter(AppConfig())
        mock_result = MagicMock()
        mock_result.connected = False
        mock_result.tools = []
        mock_result.error = "Connection refused"
        mock_manager = AsyncMock()
        mock_manager.test_server = AsyncMock(return_value=mock_result)
        with patch("myagent.tools.mcp_tools.MCPManager", return_value=mock_manager):
            with patch("myagent.cli.slash_router.console") as mock_console:
                await router.try_handle("/mcp test fail-server")
                output = str(mock_console.print.call_args_list)
                assert "接続に失敗" in output


# ---------------------------------------------------------------------------
# get_help_text
# ---------------------------------------------------------------------------


class TestSlashCommandRouterGetHelpText:
    """get_help_text のテスト."""

    def test_ヘルプテキストに全コマンドが含まれる(self) -> None:
        router = SlashCommandRouter(AppConfig())
        text = router.get_help_text()
        assert "/plugin" in text
        assert "/skill" in text
        assert "/command" in text
        assert "/config" in text
        assert "/set-config" in text
        assert "/mcp" in text
