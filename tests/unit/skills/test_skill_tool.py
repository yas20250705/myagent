"""ActivateSkillTool のユニットテスト."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from myagent.skills.skill_tool import ActivateSkillTool


def _make_skill_manager(tmp_path: Path, skills: dict[str, str]) -> MagicMock:
    """テスト用 SkillManager モックを作成する."""
    from myagent.skills.models import Skill, SkillMetadata

    def _activate(name: str):  # type: ignore[no-untyped-def]
        if name not in skills:
            return None
        meta = SkillMetadata(
            name=name,
            description=f"{name}の説明",
            skill_dir=tmp_path / name,
            scope="global",
        )
        return Skill(meta=meta, body=skills[name])

    def _get_all_metadata():  # type: ignore[no-untyped-def]
        result = []
        for name in skills:
            meta = SkillMetadata(
                name=name,
                description=f"{name}の説明",
                skill_dir=tmp_path / name,
                scope="global",
            )
            result.append(meta)
        return result

    mock = MagicMock()
    mock.activate.side_effect = _activate
    mock.get_all_metadata.side_effect = _get_all_metadata
    return mock


class TestActivateSkillTool:
    """ActivateSkillTool のテスト."""

    def test_activate_existing_skill(self, tmp_path: Path) -> None:
        """存在するスキルをアクティベートできること."""
        skill_manager = _make_skill_manager(
            tmp_path, {"my-skill": "# スキルボディ\n\n詳細な指示"}
        )
        tool = ActivateSkillTool(skill_manager=skill_manager)

        result = tool._run("my-skill")

        assert "my-skill" in result
        assert "スキルボディ" in result

    def test_activate_nonexistent_skill_returns_error(self, tmp_path: Path) -> None:
        """存在しないスキルをアクティベートするとエラーメッセージを返すこと."""
        skill_manager = _make_skill_manager(
            tmp_path, {"existing-skill": "ボディ"}
        )
        tool = ActivateSkillTool(skill_manager=skill_manager)

        result = tool._run("not-exist")

        assert "not-exist" in result
        assert "見つかりません" in result

    def test_error_message_includes_available_skills(self, tmp_path: Path) -> None:
        """エラーメッセージに利用可能なスキルリストが含まれること."""
        skill_manager = _make_skill_manager(
            tmp_path,
            {
                "skill-a": "ボディA",
                "skill-b": "ボディB",
            },
        )
        tool = ActivateSkillTool(skill_manager=skill_manager)

        result = tool._run("unknown")

        assert "skill-a" in result or "skill-b" in result

    @pytest.mark.asyncio
    async def test_arun_delegates_to_run(self, tmp_path: Path) -> None:
        """非同期版が同期版と同じ結果を返すこと."""
        skill_manager = _make_skill_manager(
            tmp_path, {"my-skill": "# ボディ"}
        )
        tool = ActivateSkillTool(skill_manager=skill_manager)

        sync_result = tool._run("my-skill")
        async_result = await tool._arun("my-skill")

        assert sync_result == async_result

    def test_requires_skill_manager(self) -> None:
        """skill_manager なしの初期化は失敗すること."""
        with pytest.raises((ValueError, Exception)):
            ActivateSkillTool(skill_manager=None)

    def test_tool_name_is_activate_skill(self, tmp_path: Path) -> None:
        """ツール名が 'activate_skill' であること."""
        skill_manager = _make_skill_manager(tmp_path, {})
        tool = ActivateSkillTool(skill_manager=skill_manager)

        assert tool.name == "activate_skill"

    def test_description_mentions_skill_activation(self, tmp_path: Path) -> None:
        """description にスキルアクティベーションの説明が含まれること."""
        skill_manager = _make_skill_manager(tmp_path, {})
        tool = ActivateSkillTool(skill_manager=skill_manager)

        assert "スキル" in tool.description
