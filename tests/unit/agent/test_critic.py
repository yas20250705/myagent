"""Criticクラスのテスト."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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

    def test_同一ツールと引数が2回連続ではFalseを返す(self) -> None:
        # 2回連続は誤検知防止のため許容する（techlearnなどのリサーチ系スキル対応）
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
        assert critic.detect_loop([msg1, msg2]) is False

    def test_同一ツールと引数が3回連続でTrueを返す(self) -> None:
        critic = Critic()
        same_call = {
            "name": "read_file",
            "args": {"path": "foo.py"},
            "type": "tool_call",
        }
        msgs = [
            AIMessage(content="", tool_calls=[{**same_call, "id": "1"}]),
            AIMessage(content="", tool_calls=[{**same_call, "id": "2"}]),
            AIMessage(content="", tool_calls=[{**same_call, "id": "3"}]),
        ]
        assert critic.detect_loop(msgs) is True

    def test_2回連続の後に別ツールを呼んだ場合Falseを返す(self) -> None:
        critic = Critic()
        same_call = {
            "name": "read_file",
            "args": {"path": "foo.py"},
            "type": "tool_call",
        }
        other_call = {
            "name": "write_file",
            "args": {"path": "bar.py", "content": "x"},
            "type": "tool_call",
        }
        msgs = [
            AIMessage(content="", tool_calls=[{**same_call, "id": "1"}]),
            AIMessage(content="", tool_calls=[{**same_call, "id": "2"}]),
            AIMessage(content="", tool_calls=[{**other_call, "id": "3"}]),
        ]
        assert critic.detect_loop(msgs) is False

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

    def test_AIMessage以外のメッセージが混在しても3回連続ループを検知できる(self) -> None:
        critic = Critic()
        same_call = {
            "name": "run_command",
            "args": {"command": "ls"},
            "type": "tool_call",
        }
        msgs = [
            AIMessage(content="", tool_calls=[{**same_call, "id": "1"}]),
            HumanMessage(content="やり直して"),
            AIMessage(content="", tool_calls=[{**same_call, "id": "2"}]),
            HumanMessage(content="もう一度"),
            AIMessage(content="", tool_calls=[{**same_call, "id": "3"}]),
        ]
        assert critic.detect_loop(msgs) is True

    def test_windowパラメータで検査範囲を制限できる(self) -> None:
        critic = Critic()
        same_call = {
            "name": "read_file",
            "args": {"path": "foo.py"},
            "type": "tool_call",
        }
        other_call = {
            "name": "write_file",
            "args": {"path": "bar.py", "content": "x"},
            "type": "tool_call",
        }
        # 3回連続だが window=2 では2件しか見ないのでFalse（閾値3未満）
        msgs = [
            AIMessage(content="", tool_calls=[{**same_call, "id": "1"}]),
            AIMessage(content="", tool_calls=[{**same_call, "id": "2"}]),
            AIMessage(content="", tool_calls=[{**same_call, "id": "3"}]),
            AIMessage(content="", tool_calls=[{**other_call, "id": "4"}]),
        ]
        assert critic.detect_loop(msgs, window=2) is False

    def test_consecutive_thresholdパラメータで閾値を変更できる(self) -> None:
        critic = Critic()
        same_call = {
            "name": "read_file",
            "args": {"path": "foo.py"},
            "type": "tool_call",
        }
        msgs = [
            AIMessage(content="", tool_calls=[{**same_call, "id": "1"}]),
            AIMessage(content="", tool_calls=[{**same_call, "id": "2"}]),
        ]
        # threshold=2 では2回連続でTrueになる
        assert critic.detect_loop(msgs, consecutive_threshold=2) is True
        # threshold=3（デフォルト）では2回連続でFalse
        assert critic.detect_loop(msgs, consecutive_threshold=3) is False


class TestCriticのdetect_error_repetition:
    """Critic.detect_error_repetition のテスト."""

    def test_メッセージが空の場合は検知しない(self) -> None:
        critic = Critic()
        detected, msg = critic.detect_error_repetition([])
        assert detected is False
        assert msg == ""

    def test_エラーが閾値未満では検知しない(self) -> None:
        critic = Critic()
        msgs = [
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="1",
                name="read_file",
            ),
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="2",
                name="read_file",
            ),
        ]
        detected, msg = critic.detect_error_repetition(msgs, threshold=3)
        assert detected is False

    def test_同一エラーが閾値以上で検知する(self) -> None:
        critic = Critic()
        msgs = [
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="1",
                name="read_file",
            ),
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="2",
                name="read_file",
            ),
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="3",
                name="read_file",
            ),
        ]
        detected, msg = critic.detect_error_repetition(msgs, threshold=3)
        assert detected is True
        assert "read_file" in msg
        assert "3回" in msg

    def test_異なるツールのエラーは別カウント(self) -> None:
        critic = Critic()
        msgs = [
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="1",
                name="read_file",
            ),
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="2",
                name="write_file",
            ),
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="3",
                name="read_file",
            ),
        ]
        detected, _ = critic.detect_error_repetition(msgs, threshold=3)
        assert detected is False

    def test_異なるエラーメッセージは別カウント(self) -> None:
        critic = Critic()
        msgs = [
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="1",
                name="read_file",
            ),
            ToolMessage(
                content="Error: パーミッションが拒否されました",
                tool_call_id="2",
                name="read_file",
            ),
            ToolMessage(
                content="Error: ファイルが見つかりません",
                tool_call_id="3",
                name="read_file",
            ),
        ]
        detected, _ = critic.detect_error_repetition(msgs, threshold=3)
        assert detected is False

    def test_禁止キーワードを含むSecurityErrorを検知する(self) -> None:
        critic = Critic()
        msgs = [
            ToolMessage(
                content="許可ディレクトリ外へのアクセスは禁止されています: C:\\",
                tool_call_id="1",
                name="list_directory",
            ),
            ToolMessage(
                content="許可ディレクトリ外へのアクセスは禁止されています: C:\\",
                tool_call_id="2",
                name="list_directory",
            ),
            ToolMessage(
                content="許可ディレクトリ外へのアクセスは禁止されています: C:\\",
                tool_call_id="3",
                name="list_directory",
            ),
        ]
        detected, msg = critic.detect_error_repetition(msgs, threshold=3)
        assert detected is True
        assert "list_directory" in msg

    def test_statusがerrorのToolMessageを検知する(self) -> None:
        critic = Critic()
        msgs = [
            ToolMessage(
                content="何らかのメッセージ",
                tool_call_id="1",
                name="list_directory",
                status="error",
            ),
            ToolMessage(
                content="何らかのメッセージ",
                tool_call_id="2",
                name="list_directory",
                status="error",
            ),
            ToolMessage(
                content="何らかのメッセージ",
                tool_call_id="3",
                name="list_directory",
                status="error",
            ),
        ]
        detected, msg = critic.detect_error_repetition(msgs, threshold=3)
        assert detected is True
        assert "list_directory" in msg

    def test_エラーキーワードを含まないメッセージは無視(self) -> None:
        critic = Critic()
        msgs = [
            ToolMessage(
                content="ファイルの内容: hello world",
                tool_call_id="1",
                name="read_file",
            ),
            ToolMessage(
                content="ファイルの内容: hello world",
                tool_call_id="2",
                name="read_file",
            ),
            ToolMessage(
                content="ファイルの内容: hello world",
                tool_call_id="3",
                name="read_file",
            ),
        ]
        detected, _ = critic.detect_error_repetition(msgs, threshold=3)
        assert detected is False

    def test_AIMessageとHumanMessageが混在しても正しく検知(self) -> None:
        critic = Critic()
        msgs = [
            HumanMessage(content="ファイルを読んで"),
            AIMessage(content="", tool_calls=[]),
            ToolMessage(
                content="Error: not found",
                tool_call_id="1",
                name="read_file",
            ),
            HumanMessage(content="もう一度"),
            ToolMessage(
                content="Error: not found",
                tool_call_id="2",
                name="read_file",
            ),
            ToolMessage(
                content="Error: not found",
                tool_call_id="3",
                name="read_file",
            ),
        ]
        detected, msg = critic.detect_error_repetition(msgs, threshold=3)
        assert detected is True
        assert "別のアプローチ" in msg


class TestCriticのbuild_recovery_message:
    """Critic.build_recovery_message のテスト."""

    def test_loop検知タイプのメッセージにパターン説明が含まれる(self) -> None:
        critic = Critic()
        msg = critic.build_recovery_message("loop", "同一ツール呼び出しが連続しています")
        assert "ブロックされています" in msg
        assert "同一ツール呼び出しの繰り返し" in msg
        assert "同一ツール呼び出しが連続しています" in msg

    def test_error_repetition検知タイプのメッセージにパターン説明が含まれる(self) -> None:
        critic = Critic()
        msg = critic.build_recovery_message(
            "error_repetition", "read_file で同じエラーが3回繰り返されました"
        )
        assert "ブロックされています" in msg
        assert "同一エラーの繰り返し" in msg
        assert "read_file" in msg

    def test_代替アプローチ提案指示が含まれる(self) -> None:
        critic = Critic()
        msg = critic.build_recovery_message("loop", "詳細")
        assert "別のアプローチを最大3つ提案" in msg
        assert "最も有望なものを試行" in msg

    def test_failed_approachesなしの場合の代替検討指示(self) -> None:
        critic = Critic()
        msg = critic.build_recovery_message("loop", "詳細")
        assert "代替アプローチを検討してください" in msg

    def test_failed_approachesありの場合に過去の失敗が列挙される(self) -> None:
        critic = Critic()
        failed = ["同一ツール呼び出しの繰り返し（1回目）", "別のエラー（2回目）"]
        msg = critic.build_recovery_message("loop", "詳細", failed_approaches=failed)
        assert "これまでに失敗したアプローチ" in msg
        assert "1. 同一ツール呼び出しの繰り返し（1回目）" in msg
        assert "2. 別のエラー（2回目）" in msg
        assert "異なる" in msg

    def test_未知の検知タイプでもメッセージが生成される(self) -> None:
        critic = Critic()
        msg = critic.build_recovery_message("unknown", "何らかのパターン")
        assert "非生産的なパターン" in msg
        assert "何らかのパターン" in msg
