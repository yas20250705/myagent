"""エージェント状態管理のテスト."""

from __future__ import annotations

from myagent.agent.state import AgentState, SubTask, ToolCallRecord


class TestSubTask:
    """SubTask のテスト."""

    def test_デフォルトで未完了状態(self) -> None:
        task = SubTask(description="テストタスク")
        assert task.is_completed is False
        assert task.result == ""

    def test_完了状態に変更できる(self) -> None:
        task = SubTask(description="テストタスク")
        task.is_completed = True
        task.result = "完了しました"
        assert task.is_completed is True


class TestToolCallRecord:
    """ToolCallRecord のテスト."""

    def test_デフォルトで成功状態(self) -> None:
        record = ToolCallRecord(tool_name="read_file")
        assert record.is_success is True
        assert record.arguments == {}
        assert record.result == ""

    def test_引数と結果を保持できる(self) -> None:
        record = ToolCallRecord(
            tool_name="write_file",
            arguments={"file_path": "test.txt", "content": "hello"},
            result="ファイルを書き込みました",
        )
        assert record.tool_name == "write_file"
        assert record.arguments["file_path"] == "test.txt"


class TestAgentState:
    """AgentState のテスト."""

    def test_TypedDictとして辞書で初期化できる(self) -> None:
        state: AgentState = {
            "messages": [],
            "phase": "planning",
            "loop_count": 0,
            "is_completed": False,
        }
        assert state["phase"] == "planning"
        assert state["is_completed"] is False

    def test_部分的なフィールドで初期化できる(self) -> None:
        state: AgentState = {"messages": [], "phase": "executing"}
        assert state["phase"] == "executing"
