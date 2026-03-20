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
