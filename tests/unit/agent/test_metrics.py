"""SessionMetrics のユニットテスト."""

from __future__ import annotations

from myagent.agent.metrics import SessionMetrics, ToolMetric, WorkerMetrics


class TestToolMetric:
    """ToolMetric のテスト."""

    def test_初期値はゼロ(self) -> None:
        metric = ToolMetric()
        assert metric.successes == 0
        assert metric.failures == 0
        assert metric.total == 0

    def test_成功率がゼロ除算にならない(self) -> None:
        metric = ToolMetric()
        assert metric.success_rate == 0.0

    def test_成功率が正しく計算される(self) -> None:
        metric = ToolMetric(successes=3, failures=1)
        assert metric.success_rate == 0.75

    def test_total計算が正しい(self) -> None:
        metric = ToolMetric(successes=5, failures=3)
        assert metric.total == 8


class TestSessionMetrics:
    """SessionMetrics のテスト."""

    def test_初期値はゼロ(self) -> None:
        metrics = SessionMetrics()
        assert metrics.tool_calls == 0
        assert metrics.tool_successes == 0
        assert metrics.tool_failures == 0
        assert metrics.steps == 0

    def test_ツール成功の記録(self) -> None:
        metrics = SessionMetrics()
        metrics.record_tool_call("read_file", is_success=True)

        assert metrics.tool_calls == 1
        assert metrics.tool_successes == 1
        assert metrics.tool_failures == 0
        assert "read_file" in metrics.tool_call_details
        assert metrics.tool_call_details["read_file"].successes == 1

    def test_ツール失敗の記録(self) -> None:
        metrics = SessionMetrics()
        metrics.record_tool_call("write_file", is_success=False)

        assert metrics.tool_calls == 1
        assert metrics.tool_successes == 0
        assert metrics.tool_failures == 1
        assert metrics.tool_call_details["write_file"].failures == 1

    def test_複数ツールの記録(self) -> None:
        metrics = SessionMetrics()
        metrics.record_tool_call("read_file", is_success=True)
        metrics.record_tool_call("read_file", is_success=True)
        metrics.record_tool_call("write_file", is_success=True)
        metrics.record_tool_call("write_file", is_success=False)

        assert metrics.tool_calls == 4
        assert metrics.tool_successes == 3
        assert metrics.tool_failures == 1
        assert metrics.tool_call_details["read_file"].successes == 2
        assert metrics.tool_call_details["write_file"].successes == 1
        assert metrics.tool_call_details["write_file"].failures == 1

    def test_ステップ記録(self) -> None:
        metrics = SessionMetrics()
        metrics.record_step()
        metrics.record_step()
        metrics.record_step()

        assert metrics.steps == 3

    def test_全体成功率の計算(self) -> None:
        metrics = SessionMetrics()
        metrics.record_tool_call("read_file", is_success=True)
        metrics.record_tool_call("read_file", is_success=True)
        metrics.record_tool_call("write_file", is_success=False)
        metrics.record_tool_call("write_file", is_success=True)

        assert metrics.success_rate == 0.75

    def test_ゼロ呼び出し時の成功率(self) -> None:
        metrics = SessionMetrics()
        assert metrics.success_rate == 0.0

    def test_サマリーの構造(self) -> None:
        metrics = SessionMetrics()
        metrics.record_tool_call("read_file", is_success=True)
        metrics.record_tool_call("write_file", is_success=False)
        metrics.record_step()

        summary = metrics.summary()

        assert summary["tool_calls"] == 2
        assert summary["tool_successes"] == 1
        assert summary["tool_failures"] == 1
        assert summary["success_rate"] == 0.5
        assert summary["steps"] == 1
        assert "read_file" in summary["tool_details"]
        assert "write_file" in summary["tool_details"]
        assert summary["tool_details"]["read_file"]["successes"] == 1
        assert summary["tool_details"]["write_file"]["failures"] == 1

    def test_空のサマリー(self) -> None:
        metrics = SessionMetrics()
        summary = metrics.summary()

        assert summary["tool_calls"] == 0
        assert summary["success_rate"] == 0.0
        assert summary["steps"] == 0
        assert summary["tool_details"] == {}
        assert summary["worker_details"] == []


class TestWorkerMetrics:
    """WorkerMetrics のテスト."""

    def test_初期値(self) -> None:
        wm = WorkerMetrics(worker_id="w1", task_description="タスク")
        assert wm.worker_id == "w1"
        assert wm.task_description == "タスク"
        assert wm.prompt_tokens == 0
        assert wm.completion_tokens == 0
        assert wm.total_tokens == 0

    def test_total_tokensの計算(self) -> None:
        wm = WorkerMetrics(
            worker_id="w1",
            task_description="タスク",
            prompt_tokens=100,
            completion_tokens=50,
        )
        assert wm.total_tokens == 150


class Testrecord_worker:
    """SessionMetrics.record_worker のテスト."""

    def test_ワーカーメトリクスが記録される(self) -> None:
        metrics = SessionMetrics()
        metrics.record_worker("w1", "タスク1", prompt_tokens=100, completion_tokens=50)
        assert len(metrics.worker_metrics) == 1
        assert metrics.worker_metrics[0].worker_id == "w1"
        assert metrics.worker_metrics[0].prompt_tokens == 100

    def test_複数ワーカーの記録(self) -> None:
        metrics = SessionMetrics()
        metrics.record_worker("w1", "タスク1")
        metrics.record_worker("w2", "タスク2")
        assert len(metrics.worker_metrics) == 2

    def test_サマリーにworker_detailsが含まれる(self) -> None:
        metrics = SessionMetrics()
        metrics.record_worker("w1", "タスク1", prompt_tokens=50, completion_tokens=25)
        summary = metrics.summary()
        assert len(summary["worker_details"]) == 1
        assert summary["worker_details"][0]["worker_id"] == "w1"
        assert summary["worker_details"][0]["total_tokens"] == 75
