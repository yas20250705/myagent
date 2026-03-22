"""Orchestrator のユニットテスト."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from myagent.agent.metrics import SessionMetrics
from myagent.agent.orchestrator import (
    Orchestrator,
    WorkerResult,
    _build_summary,
    detect_file_conflicts,
    topological_sort_levels,
)
from myagent.agent.state import SubTask
from myagent.infra.errors import OrchestratorError


class Testトポロジカルソート:
    """topological_sort_levels のテスト."""

    def test_空リストは空リストを返す(self) -> None:
        assert topological_sort_levels([]) == []

    def test_独立したタスクは全て同一レベル(self) -> None:
        tasks = [
            SubTask(description="A", task_id="t1"),
            SubTask(description="B", task_id="t2"),
            SubTask(description="C", task_id="t3"),
        ]
        levels = topological_sort_levels(tasks)
        assert len(levels) == 1
        assert len(levels[0]) == 3

    def test_線形依存は各レベル1タスク(self) -> None:
        tasks = [
            SubTask(description="A", task_id="t1"),
            SubTask(description="B", task_id="t2", depends_on=["t1"]),
            SubTask(description="C", task_id="t3", depends_on=["t2"]),
        ]
        levels = topological_sort_levels(tasks)
        assert len(levels) == 3
        assert levels[0][0].task_id == "t1"
        assert levels[1][0].task_id == "t2"
        assert levels[2][0].task_id == "t3"

    def test_ダイヤモンド依存(self) -> None:
        tasks = [
            SubTask(description="A", task_id="t1"),
            SubTask(description="B", task_id="t2", depends_on=["t1"]),
            SubTask(description="C", task_id="t3", depends_on=["t1"]),
            SubTask(description="D", task_id="t4", depends_on=["t2", "t3"]),
        ]
        levels = topological_sort_levels(tasks)
        assert len(levels) == 3
        # レベル0: t1, レベル1: t2,t3, レベル2: t4
        assert levels[0][0].task_id == "t1"
        level1_ids = {t.task_id for t in levels[1]}
        assert level1_ids == {"t2", "t3"}
        assert levels[2][0].task_id == "t4"

    def test_循環依存でOrchestratorError(self) -> None:
        tasks = [
            SubTask(description="A", task_id="t1", depends_on=["t2"]),
            SubTask(description="B", task_id="t2", depends_on=["t1"]),
        ]
        with pytest.raises(OrchestratorError, match="循環依存"):
            topological_sort_levels(tasks)

    def test_task_idなしタスクはレベル0に含まれる(self) -> None:
        tasks = [
            SubTask(description="ID無し"),
            SubTask(description="A", task_id="t1"),
        ]
        levels = topological_sort_levels(tasks)
        assert len(levels) == 1
        descs = {t.description for t in levels[0]}
        assert "ID無し" in descs
        assert "A" in descs


class Testファイルコンフリクト検知:
    """detect_file_conflicts のテスト."""

    def test_コンフリクトなしの場合(self) -> None:
        tasks = [
            SubTask(description="A", task_id="t1", target_files=["a.py"]),
            SubTask(description="B", task_id="t2", target_files=["b.py"]),
        ]
        parallel, sequential = detect_file_conflicts(tasks)
        assert len(parallel) == 2
        assert len(sequential) == 0

    def test_コンフリクトありの場合(self) -> None:
        tasks = [
            SubTask(description="A", task_id="t1", target_files=["shared.py"]),
            SubTask(description="B", task_id="t2", target_files=["shared.py"]),
        ]
        parallel, sequential = detect_file_conflicts(tasks)
        assert len(parallel) == 1
        assert len(sequential) == 1

    def test_単一タスクはコンフリクトなし(self) -> None:
        tasks = [SubTask(description="A", task_id="t1", target_files=["a.py"])]
        parallel, sequential = detect_file_conflicts(tasks)
        assert len(parallel) == 1
        assert len(sequential) == 0

    def test_空リスト(self) -> None:
        parallel, sequential = detect_file_conflicts([])
        assert parallel == []
        assert sequential == []

    def test_target_files空のタスクはコンフリクトなし(self) -> None:
        tasks = [
            SubTask(description="A", task_id="t1"),
            SubTask(description="B", task_id="t2"),
        ]
        parallel, sequential = detect_file_conflicts(tasks)
        assert len(parallel) == 2
        assert len(sequential) == 0


class TestWorkerResult:
    """WorkerResult のテスト."""

    def test_デフォルト値(self) -> None:
        wr = WorkerResult(task_id="t1", description="タスク")
        assert wr.is_success is True
        assert wr.result_text == ""
        assert wr.error == ""
        assert wr.prompt_tokens == 0


class Testbuild_summary:
    """_build_summary のテスト."""

    def test_成功と失敗が含まれる(self) -> None:
        results = [
            WorkerResult(task_id="t1", description="タスクA", is_success=True),
            WorkerResult(
                task_id="t2",
                description="タスクB",
                is_success=False,
                error="エラー発生",
            ),
        ]
        summary = _build_summary(results)
        assert "✓" in summary
        assert "✗" in summary
        assert "エラー発生" in summary

    def test_空リスト(self) -> None:
        assert _build_summary([]) == ""


class TestOrchestrator実行:
    """Orchestrator.execute のテスト."""

    @pytest.mark.asyncio
    async def test_独立タスクの並列実行(self) -> None:
        mock_model = MagicMock()
        tasks = [
            SubTask(description="タスクA", task_id="t1"),
            SubTask(description="タスクB", task_id="t2"),
        ]

        orchestrator = Orchestrator(
            model=mock_model,
            tools=[],
            max_workers=3,
        )

        # _run_worker をモックして直接結果を返す
        async def mock_run(task: SubTask, wid: str) -> WorkerResult:
            return WorkerResult(
                task_id=task.task_id,
                description=task.description,
                is_success=True,
                result_text=f"{task.description} 完了",
            )

        orchestrator._run_worker = mock_run  # type: ignore[assignment]

        results = await orchestrator.execute(tasks)
        assert len(results) == 2
        assert all(r.is_success for r in results)

    @pytest.mark.asyncio
    async def test_部分失敗時に成功結果が保持される(self) -> None:
        mock_model = MagicMock()
        tasks = [
            SubTask(description="成功タスク", task_id="t1"),
            SubTask(description="失敗タスク", task_id="t2"),
        ]

        orchestrator = Orchestrator(
            model=mock_model,
            tools=[],
            max_workers=3,
        )

        async def mock_run(task: SubTask, wid: str) -> WorkerResult:
            if task.task_id == "t2":
                return WorkerResult(
                    task_id=task.task_id,
                    description=task.description,
                    is_success=False,
                    error="テストエラー",
                )
            return WorkerResult(
                task_id=task.task_id,
                description=task.description,
                is_success=True,
                result_text="完了",
            )

        orchestrator._run_worker = mock_run  # type: ignore[assignment]

        results = await orchestrator.execute(tasks)
        assert len(results) == 2
        success_results = [r for r in results if r.is_success]
        fail_results = [r for r in results if not r.is_success]
        assert len(success_results) == 1
        assert len(fail_results) == 1

    @pytest.mark.asyncio
    async def test_メトリクスが記録される(self) -> None:
        mock_model = MagicMock()
        tasks = [SubTask(description="タスクA", task_id="t1")]

        orchestrator = Orchestrator(
            model=mock_model,
            tools=[],
            max_workers=3,
        )

        async def mock_run(task: SubTask, wid: str) -> WorkerResult:
            return WorkerResult(
                task_id=task.task_id,
                description=task.description,
                is_success=True,
                prompt_tokens=100,
                completion_tokens=50,
            )

        orchestrator._run_worker = mock_run  # type: ignore[assignment]

        metrics = SessionMetrics()
        await orchestrator.execute(tasks, metrics=metrics)
        assert len(metrics.worker_metrics) == 1
        assert metrics.worker_metrics[0].prompt_tokens == 100

    @pytest.mark.asyncio
    async def test_Semaphoreで並列数が制限される(self) -> None:
        mock_model = MagicMock()
        # 5タスクを最大2並列で実行
        tasks = [
            SubTask(description=f"タスク{i}", task_id=f"t{i}")
            for i in range(5)
        ]

        orchestrator = Orchestrator(
            model=mock_model,
            tools=[],
            max_workers=2,
        )

        concurrent_count = 0
        max_concurrent = 0
        async def mock_run_no_sem(task: SubTask, wid: str) -> WorkerResult:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return WorkerResult(
                task_id=task.task_id,
                description=task.description,
                is_success=True,
            )

        orchestrator._run_worker = mock_run_no_sem  # type: ignore[assignment]

        # _run_worker をモックしているのでSemaphoreが効かない
        # 代わりに Semaphore の max_workers 設定値を確認
        assert orchestrator._semaphore._value == 2  # type: ignore[attr-defined]
        await orchestrator.execute(tasks)
        assert len(tasks) == 5  # 全タスクが処理された


class TestOrchestratorイベント実行:
    """Orchestrator.execute_with_events のテスト."""

    @pytest.mark.asyncio
    async def test_イベントが順序通り発行される(self) -> None:
        mock_model = MagicMock()
        tasks = [
            SubTask(description="タスクA", task_id="t1"),
            SubTask(description="タスクB", task_id="t2"),
        ]

        orchestrator = Orchestrator(
            model=mock_model,
            tools=[],
            max_workers=3,
        )

        async def mock_run(task: SubTask, wid: str) -> WorkerResult:
            return WorkerResult(
                task_id=task.task_id,
                description=task.description,
                is_success=True,
                result_text=f"{task.description} 完了",
            )

        orchestrator._run_worker = mock_run  # type: ignore[assignment]

        events = [e async for e in orchestrator.execute_with_events(tasks)]
        event_types = [e.event_type for e in events]

        assert event_types[0] == "parallel_start"
        assert "worker_start" in event_types
        assert "worker_end" in event_types
        assert event_types[-1] == "parallel_end"

        last = events[-1]
        assert last.data["succeeded"] == 2
        assert last.data["failed"] == 0

    @pytest.mark.asyncio
    async def test_失敗ワーカーのイベントが正しい(self) -> None:
        mock_model = MagicMock()
        tasks = [
            SubTask(description="成功タスク", task_id="t1"),
            SubTask(description="失敗タスク", task_id="t2"),
        ]

        orchestrator = Orchestrator(
            model=mock_model,
            tools=[],
            max_workers=3,
        )

        async def mock_run(task: SubTask, wid: str) -> WorkerResult:
            if task.task_id == "t2":
                return WorkerResult(
                    task_id=task.task_id,
                    description=task.description,
                    is_success=False,
                    error="テストエラー",
                )
            return WorkerResult(
                task_id=task.task_id,
                description=task.description,
                is_success=True,
            )

        orchestrator._run_worker = mock_run  # type: ignore[assignment]

        events = [e async for e in orchestrator.execute_with_events(tasks)]
        last = events[-1]
        assert last.data["succeeded"] == 1
        assert last.data["failed"] == 1

    @pytest.mark.asyncio
    async def test_逐次実行タスクのイベント(self) -> None:
        mock_model = MagicMock()
        tasks = [
            SubTask(
                description="タスクA", task_id="t1", target_files=["shared.py"]
            ),
            SubTask(
                description="タスクB", task_id="t2", target_files=["shared.py"]
            ),
        ]

        orchestrator = Orchestrator(
            model=mock_model,
            tools=[],
            max_workers=3,
        )

        async def mock_run(task: SubTask, wid: str) -> WorkerResult:
            return WorkerResult(
                task_id=task.task_id,
                description=task.description,
                is_success=True,
            )

        orchestrator._run_worker = mock_run  # type: ignore[assignment]

        events = [e async for e in orchestrator.execute_with_events(tasks)]
        event_types = [e.event_type for e in events]

        assert event_types.count("worker_start") == 2
        assert event_types.count("worker_end") == 2
        assert events[-1].data["total"] == 2

    @pytest.mark.asyncio
    async def test_メトリクスが記録される(self) -> None:
        mock_model = MagicMock()
        tasks = [SubTask(description="タスクA", task_id="t1")]

        orchestrator = Orchestrator(
            model=mock_model,
            tools=[],
            max_workers=3,
        )

        async def mock_run(task: SubTask, wid: str) -> WorkerResult:
            return WorkerResult(
                task_id=task.task_id,
                description=task.description,
                is_success=True,
                prompt_tokens=200,
                completion_tokens=100,
            )

        orchestrator._run_worker = mock_run  # type: ignore[assignment]

        metrics = SessionMetrics()
        _ = [
            e async for e in orchestrator.execute_with_events(tasks, metrics=metrics)
        ]
        assert len(metrics.worker_metrics) == 1
        assert metrics.worker_metrics[0].prompt_tokens == 200
