"""カスタム例外クラス定義."""

from __future__ import annotations


class MyAgentError(Exception):
    """myagent の基底例外クラス."""


class LLMError(MyAgentError):
    """LLM呼び出しに関するエラー."""

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        if cause is not None:
            self.__cause__ = cause


class ToolExecutionError(MyAgentError):
    """ツール実行に関するエラー."""

    def __init__(
        self,
        message: str,
        tool_name: str = "unknown",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        if cause is not None:
            self.__cause__ = cause


class SecurityError(MyAgentError):
    """セキュリティ違反に関するエラー."""


class ConfigError(MyAgentError):
    """設定に関するエラー."""


class MCPConnectionError(MyAgentError):
    """MCPサーバーへの接続に関するエラー."""

    def __init__(
        self,
        message: str,
        server_name: str = "unknown",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.server_name = server_name
        if cause is not None:
            self.__cause__ = cause


class MCPToolError(MyAgentError):
    """MCPツール実行に関するエラー."""

    def __init__(
        self,
        message: str,
        server_name: str = "unknown",
        tool_name: str = "unknown",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.server_name = server_name
        self.tool_name = tool_name
        if cause is not None:
            self.__cause__ = cause


class MCPTimeoutError(MCPToolError):
    """MCPツール実行タイムアウトに関するエラー."""


class OrchestratorError(MyAgentError):
    """オーケストレーター全体のエラー."""


class WorkerError(MyAgentError):
    """個別ワーカーのエラー."""

    def __init__(
        self,
        message: str,
        worker_id: str = "unknown",
        task_id: str = "unknown",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.worker_id = worker_id
        self.task_id = task_id
        if cause is not None:
            self.__cause__ = cause


class CommandNotFoundError(MyAgentError):
    """コマンドが見つからない場合のエラー."""

    def __init__(self, name: str, similar: list[str] | None = None) -> None:
        self.name = name
        self.similar = similar or []
        if self.similar:
            suggestion = "、".join(self.similar)
            message = f"コマンドが見つかりません: /{name}\n類似コマンド: {suggestion}"
        else:
            message = f"コマンドが見つかりません: /{name}"
        super().__init__(message)
