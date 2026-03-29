"""セッションメトリクスモジュール.

エージェントのツール呼び出し精度・ステップ数を追跡する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkerMetrics:
    """ワーカー単位のメトリクス."""

    worker_id: str
    task_description: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """総トークン数."""
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ToolMetric:
    """ツール別のメトリクス."""

    successes: int = 0
    failures: int = 0

    @property
    def total(self) -> int:
        """総呼び出し回数."""
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        """成功率（0.0〜1.0）."""
        if self.total == 0:
            return 0.0
        return self.successes / self.total


@dataclass
class SessionMetrics:
    """セッション単位の精度メトリクス.

    ツール呼び出しの成功/失敗数、ステップ数を追跡する。
    """

    tool_calls: int = 0
    tool_successes: int = 0
    tool_failures: int = 0
    steps: int = 0
    recovery_attempts: int = 0
    recovery_successes: int = 0
    tool_call_details: dict[str, ToolMetric] = field(default_factory=dict)
    worker_metrics: list[WorkerMetrics] = field(default_factory=list)

    def record_tool_call(self, tool_name: str, *, is_success: bool) -> None:
        """ツール呼び出しを記録する.

        Args:
            tool_name: ツール名。
            is_success: 成功ならTrue。
        """
        self.tool_calls += 1
        if is_success:
            self.tool_successes += 1
        else:
            self.tool_failures += 1

        if tool_name not in self.tool_call_details:
            self.tool_call_details[tool_name] = ToolMetric()

        metric = self.tool_call_details[tool_name]
        if is_success:
            metric.successes += 1
        else:
            metric.failures += 1

    def record_step(self) -> None:
        """ステップ（ループ1回）を記録する."""
        self.steps += 1

    def record_recovery_attempt(self) -> None:
        """回復試行を記録する."""
        self.recovery_attempts += 1

    def record_recovery_success(self) -> None:
        """回復成功を記録する."""
        self.recovery_successes += 1

    def record_worker(
        self,
        worker_id: str,
        task_description: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """ワーカーの実行結果を記録する.

        Args:
            worker_id: ワーカー識別子。
            task_description: 実行したタスクの説明。
            prompt_tokens: プロンプトトークン数。
            completion_tokens: 完了トークン数。
        """
        self.worker_metrics.append(
            WorkerMetrics(
                worker_id=worker_id,
                task_description=task_description,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )

    @property
    def success_rate(self) -> float:
        """全体のツール成功率（0.0〜1.0）."""
        if self.tool_calls == 0:
            return 0.0
        return self.tool_successes / self.tool_calls

    def summary(self) -> dict[str, Any]:
        """メトリクスの集計結果を辞書で返す.

        Returns:
            集計結果の辞書。
        """
        tool_details: dict[str, dict[str, Any]] = {}
        for name, metric in sorted(self.tool_call_details.items()):
            tool_details[name] = {
                "successes": metric.successes,
                "failures": metric.failures,
                "total": metric.total,
                "success_rate": metric.success_rate,
            }

        worker_details: list[dict[str, Any]] = []
        for wm in self.worker_metrics:
            worker_details.append({
                "worker_id": wm.worker_id,
                "task_description": wm.task_description,
                "prompt_tokens": wm.prompt_tokens,
                "completion_tokens": wm.completion_tokens,
                "total_tokens": wm.total_tokens,
            })

        return {
            "tool_calls": self.tool_calls,
            "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures,
            "success_rate": self.success_rate,
            "steps": self.steps,
            "recovery_attempts": self.recovery_attempts,
            "recovery_successes": self.recovery_successes,
            "tool_details": tool_details,
            "worker_details": worker_details,
        }
