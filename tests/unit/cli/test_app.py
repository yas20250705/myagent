"""CLI アプリケーションのテスト."""

from __future__ import annotations

from pathlib import Path
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

    @pytest.mark.asyncio
    async def test_activate_skill_toolが登録される(self) -> None:
        """_create_runner でActivateSkillToolがregistryに登録されること."""
        from myagent.skills.skill_tool import ActivateSkillTool

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

                    # AgentRunnerに渡されたtoolsにActivateSkillToolが含まれること
                    call_kwargs = mock_runner_cls.call_args
                    tools = call_kwargs.kwargs.get("tools", [])
                    tool_names = [t.name for t in tools]
                    assert "activate_skill" in tool_names

    @pytest.mark.asyncio
    async def test_skills_contextがAgentRunnerに渡される(self) -> None:
        """_create_runner でskills_contextがAgentRunnerに渡されること."""
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

                    call_kwargs = mock_runner_cls.call_args
                    # skills_context キーワード引数が渡されること
                    assert "skills_context" in call_kwargs.kwargs


class TestResolveSkillInput:
    """_resolve_skill_input のテスト."""

    def test_スラッシュコマンドでスキルがアクティベートされる(
        self, tmp_path: Path
    ) -> None:
        from pathlib import Path

        from myagent.skills.manager import SkillManager
        from myagent.cli.app import _resolve_skill_input

        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: テスト\n---\n\nスキルボディ",
            encoding="utf-8",
        )
        manager = SkillManager(
            project_skills_dir=tmp_path / "skills",
            global_skills_dir=tmp_path / "no-global",
        )

        effective, name = _resolve_skill_input("/my-skill 指示テキスト", manager)

        assert name == "my-skill"
        assert "スキルボディ" in effective
        assert "指示テキスト" in effective

    def test_通常入力はキーワードマッチングしない(self, tmp_path: Path) -> None:
        """F21: 通常入力ではキーワードマッチングを行わない（LLMに委任）."""
        from myagent.skills.manager import SkillManager
        from myagent.cli.app import _resolve_skill_input

        skill_dir = tmp_path / "skills" / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: code-review\ndescription: コードレビューを実行\n---\nボディ",
            encoding="utf-8",
        )
        manager = SkillManager(
            project_skills_dir=tmp_path / "skills",
            global_skills_dir=tmp_path / "no-global",
        )

        # キーワードが含まれていても、自動マッチングはしない
        effective, name = _resolve_skill_input("コードレビューをお願いします", manager)

        assert name is None
        assert effective == "コードレビューをお願いします"


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
        mock_skill_manager = MagicMock()

        with patch(
            "myagent.cli.app._create_runner",
            new_callable=AsyncMock,
            return_value=(mock_runner, mock_mcp_manager, mock_skill_manager),
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
        mock_skill_manager = MagicMock()

        with patch(
            "myagent.cli.app._create_runner",
            new_callable=AsyncMock,
            return_value=(mock_runner, mock_mcp_manager, mock_skill_manager),
        ):
            with patch("myagent.cli.app.print_error") as mock_print_error:
                with patch("myagent.cli.app.console"):
                    from myagent.cli.app import run_oneshot

                    await run_oneshot(config, "エラーを起こして")
                    mock_print_error.assert_called_once()
