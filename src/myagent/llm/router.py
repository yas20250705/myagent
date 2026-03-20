"""LLMルーターモジュール.

OpenAI / Gemini プロバイダの統一インターフェースを提供する。
指数バックオフリトライとフォールバック制御を含む。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from myagent.infra.errors import LLMError

if TYPE_CHECKING:
    from myagent.infra.config import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """トークン使用量の追跡."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, prompt: int, completion: int) -> None:
        """トークン使用量を加算する."""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion


@dataclass
class LLMRouter:
    """LLMプロバイダのルーティングとフォールバックを管理する.

    Attributes:
        config: LLM設定。
        token_usage: トークン使用量の累計。
    """

    config: LLMConfig
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    _primary: BaseChatModel | None = field(default=None, init=False, repr=False)
    _fallback: BaseChatModel | None = field(default=None, init=False, repr=False)

    def _create_model(
        self,
        provider: Literal["openai", "gemini"],
        model: str,
    ) -> BaseChatModel:
        """指定プロバイダのChatModelインスタンスを生成する."""
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model,
                temperature=self.config.temperature,
            )
        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model,
                temperature=self.config.temperature,
            )
        msg = f"未対応のプロバイダ: {provider}"
        raise LLMError(msg)

    @property
    def primary(self) -> BaseChatModel:
        """プライマリモデルを取得（遅延初期化）."""
        if self._primary is None:
            self._primary = self._create_model(
                self.config.provider,
                self.config.model,
            )
        return self._primary

    @property
    def fallback(self) -> BaseChatModel | None:
        """フォールバックモデルを取得（遅延初期化）."""
        if (
            self._fallback is None
            and self.config.fallback_provider
            and self.config.fallback_model
        ):
            self._fallback = self._create_model(
                self.config.fallback_provider,
                self.config.fallback_model,
            )
        return self._fallback

    async def _invoke_with_retry(
        self,
        model: BaseChatModel,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> BaseMessage:
        """指数バックオフリトライ付きでモデルを呼び出す."""
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                response = await model.ainvoke(messages, **kwargs)
                self._track_usage(response)
                return response
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        "LLM呼び出し失敗 (試行 %d/%d): %s, %d秒後にリトライ",
                        attempt + 1,
                        self.config.max_retries,
                        e,
                        wait,
                    )
                    await asyncio.sleep(wait)
        msg = f"LLM呼び出しが{self.config.max_retries}回失敗しました"
        raise LLMError(msg) from last_error

    def _track_usage(self, response: BaseMessage) -> None:
        """レスポンスからトークン使用量を追跡する."""
        usage = getattr(response, "usage_metadata", None)
        if usage and isinstance(usage, dict):
            self.token_usage.add(
                prompt=usage.get("input_tokens", 0),
                completion=usage.get("output_tokens", 0),
            )

    async def invoke(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> BaseMessage:
        """LLMを呼び出す。失敗時はフォールバックを試行する.

        Args:
            messages: 送信するメッセージ一覧。
            **kwargs: モデルへの追加パラメータ。

        Returns:
            LLMからのレスポンス。

        Raises:
            LLMError: プライマリとフォールバックの両方が失敗した場合。
        """
        try:
            return await self._invoke_with_retry(self.primary, messages, **kwargs)
        except LLMError:
            if self.fallback is None:
                raise
            logger.warning("プライマリモデル失敗、フォールバックに切り替え")
            try:
                return await self._invoke_with_retry(self.fallback, messages, **kwargs)
            except LLMError as e:
                msg = "プライマリ・フォールバック両方のモデルが失敗しました"
                raise LLMError(msg) from e

    async def stream(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """LLMをストリーミングで呼び出す.

        Args:
            messages: 送信するメッセージ一覧。
            **kwargs: モデルへの追加パラメータ。

        Yields:
            ストリーミングされたテキストチャンク。

        Raises:
            LLMError: ストリーミング呼び出しに失敗した場合。
        """
        model = self.primary
        try:
            async for chunk in model.astream(messages, **kwargs):
                if hasattr(chunk, "content") and isinstance(chunk.content, str):
                    yield chunk.content
        except Exception as e:
            if self.fallback is None:
                msg = f"ストリーミング呼び出しに失敗しました: {e}"
                raise LLMError(msg) from e
            logger.warning("プライマリストリーム失敗、フォールバックに切り替え")
            try:
                async for chunk in self.fallback.astream(messages, **kwargs):
                    if hasattr(chunk, "content") and isinstance(chunk.content, str):
                        yield chunk.content
            except Exception as fallback_e:
                msg = f"フォールバックストリーミングも失敗しました: {fallback_e}"
                raise LLMError(msg) from fallback_e

    def get_model_for_bind_tools(self) -> BaseChatModel:
        """ツールバインド用のモデルインスタンスを返す."""
        return self.primary
