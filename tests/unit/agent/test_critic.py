"""Criticクラスのテスト."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from myagent.agent.critic import Critic


class TestCriticのdetect_loop:
    """Critic.detect_loop のテスト."""

    def test_メッセージが空の場合Falseを返す(self) -> None:
        critic = Critic()
        assert critic.detect_loop([]) is False

    def test_AIMessageが1件以下の場合Falseを返す(self) -> None:
        critic = Critic()
        msg = AIMessage(content="こんにちは")
        assert critic.detect_loop([msg]) is False

    def test_tool_callsがないAIMessageはFalseを返す(self) -> None:
        critic = Critic()
        msgs = [
            AIMessage(content="回答1"),
            AIMessage(content="回答2"),
        ]
        assert critic.detect_loop(msgs) is False

    def test_異なるツール呼び出しが2回ならFalseを返す(self) -> None:
        critic = Critic()
        msg1 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "foo.py"},
                    "id": "1",
                    "type": "tool_call",
                }
            ],
        )
        msg2 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {"path": "bar.py", "content": "test"},
                    "id": "2",
                    "type": "tool_call",
                }
            ],
        )
        assert critic.detect_loop([msg1, msg2]) is False

    def test_同一ツールと引数が2回連続でTrueを返す(self) -> None:
        critic = Critic()
        msg1 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "foo.py"},
                    "id": "1",
                    "type": "tool_call",
                }
            ],
        )
        msg2 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "foo.py"},
                    "id": "2",
                    "type": "tool_call",
                }
            ],
        )
        assert critic.detect_loop([msg1, msg2]) is True

    def test_同一ツールでも引数が異なる場合Falseを返す(self) -> None:
        critic = Critic()
        msg1 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "foo.py"},
                    "id": "1",
                    "type": "tool_call",
                }
            ],
        )
        msg2 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "bar.py"},
                    "id": "2",
                    "type": "tool_call",
                }
            ],
        )
        assert critic.detect_loop([msg1, msg2]) is False

    def test_AIMessage以外のメッセージが混在してもループ検知できる(self) -> None:
        critic = Critic()
        tool_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "run_command",
                    "args": {"command": "ls"},
                    "id": "1",
                    "type": "tool_call",
                }
            ],
        )
        human_msg = HumanMessage(content="やり直して")
        tool_msg2 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "run_command",
                    "args": {"command": "ls"},
                    "id": "2",
                    "type": "tool_call",
                }
            ],
        )
        msgs = [tool_msg, human_msg, tool_msg2]
        assert critic.detect_loop(msgs) is True

    def test_windowパラメータで検査範囲を制限できる(self) -> None:
        critic = Critic()
        # 古い重複は検知しない（windowの外）
        old_msg1 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "foo.py"},
                    "id": "1",
                    "type": "tool_call",
                }
            ],
        )
        old_msg2 = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "foo.py"},
                    "id": "2",
                    "type": "tool_call",
                }
            ],
        )
        new_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {"path": "bar.py", "content": "x"},
                    "id": "3",
                    "type": "tool_call",
                }
            ],
        )
        # window=1 では1件しか見ないのでFalse
        assert critic.detect_loop([old_msg1, old_msg2, new_msg], window=1) is False
