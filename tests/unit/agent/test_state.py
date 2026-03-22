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

    def test_依存関係フィールドのデフォルト値(self) -> None:
        task = SubTask(description="テストタスク")
        assert task.task_id == ""
        assert task.depends_on == []
        assert task.target_files == []

    def test_後方互換性_既存コンストラクタが動作する(self) -> None:
        task = SubTask(description="テスト", is_completed=True, result="完了")
        assert task.description == "テスト"
        assert task.is_completed is True
        assert task.task_id == ""
        assert task.depends_on == []

    def test_依存関係フィールドを指定して生成できる(self) -> None:
        task = SubTask(
            description="ファイル修正",
            task_id="t1",
            depends_on=["t0"],
            target_files=["src/foo.py", "src/bar.py"],
        )
        assert task.task_id == "t1"
        assert task.depends_on == ["t0"]
        assert task.target_files == ["src/foo.py", "src/bar.py"]


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
