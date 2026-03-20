"""AgentEvent のテスト."""

from __future__ import annotations

from myagent.agent.events import AgentEvent


class TestAgentEventのファクトリメソッド:
    """AgentEvent の静的ファクトリメソッドのテスト."""

    def test_stream_tokenイベントを生成できる(self) -> None:
        event = AgentEvent.stream_token("hello")
        assert event.event_type == "stream_token"
        assert event.data["token"] == "hello"

    def test_tool_startイベントを生成できる(self) -> None:
        event = AgentEvent.tool_start("read_file", {"file_path": "a.txt"})
        assert event.event_type == "tool_start"
        assert event.data["tool_name"] == "read_file"
        assert event.data["arguments"] == {"file_path": "a.txt"}

    def test_tool_endイベントを生成できる(self) -> None:
        event = AgentEvent.tool_end("read_file", "内容", True)
        assert event.event_type == "tool_end"
        assert event.data["tool_name"] == "read_file"
        assert event.data["result"] == "内容"
        assert event.data["is_success"] is True

    def test_tool_end失敗イベントを生成できる(self) -> None:
        event = AgentEvent.tool_end("run_command", "エラー", False)
        assert event.data["is_success"] is False

    def test_confirm_requestイベントを生成できる(self) -> None:
        event = AgentEvent.confirm_request("ファイル削除", "test.py を削除します")
        assert event.event_type == "confirm_request"
        assert event.data["action"] == "ファイル削除"
        assert event.data["details"] == "test.py を削除します"

    def test_agent_completeイベントを生成できる(self) -> None:
        event = AgentEvent.agent_complete("作業完了しました")
        assert event.event_type == "agent_complete"
        assert event.data["final_answer"] == "作業完了しました"

    def test_agent_errorイベントを生成できる(self) -> None:
        event = AgentEvent.agent_error("LLM呼び出し失敗")
        assert event.event_type == "agent_error"
        assert event.data["error"] == "LLM呼び出し失敗"


class TestAgentEventの属性:
    """AgentEvent の属性のテスト."""

    def test_dataのデフォルトは空辞書(self) -> None:
        event = AgentEvent(event_type="stream_token")
        assert event.data == {}

    def test_dataにカスタムフィールドを設定できる(self) -> None:
        event = AgentEvent(event_type="tool_start", data={"key": "value"})
        assert event.data["key"] == "value"
