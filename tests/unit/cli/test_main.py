"""エントリーポイントのテスト."""

from __future__ import annotations

from unittest.mock import patch


class TestMain:
    """main モジュールのテスト."""

    def test_mainを呼び出せる(self) -> None:
        with patch("myagent.cli.commands.cli") as mock_cli:
            from myagent.main import main
            main()
            mock_cli.assert_called_once_with(obj={})
