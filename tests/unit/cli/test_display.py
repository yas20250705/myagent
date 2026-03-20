"""CLIディスプレイモジュールのテスト."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from myagent.agent.events import AgentEvent
from myagent.cli.display import _start_spinner, _stop_spinner, handle_event


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
