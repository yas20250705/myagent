"""エントリーポイント.

CLIアプリケーションの起動とDI組み立てを行う。
"""

from __future__ import annotations

from myagent.cli.commands import cli


def main() -> None:
    """myagent CLIのメインエントリーポイント."""
    cli(obj={})


if __name__ == "__main__":
    main()
