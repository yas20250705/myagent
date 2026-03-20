"""共有状態モジュール.

ツール間で作業ディレクトリを共有するための可変状態クラスを提供する。
"""

from __future__ import annotations

from pathlib import Path


class WorkingDirectory:
    """ツール間で共有される作業ディレクトリ状態.

    シェルツールと ファイルツールが同じインスタンスを参照することで、
    cd コマンド後の相対パス解決が正しく機能する。
    """

    def __init__(self, initial: Path) -> None:
        self._path = initial.resolve()

    @property
    def path(self) -> Path:
        """現在の作業ディレクトリを返す."""
        return self._path

    @path.setter
    def path(self, value: Path) -> None:
        """作業ディレクトリを更新する."""
        self._path = value.resolve()

    def resolve_path(self, path_str: str) -> Path:
        """パス文字列を現在の作業ディレクトリ基準で解決する.

        絶対パスはそのまま resolve()、相対パスは cwd からの相対として解決する。
        """
        p = Path(path_str)
        if p.is_absolute():
            return p.resolve()
        return (self._path / p).resolve()
