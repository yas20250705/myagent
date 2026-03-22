"""CLI アプリケーションのテスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myagent.infra.config import AppConfig


class TestCreate_runner:
    """_create_runner のテスト."""

    @pytest.mark.asyncio
    async def test_設定からAgentRunnerを構築できる(self) -> None:
        config = AppConfig()
        with patch("myagent.cli.app.LLMRouter") as mock_router_cls:
            mock_router = MagicMock()
            mock_model = MagicMock()
            mock_router.get_model_for_bind_tools.return_value = mock_model
            mock_router_cls.return_value = mock_router

            with patch("myagent.cli.app.AgentRunner") as mock_runner_cls:
                with patch("myagent.cli.app.MCPManager") as mock_mcp_cls:
                    mock_mcp = AsyncMock()
                    mock_mcp.connect_all = AsyncMock()
                    mock_mcp_cls.return_value = mock_mcp

                    from myagent.cli.app import _create_runner

                    await _create_runner(config)
                    mock_runner_cls.assert_called_once()


class TestRun_oneshot:
    """run_oneshot のテスト."""

    @pytest.mark.asyncio
    async def test_ワンショット実行が正常に完了する(self) -> None:
        from myagent.agent.events import AgentEvent

        config = AppConfig()

        async def mock_run_with_events(instruction: str):  # type: ignore[no-untyped-def]
            yield AgentEvent.agent_complete("完了")

        mock_runner = MagicMock()
        mock_runner.run_with_events = mock_run_with_events
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.disconnect_all = AsyncMock()

        with patch(
            "myagent.cli.app._create_runner",
            new_callable=AsyncMock,
            return_value=(mock_runner, mock_mcp_manager),
        ):
            with patch("myagent.cli.app.handle_event") as mock_handle:
                with patch("myagent.cli.app.console"):
                    from myagent.cli.app import run_oneshot

                    await run_oneshot(config, "テスト指示")
                    mock_handle.assert_called()

    @pytest.mark.asyncio
    async def test_エラー時にprint_errorが呼ばれる(self) -> None:
        config = AppConfig()

        async def failing_run_with_events(instruction: str):  # type: ignore[no-untyped-def]
            raise RuntimeError("実行エラー")
            yield  # generator化

        mock_runner = MagicMock()
        mock_runner.run_with_events = failing_run_with_events
        mock_mcp_manager = AsyncMock()
        mock_mcp_manager.disconnect_all = AsyncMock()

        with patch(
            "myagent.cli.app._create_runner",
            new_callable=AsyncMock,
            return_value=(mock_runner, mock_mcp_manager),
        ):
            with patch("myagent.cli.app.print_error") as mock_print_error:
                with patch("myagent.cli.app.console"):
                    from myagent.cli.app import run_oneshot

                    await run_oneshot(config, "エラーを起こして")
                    mock_print_error.assert_called_once()
