"""CLIディスプレイモジュールのテスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from myagent.agent.events import AgentEvent
from myagent.cli.display import (
    _build_confirm_details,
    _start_spinner,
    _stop_spinner,
    confirm_action,
    handle_event,
    print_token_usage,
)


class TestSpinner:
    """スピナー関数のテスト."""

    def test_start_spinnerでconsole_statusが呼ばれる(self) -> None:
        mock_status = MagicMock()
        with patch("myagent.cli.display.console") as mock_console:
            mock_console.status.return_value = mock_status
            _start_spinner("read_file")
            mock_console.status.assert_called_once()
            mock_status.__enter__.assert_called_once()

    def test_stop_spinnerでアクティブスピナーが停止される(self) -> None:
        mock_status = MagicMock()
        with patch("myagent.cli.display.console") as mock_console:
            mock_console.status.return_value = mock_status
            _start_spinner("write_file")
            _stop_spinner()
            mock_status.__exit__.assert_called_once()

    def test_stop_spinner_スピナーなしでも安全に実行できる(self) -> None:
        with patch("myagent.cli.display._active_spinner", None):
            _stop_spinner()  # エラーが出ないことを確認


class TestHandle_event:
    """handle_event 関数のテスト."""

    def test_stream_tokenイベントでprint_tokenが呼ばれる(self) -> None:
        event = AgentEvent.stream_token("hello")
        with patch("myagent.cli.display.console") as mock_console:
            handle_event(event)
            mock_console.print.assert_called()

    def test_tool_startイベントでスピナーが開始される(self) -> None:
        event = AgentEvent.tool_start("read_file", {"file_path": "test.txt"})
        mock_status = MagicMock()
        with patch("myagent.cli.display.console") as mock_console:
            mock_console.status.return_value = mock_status
            handle_event(event)
            mock_console.status.assert_called_once()
            mock_status.__enter__.assert_called_once()

    def test_tool_endイベントでスピナーが停止されてから結果が表示される(self) -> None:
        event = AgentEvent.tool_end("read_file", "ファイル内容", True)
        with patch("myagent.cli.display._stop_spinner") as mock_stop:
            with patch("myagent.cli.display.console") as mock_console:
                handle_event(event)
                mock_stop.assert_called_once()
                mock_console.print.assert_called()

    def test_tool_endイベントで失敗結果が表示される(self) -> None:
        event = AgentEvent.tool_end("run_command", "エラー", False)
        with patch("myagent.cli.display.console") as mock_console:
            handle_event(event)
            mock_console.print.assert_called()

    def test_agent_completeイベントで完了が表示される(self) -> None:
        event = AgentEvent.agent_complete("完了しました")
        with patch("myagent.cli.display.console") as mock_console:
            handle_event(event)
            mock_console.print.assert_called()

    def test_agent_errorイベントでエラーが表示される(self) -> None:
        event = AgentEvent.agent_error("エラーメッセージ")
        with patch("myagent.cli.display.console") as mock_console:
            handle_event(event)
            mock_console.print.assert_called()

    def test_tool_end長い結果がトランケートされる(self) -> None:
        long_result = "\n".join([f"line {i}" for i in range(30)])
        event = AgentEvent.tool_end("read_file", long_result, True)
        with patch("myagent.cli.display.console") as mock_console:
            handle_event(event)
            mock_console.print.assert_called()

    def test_agent_completeでtotal_tokens_gt_0のときトークン表示される(self) -> None:
        event = AgentEvent.agent_complete(
            "完了", prompt_tokens=100, completion_tokens=50, model_name="gpt-4o-mini"
        )
        with patch("myagent.cli.display.console") as mock_console:
            with patch("myagent.cli.display.print_token_usage") as mock_print_usage:
                handle_event(event)
                mock_print_usage.assert_called_once_with(100, 50, 150, "gpt-4o-mini")
                mock_console.print.assert_called()

    def test_agent_completeでtotal_tokens_eq_0のときトークン表示しない(self) -> None:
        event = AgentEvent.agent_complete("完了")
        with patch("myagent.cli.display.console"):
            with patch("myagent.cli.display.print_token_usage") as mock_print_usage:
                handle_event(event)
                mock_print_usage.assert_not_called()


class TestConfirmAction:
    """confirm_action 関数のテスト."""

    def test_承認するとTrueが返る(self) -> None:
        with patch("myagent.cli.display.console") as mock_console:
            mock_console.input.return_value = "y"
            result = confirm_action(
                "write_file", {"file_path": "test.txt", "content": "hello"}
            )
            assert result is True

    def test_拒否するとFalseが返る(self) -> None:
        with patch("myagent.cli.display.console") as mock_console:
            mock_console.input.return_value = "n"
            result = confirm_action(
                "write_file", {"file_path": "test.txt", "content": "hello"}
            )
            assert result is False

    def test_yes入力でTrueが返る(self) -> None:
        with patch("myagent.cli.display.console") as mock_console:
            mock_console.input.return_value = "yes"
            result = confirm_action(
                "edit_file", {"file_path": "a.py", "old_string": "x", "new_string": "y"}
            )
            assert result is True

    def test_build_confirm_details_write_fileでファイルパスとプレビューが含まれる(
        self,
    ) -> None:
        text = _build_confirm_details(
            "write_file", {"file_path": "out.txt", "content": "line1\nline2"}
        )
        plain = text.plain
        assert "out.txt" in plain
        assert "line1" in plain

    def test_build_confirm_details_edit_fileでdiffが含まれる(self) -> None:
        text = _build_confirm_details(
            "edit_file", {"file_path": "a.py", "old_string": "foo", "new_string": "bar"}
        )
        plain = text.plain
        assert "foo" in plain
        assert "bar" in plain

    def test_build_confirm_details_その他ツールでtool_nameが含まれる(self) -> None:
        text = _build_confirm_details("run_command", {"command": "ls -la"})
        plain = text.plain
        assert "run_command" in plain

    def test_write_fileで21行以上のcontentがトランケートされる(self) -> None:
        long_content = "\n".join([f"line{i}" for i in range(25)])
        text = _build_confirm_details(
            "write_file", {"file_path": "f.txt", "content": long_content}
        )
        plain = text.plain
        assert "省略" in plain

    def test_diff入力で再表示してからy入力で承認される(self) -> None:
        with patch("myagent.cli.display.console") as mock_console:
            mock_console.input.side_effect = ["diff", "y"]
            result = confirm_action(
                "write_file", {"file_path": "test.txt", "content": "hello"}
            )
            assert result is True
            assert mock_console.input.call_count == 2

    def test_無効入力の後n入力で拒否される(self) -> None:
        with patch("myagent.cli.display.console") as mock_console:
            mock_console.input.side_effect = ["xyz", "n"]
            result = confirm_action(
                "write_file", {"file_path": "test.txt", "content": "hello"}
            )
            assert result is False


class TestPrintTokenUsage:
    """print_token_usage 関数のテスト."""

    def test_トークン使用量をコンソールに出力する(self) -> None:
        with patch("myagent.cli.display.console") as mock_console:
            with patch("myagent.llm.cost.estimate_cost_usd", return_value=None):
                print_token_usage(100, 50, 150)
                mock_console.print.assert_called_once()
                call_args = mock_console.print.call_args[0][0]
                assert "100" in call_args
                assert "50" in call_args
                assert "150" in call_args

    def test_コストが計算できる場合はUSD表示を含む(self) -> None:
        with patch("myagent.cli.display.console") as mock_console:
            with patch("myagent.llm.cost.estimate_cost_usd", return_value=0.000123):
                print_token_usage(100, 50, 150, "gpt-4o-mini")
                call_args = mock_console.print.call_args[0][0]
                assert "$" in call_args
