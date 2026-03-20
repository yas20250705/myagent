"""パスセキュリティのテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from myagent.infra.errors import SecurityError
from myagent.tools.path_security import AllowedDirectories


class TestAllowedDirectories:
    """AllowedDirectories のテスト."""

    def test_project_rootが常に許可リストに含まれる(self, tmp_path: Path) -> None:
        allowed = AllowedDirectories(tmp_path)
        assert allowed.project_root == tmp_path.resolve()
        assert len(allowed.allowed_dirs) == 1

    def test_extra_dirsが許可リストに追加される(self, tmp_path: Path) -> None:
        extra1 = tmp_path / "extra1"
        extra2 = tmp_path / "extra2"
        extra1.mkdir()
        extra2.mkdir()
        allowed = AllowedDirectories(tmp_path, extra_dirs=[extra1, extra2])
        assert len(allowed.allowed_dirs) == 3

    def test_重複するディレクトリが排除される(self, tmp_path: Path) -> None:
        allowed = AllowedDirectories(tmp_path, extra_dirs=[tmp_path])
        assert len(allowed.allowed_dirs) == 1

    def test_validate_pathで許可ディレクトリ内のパスが通る(
        self, tmp_path: Path
    ) -> None:
        test_file = tmp_path / "test.txt"
        test_file.touch()
        allowed = AllowedDirectories(tmp_path)
        result = allowed.validate_path(test_file)
        assert result == test_file.resolve()

    def test_validate_pathで許可ディレクトリ外のパスがSecurityError(
        self, tmp_path: Path
    ) -> None:
        allowed = AllowedDirectories(tmp_path)
        with pytest.raises(SecurityError):
            allowed.validate_path("/etc/passwd")

    def test_validate_pathでextra_dirs内のパスが通る(self, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        extra.mkdir()
        test_file = extra / "test.txt"
        test_file.touch()
        # project_rootとextraは兄弟ではなく、extraはproject_root配下なので
        # 別のtmp_pathを使って独立したケースをテスト
        project = tmp_path / "project"
        project.mkdir()
        allowed = AllowedDirectories(project, extra_dirs=[extra])
        result = allowed.validate_path(test_file)
        assert result == test_file.resolve()

    def test_validate_cwdで許可外のパスがSecurityError(self, tmp_path: Path) -> None:
        allowed = AllowedDirectories(tmp_path)
        with pytest.raises(SecurityError):
            allowed.validate_cwd(Path("/nonexistent_forbidden_dir"))

    def test_is_within_allowedでブール判定できる(self, tmp_path: Path) -> None:
        allowed = AllowedDirectories(tmp_path)
        assert allowed.is_within_allowed(tmp_path / "subdir" / "file.txt") is True
        assert allowed.is_within_allowed("/etc/passwd") is False

    def test_is_within_allowedで許可ディレクトリ自体がTrueになる(
        self, tmp_path: Path
    ) -> None:
        allowed = AllowedDirectories(tmp_path)
        assert allowed.is_within_allowed(tmp_path) is True

    def test_文字列パスでも動作する(self, tmp_path: Path) -> None:
        allowed = AllowedDirectories(tmp_path)
        result = allowed.validate_path(str(tmp_path / "test.txt"))
        assert isinstance(result, Path)

    def test_extra_dirsがNoneでも動作する(self, tmp_path: Path) -> None:
        allowed = AllowedDirectories(tmp_path, extra_dirs=None)
        assert len(allowed.allowed_dirs) == 1
