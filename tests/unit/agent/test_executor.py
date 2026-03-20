"""Executorクラスのテスト."""

from __future__ import annotations

from myagent.agent.executor import Executor


class TestExecutorのshould_confirm:
    """Executor.should_confirm のテスト."""

    def test_autonomousレベルでは常にFalseを返す(self) -> None:
        executor = Executor(confirmation_level="autonomous")
        assert (
            executor.should_confirm("write_file", {"path": "foo.py", "content": ""})
            is False
        )
        assert (
            executor.should_confirm(
                "edit_file", {"path": "foo.py", "old_string": "x", "new_string": "y"}
            )
            is False
        )
        assert executor.should_confirm("run_command", {"command": "rm file"}) is False
        assert executor.should_confirm("read_file", {"path": "foo.py"}) is False

    def test_normalレベルでwrite_fileはTrueを返す(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert (
            executor.should_confirm("write_file", {"path": "foo.py", "content": ""})
            is True
        )

    def test_normalレベルでedit_fileはTrueを返す(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert (
            executor.should_confirm(
                "edit_file", {"path": "foo.py", "old_string": "x", "new_string": "y"}
            )
            is True
        )

    def test_normalレベルでrun_commandはTrueを返す(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert executor.should_confirm("run_command", {"command": "ls"}) is True

    def test_normalレベルでgit_commitはTrueを返す(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert executor.should_confirm("git_commit", {"message": "fix"}) is True

    def test_normalレベルでread_fileはFalseを返す(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert executor.should_confirm("read_file", {"path": "foo.py"}) is False

    def test_normalレベルでlist_directoryはFalseを返す(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert executor.should_confirm("list_directory", {"path": "."}) is False

    def test_normalレベルでgrep_searchはFalseを返す(self) -> None:
        executor = Executor(confirmation_level="normal")
        assert executor.should_confirm("grep_search", {"pattern": "foo"}) is False

    def test_strictレベルでwrite_fileはTrueを返す(self) -> None:
        executor = Executor(confirmation_level="strict")
        assert (
            executor.should_confirm("write_file", {"path": "foo.py", "content": ""})
            is True
        )

    def test_strictレベルでread_fileはFalseを返す(self) -> None:
        executor = Executor(confirmation_level="strict")
        assert executor.should_confirm("read_file", {"path": "foo.py"}) is False

    def test_strictレベルでgit_statusはFalseを返す(self) -> None:
        executor = Executor(confirmation_level="strict")
        assert executor.should_confirm("git_status", {}) is False

    def test_strictレベルで未知のツールはTrueを返す(self) -> None:
        executor = Executor(confirmation_level="strict")
        assert executor.should_confirm("unknown_tool", {}) is True

    def test_デフォルトはnormalレベル(self) -> None:
        executor = Executor()
        assert executor.confirmation_level == "normal"
