"""マルチエージェントオーケストレーター.

サブタスクの依存関係を解析し、独立したタスクを並列実行する。
各ワーカーは独立した AgentRunner インスタンスで実行される。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from myagent.agent.events import AgentEvent
from myagent.agent.graph import AgentRunner
from myagent.agent.state import SubTask
from myagent.infra.errors import OrchestratorError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool

    from myagent.agent.executor import Executor
    from myagent.agent.metrics import SessionMetrics
    from myagent.agent.prompt_manager import PromptManager
    from myagent.infra.context import ContextManager
    from myagent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    """個々のワーカーの実行結果."""

    task_id: str
    description: str
    is_success: bool = True
    result_text: str = ""
    error: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


def topological_sort_levels(tasks: list[SubTask]) -> list[list[SubTask]]:
    """サブタスクを依存関係に基づいてレベル別にグループ化する.

    同じレベルのタスクは並列実行可能。レベル0が最初に実行される。

    Args:
        tasks: 依存関係付きサブタスクのリスト。

    Returns:
        レベル別にグループ化されたサブタスクのリスト。

    Raises:
        OrchestratorError: 循環依存が検出された場合。
    """
    if not tasks:
        return []

    task_map: dict[str, SubTask] = {}
    for task in tasks:
        if task.task_id:
            task_map[task.task_id] = task

    # 入次数を計算
    in_degree: dict[str, int] = {t.task_id: 0 for t in tasks if t.task_id}
    for task in tasks:
        if not task.task_id:
            continue
        for dep in task.depends_on:
            if dep in task_map:
                in_degree[task.task_id] = in_degree.get(task.task_id, 0) + 1

    # task_id がないタスクはレベル0として扱う
    no_id_tasks = [t for t in tasks if not t.task_id]

    levels: list[list[SubTask]] = []
    remaining = {tid for tid in in_degree}
    processed: set[str] = set()

    while remaining:
        # 入次数0のタスクを現在のレベルに追加
        current_level_ids = [
            tid for tid in remaining if in_degree.get(tid, 0) == 0
        ]

        if not current_level_ids:
            msg = "循環依存が検出されました"
            raise OrchestratorError(msg)

        current_level = [task_map[tid] for tid in current_level_ids]
        levels.append(current_level)

        processed.update(current_level_ids)
        remaining -= set(current_level_ids)

        # 完了したタスクに依存するタスクの入次数を減らす
        for task in tasks:
            if task.task_id not in remaining:
                continue
            new_degree = 0
            for dep in task.depends_on:
                if dep not in processed:
                    new_degree += 1
            in_degree[task.task_id] = new_degree

    # task_id なしタスクを先頭レベルに追加
    if no_id_tasks:
        if levels:
            levels[0] = no_id_tasks + levels[0]
        else:
            levels.append(no_id_tasks)

    return levels


def detect_file_conflicts(
    tasks: list[SubTask],
) -> tuple[list[SubTask], list[SubTask]]:
    """並列実行候補のタスク間でファイルコンフリクトを検知する.

    同一ファイルを対象とするタスクを逐次実行グループに移動する。

    Args:
        tasks: 並列実行候補のサブタスクリスト。

    Returns:
        (並列実行可能なタスク, 逐次実行にフォールバックするタスク) のタプル。
    """
    if len(tasks) <= 1:
        return tasks, []

    # ファイル→タスクのマッピングを構築
    file_to_tasks: dict[str, list[int]] = defaultdict(list)
    for i, task in enumerate(tasks):
        for f in task.target_files:
            file_to_tasks[f].append(i)

    # コンフリクトするタスクのインデックスを特定
    conflict_indices: set[int] = set()
    for _file, indices in file_to_tasks.items():
        if len(indices) > 1:
            # 最初のタスク以外を逐次グループに移動
            for idx in indices[1:]:
                conflict_indices.add(idx)

    parallel = [t for i, t in enumerate(tasks) if i not in conflict_indices]
    sequential = [t for i, t in enumerate(tasks) if i in conflict_indices]

    if sequential:
        logger.info(
            "ファイルコンフリクト検知: %d個のタスクを逐次実行にフォールバック",
            len(sequential),
        )

    return parallel, sequential


class Orchestrator:
    """マルチエージェントオーケストレーター.

    依存関係に基づいてサブタスクを並列または逐次に実行する。
    """

    def __init__(
        self,
        model: BaseChatModel,
        tools: list[BaseTool],
        max_workers: int = 3,
        max_loops: int = 20,
        executor: Executor | None = None,
        confirm_callback: Callable[[str, dict[str, Any]], bool] | None = None,
        context_manager: ContextManager | None = None,
        prompt_manager: PromptManager | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._model = model
        self._tools = tools
        self._max_workers = max_workers
        self._max_loops = max_loops
        self._executor = executor
        self._confirm_callback = confirm_callback
        self._context_manager = context_manager
        self._prompt_manager = prompt_manager
        self._tool_registry = tool_registry
        self._semaphore = asyncio.Semaphore(max_workers)

    def _create_worker(self) -> AgentRunner:
        """独立した AgentRunner インスタンスを生成する."""
        return AgentRunner(
            model=self._model,
            tools=self._tools,
            max_loops=self._max_loops,
            executor=self._executor,
            confirm_callback=self._confirm_callback,
            context_manager=self._context_manager,
            prompt_manager=self._prompt_manager,
            tool_registry=self._tool_registry,
        )

    async def _run_worker(
        self,
        task: SubTask,
        worker_id: str,
    ) -> WorkerResult:
        """単一ワーカーでサブタスクを実行する.

        Args:
            task: 実行するサブタスク。
            worker_id: ワーカー識別子。

        Returns:
            ワーカーの実行結果。
        """
        async with self._semaphore:
            worker = self._create_worker()
            try:
                result = await worker.run(task.description)
                return WorkerResult(
                    task_id=task.task_id,
                    description=task.description,
                    is_success=True,
                    result_text=result,
                )
            except Exception as e:
                logger.warning(
                    "ワーカー %s が失敗: %s",
                    worker_id,
                    e,
                )
                return WorkerResult(
                    task_id=task.task_id,
                    description=task.description,
                    is_success=False,
                    error=str(e),
                )

    async def execute(
        self,
        tasks: list[SubTask],
        metrics: SessionMetrics | None = None,
    ) -> list[WorkerResult]:
        """サブタスクを依存関係に基づいて並列/逐次実行する.

        Args:
            tasks: 依存関係付きサブタスクのリスト。
            metrics: メトリクス記録先。

        Returns:
            全ワーカーの実行結果リスト。

        Raises:
            OrchestratorError: 循環依存が検出された場合。
        """
        levels = topological_sort_levels(tasks)
        all_results: list[WorkerResult] = []
        worker_counter = 0

        for level in levels:
            # 同レベルタスクのコンフリクトチェック
            parallel_tasks, sequential_tasks = detect_file_conflicts(level)

            # 並列実行
            if len(parallel_tasks) > 1:
                coros = []
                worker_ids = []
                for task in parallel_tasks:
                    worker_counter += 1
                    wid = f"worker-{worker_counter}"
                    worker_ids.append(wid)
                    coros.append(self._run_worker(task, wid))

                results = await asyncio.gather(*coros, return_exceptions=True)
                for wid, result in zip(worker_ids, results, strict=True):
                    if isinstance(result, BaseException):
                        wr = WorkerResult(
                            task_id="",
                            description="",
                            is_success=False,
                            error=str(result),
                        )
                    else:
                        wr = result
                    all_results.append(wr)

                    if metrics is not None:
                        metrics.record_worker(
                            worker_id=wid,
                            task_description=wr.description,
                            prompt_tokens=wr.prompt_tokens,
                            completion_tokens=wr.completion_tokens,
                        )
            elif parallel_tasks:
                # 1つだけの場合は直接実行
                worker_counter += 1
                wid = f"worker-{worker_counter}"
                wr = await self._run_worker(parallel_tasks[0], wid)
                all_results.append(wr)
                if metrics is not None:
                    metrics.record_worker(
                        worker_id=wid,
                        task_description=wr.description,
                        prompt_tokens=wr.prompt_tokens,
                        completion_tokens=wr.completion_tokens,
                    )

            # 逐次実行（コンフリクトタスク）
            for task in sequential_tasks:
                worker_counter += 1
                wid = f"worker-{worker_counter}"
                wr = await self._run_worker(task, wid)
                all_results.append(wr)
                if metrics is not None:
                    metrics.record_worker(
                        worker_id=wid,
                        task_description=wr.description,
                        prompt_tokens=wr.prompt_tokens,
                        completion_tokens=wr.completion_tokens,
                    )

        return all_results

    async def execute_with_events(
        self,
        tasks: list[SubTask],
        metrics: SessionMetrics | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """サブタスクを実行し、イベントをストリーミングで返す.

        Args:
            tasks: 依存関係付きサブタスクのリスト。
            metrics: メトリクス記録先。

        Yields:
            エージェントイベント。
        """
        levels = topological_sort_levels(tasks)
        all_tasks_flat = [t for level in levels for t in level]

        yield AgentEvent.parallel_start(
            total_workers=len(all_tasks_flat),
            task_descriptions=[t.description for t in all_tasks_flat],
        )

        all_results: list[WorkerResult] = []
        worker_counter = 0

        for level in levels:
            parallel_tasks, sequential_tasks = detect_file_conflicts(level)

            # 並列実行
            if len(parallel_tasks) > 1:
                coros = []
                worker_ids = []
                for task in parallel_tasks:
                    worker_counter += 1
                    wid = f"worker-{worker_counter}"
                    worker_ids.append(wid)
                    yield AgentEvent.worker_start(wid, task.description)
                    coros.append(self._run_worker(task, wid))

                results = await asyncio.gather(*coros, return_exceptions=True)
                for wid, task, result in zip(
                    worker_ids, parallel_tasks, results, strict=True
                ):
                    if isinstance(result, BaseException):
                        wr = WorkerResult(
                            task_id=task.task_id,
                            description=task.description,
                            is_success=False,
                            error=str(result),
                        )
                    else:
                        wr = result
                    all_results.append(wr)

                    yield AgentEvent.worker_end(
                        wid, wr.description, wr.is_success, wr.result_text
                    )
                    if metrics is not None:
                        metrics.record_worker(
                            worker_id=wid,
                            task_description=wr.description,
                            prompt_tokens=wr.prompt_tokens,
                            completion_tokens=wr.completion_tokens,
                        )
            elif parallel_tasks:
                worker_counter += 1
                wid = f"worker-{worker_counter}"
                yield AgentEvent.worker_start(wid, parallel_tasks[0].description)
                wr = await self._run_worker(parallel_tasks[0], wid)
                all_results.append(wr)
                yield AgentEvent.worker_end(
                    wid, wr.description, wr.is_success, wr.result_text
                )
                if metrics is not None:
                    metrics.record_worker(
                        worker_id=wid,
                        task_description=wr.description,
                        prompt_tokens=wr.prompt_tokens,
                        completion_tokens=wr.completion_tokens,
                    )

            # 逐次実行
            for task in sequential_tasks:
                worker_counter += 1
                wid = f"worker-{worker_counter}"
                yield AgentEvent.worker_start(wid, task.description)
                wr = await self._run_worker(task, wid)
                all_results.append(wr)
                yield AgentEvent.worker_end(
                    wid, wr.description, wr.is_success, wr.result_text
                )
                if metrics is not None:
                    metrics.record_worker(
                        worker_id=wid,
                        task_description=wr.description,
                        prompt_tokens=wr.prompt_tokens,
                        completion_tokens=wr.completion_tokens,
                    )

        succeeded = sum(1 for r in all_results if r.is_success)
        failed = len(all_results) - succeeded
        summary = _build_summary(all_results)

        yield AgentEvent.parallel_end(
            total=len(all_results),
            succeeded=succeeded,
            failed=failed,
            summary=summary,
        )


def _build_summary(results: list[WorkerResult]) -> str:
    """ワーカー結果を要約テキストに統合する."""
    lines: list[str] = []
    for r in results:
        status = "✓" if r.is_success else "✗"
        line = f"{status} [{r.task_id}] {r.description}"
        if not r.is_success and r.error:
            line += f" (エラー: {r.error[:100]})"
        lines.append(line)
    return "\n".join(lines)
