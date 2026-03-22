"""Plannerクラスのテスト."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from myagent.agent.planner import Planner
from myagent.agent.state import SubTask


class TestPlannerのplan:
    """Planner.plan のテスト."""

    @pytest.mark.asyncio
    async def test_LLMからSubTaskリストを生成できる(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {"tasks": ["ファイルを読む", "コードを修正する", "テストを実行する"]}
        )
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        planner = Planner(model=mock_model)
        tasks = await planner.plan("バグを修正してテストを通してください")

        assert len(tasks) == 3
        assert all(isinstance(t, SubTask) for t in tasks)
        assert tasks[0].description == "ファイルを読む"
        assert tasks[1].description == "コードを修正する"
        assert tasks[2].description == "テストを実行する"

    @pytest.mark.asyncio
    async def test_LLM失敗時にフォールバックで元の指示を単一タスクとして返す(
        self,
    ) -> None:
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=Exception("APIエラー"))

        planner = Planner(model=mock_model)
        instruction = "バグを修正してください"
        tasks = await planner.plan(instruction)

        assert len(tasks) == 1
        assert tasks[0].description == instruction

    @pytest.mark.asyncio
    async def test_JSONパース失敗時にフォールバックが動作する(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "これはJSONではない"
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        planner = Planner(model=mock_model)
        instruction = "コードを整理してください"
        tasks = await planner.plan(instruction)

        assert len(tasks) == 1
        assert tasks[0].description == instruction

    @pytest.mark.asyncio
    async def test_tasksキーが空の場合は空リストを返す(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({"tasks": []})
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        planner = Planner(model=mock_model)
        tasks = await planner.plan("何かしてください")

        assert tasks == []

    @pytest.mark.asyncio
    async def test_content_がリスト型の場合フォールバックする(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [{"type": "text", "text": "不正な形式"}]
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        planner = Planner(model=mock_model)
        instruction = "テストを実行してください"
        tasks = await planner.plan(instruction)

        # content がリストの場合は空文字になりJSONパース失敗→フォールバック
        assert len(tasks) == 1
        assert tasks[0].description == instruction


class TestPlannerのplan_with_dependencies:
    """Planner.plan_with_dependencies のテスト."""

    @pytest.mark.asyncio
    async def test_依存関係付きSubTaskリストを生成できる(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "tasks": [
                {
                    "id": "t1",
                    "description": "テストを実行",
                    "depends_on": [],
                    "target_files": ["tests/"],
                },
                {
                    "id": "t2",
                    "description": "バグを修正",
                    "depends_on": ["t1"],
                    "target_files": ["src/main.py"],
                },
            ]
        })
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        planner = Planner(model=mock_model)
        tasks = await planner.plan_with_dependencies("バグを修正して")

        assert len(tasks) == 2
        assert tasks[0].task_id == "t1"
        assert tasks[0].depends_on == []
        assert tasks[0].target_files == ["tests/"]
        assert tasks[1].task_id == "t2"
        assert tasks[1].depends_on == ["t1"]

    @pytest.mark.asyncio
    async def test_パース失敗時に逐次実行にフォールバック(self) -> None:
        mock_model = MagicMock()
        # 1回目（依存関係分析）は失敗、2回目（通常plan）は成功
        fail_response = MagicMock()
        fail_response.content = "invalid json"
        ok_response = MagicMock()
        ok_response.content = json.dumps({"tasks": ["タスクA", "タスクB"]})
        mock_model.ainvoke = AsyncMock(side_effect=[Exception("API失敗"), ok_response])

        planner = Planner(model=mock_model)
        tasks = await planner.plan_with_dependencies("何かして")

        assert len(tasks) == 2
        # フォールバック時は連鎖依存になる
        assert tasks[0].task_id == "t1"
        assert tasks[0].depends_on == []
        assert tasks[1].task_id == "t2"
        assert tasks[1].depends_on == ["t1"]

    @pytest.mark.asyncio
    async def test_空のtasksリスト時にフォールバック(self) -> None:
        mock_model = MagicMock()
        # 1回目: 空のtasks、2回目: 通常plan
        empty_response = MagicMock()
        empty_response.content = json.dumps({"tasks": []})
        ok_response = MagicMock()
        ok_response.content = json.dumps({"tasks": ["タスクA"]})
        mock_model.ainvoke = AsyncMock(
            side_effect=[empty_response, ok_response]
        )

        planner = Planner(model=mock_model)
        tasks = await planner.plan_with_dependencies("タスク")

        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"


class TestPlannerのreplan:
    """Planner.replan のテスト."""

    @pytest.mark.asyncio
    async def test_失敗タスクを考慮した再計画を生成する(self) -> None:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {"tasks": ["別の方法でファイルを読む", "エラーを修正する"]}
        )
        mock_model.ainvoke = AsyncMock(return_value=mock_response)

        planner = Planner(model=mock_model)
        failed_tasks = [
            SubTask(description="ファイルを読む", result="ファイルが見つかりません"),
        ]
        tasks = await planner.replan("バグを修正して", failed_tasks)

        assert len(tasks) == 2
        # LLMが呼ばれていることを確認
        assert mock_model.ainvoke.called
        # 呼び出し時のメッセージに失敗情報が含まれているか確認
        call_args = mock_model.ainvoke.call_args
        messages = call_args[0][0]
        human_content = messages[1].content
        assert "失敗しました" in human_content
        assert "ファイルを読む" in human_content
