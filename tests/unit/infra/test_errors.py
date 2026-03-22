"""カスタム例外クラスのテスト."""

import pytest

from myagent.infra.errors import (
    ConfigError,
    LLMError,
    MyAgentError,
    OrchestratorError,
    SecurityError,
    ToolExecutionError,
    WorkerError,
)


class TestMyAgentErrorの継承関係:
    """例外クラスの継承関係を検証する."""

    def test_MyAgentErrorはExceptionを継承する(self) -> None:
        assert issubclass(MyAgentError, Exception)

    def test_LLMErrorはMyAgentErrorを継承する(self) -> None:
        assert issubclass(LLMError, MyAgentError)

    def test_ToolExecutionErrorはMyAgentErrorを継承する(self) -> None:
        assert issubclass(ToolExecutionError, MyAgentError)

    def test_SecurityErrorはMyAgentErrorを継承する(self) -> None:
        assert issubclass(SecurityError, MyAgentError)

    def test_ConfigErrorはMyAgentErrorを継承する(self) -> None:
        assert issubclass(ConfigError, MyAgentError)

    def test_OrchestratorErrorはMyAgentErrorを継承する(self) -> None:
        assert issubclass(OrchestratorError, MyAgentError)

    def test_WorkerErrorはMyAgentErrorを継承する(self) -> None:
        assert issubclass(WorkerError, MyAgentError)


class TestMyAgentErrorのキャッチ:
    """基底クラスで全例外をキャッチできることを検証する."""

    def test_LLMErrorをMyAgentErrorでキャッチできる(self) -> None:
        with pytest.raises(MyAgentError):
            raise LLMError("LLMエラー")

    def test_ToolExecutionErrorをMyAgentErrorでキャッチできる(self) -> None:
        with pytest.raises(MyAgentError):
            raise ToolExecutionError("ツールエラー")

    def test_SecurityErrorをMyAgentErrorでキャッチできる(self) -> None:
        with pytest.raises(MyAgentError):
            raise SecurityError("セキュリティエラー")

    def test_ConfigErrorをMyAgentErrorでキャッチできる(self) -> None:
        with pytest.raises(MyAgentError):
            raise ConfigError("設定エラー")


class TestMyAgentErrorのメッセージ:
    """例外メッセージが正しく保持されることを検証する."""

    def test_メッセージが保持される(self) -> None:
        error = LLMError("テストメッセージ")
        assert str(error) == "テストメッセージ"

    def test_空のメッセージでも生成できる(self) -> None:
        error = MyAgentError()
        assert str(error) == ""


class TestWorkerErrorの属性:
    """WorkerError の属性を検証する."""

    def test_worker_idとtask_idが保持される(self) -> None:
        error = WorkerError("失敗", worker_id="w1", task_id="t1")
        assert error.worker_id == "w1"
        assert error.task_id == "t1"
        assert str(error) == "失敗"

    def test_デフォルト値はunknown(self) -> None:
        error = WorkerError("エラー")
        assert error.worker_id == "unknown"
        assert error.task_id == "unknown"

    def test_cause設定(self) -> None:
        cause = ValueError("原因")
        error = WorkerError("失敗", cause=cause)
        assert error.__cause__ is cause
