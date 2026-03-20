"""パスセキュリティモジュール.

許可ディレクトリの管理とパスバリデーションを提供する。
"""

from __future__ import annotations

import os
from pathlib import Path

from myagent.infra.errors import SecurityError

_SEP = os.sep


class AllowedDirectories:
    """許可ディレクトリの管理とパスバリデーションを行うクラス.

    project_root は常に許可リストの先頭に含まれる。
    全パスは resolve() でシンボリックリンクを解決して管理される。
    """

    def __init__(
        self, project_root: Path, extra_dirs: list[Path] | None = None
    ) -> None:
        root = project_root.resolve()
        seen = {root}
        self._allowed: list[Path] = [root]
        for d in extra_dirs or []:
            resolved = d.resolve()
            if resolved not in seen:
                seen.add(resolved)
                self._allowed.append(resolved)

    def validate_path(self, target: Path | str) -> Path:
        """パスがいずれかの許可ディレクトリ内か検証する.

        Args:
            target: 検証対象のパス。

        Returns:
            解決済みの絶対パス。

        Raises:
            SecurityError: 許可ディレクトリ外へのアクセスの場合。
        """
        resolved = Path(target).resolve()
        if not self.is_within_allowed(resolved):
            msg = f"許可ディレクトリ外へのアクセスは禁止されています: {target}"
            raise SecurityError(msg)
        return resolved

    def validate_cwd(self, cwd: Path) -> None:
        """cwdが許可ディレクトリ内か検証する.

        Args:
            cwd: 検証対象の作業ディレクトリ。

        Raises:
            SecurityError: 許可ディレクトリ外の場合。
        """
        self.validate_path(cwd)

    def is_within_allowed(self, target: Path | str) -> bool:
        """パスがいずれかの許可ディレクトリ内にあるかブール判定する."""
        resolved = Path(target).resolve()
        resolved_str = str(resolved)
        for allowed in self._allowed:
            allowed_str = str(allowed)
            if resolved_str == allowed_str or resolved_str.startswith(
                allowed_str + _SEP
            ):
                return True
        return False

    @property
    def project_root(self) -> Path:
        """プロジェクトルート（先頭要素）を返す."""
        return self._allowed[0]

    @property
    def allowed_dirs(self) -> list[Path]:
        """許可ディレクトリの一覧を返す."""
        return list(self._allowed)
