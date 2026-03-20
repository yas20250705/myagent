"""LLMルーターのテスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myagent.infra.config import LLMConfig
from myagent.infra.errors import LLMError
from myagent.llm.router import LLMRouter, TokenUsage


class TestTokenUsage:
    """TokenUsage のテスト."""

    def test_初期値はすべてゼロ(self) -> None:
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_addで使用量を加算できる(self) -> None:
        usage = TokenUsage()
        usage.add(100, 50)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_複数回addで累積される(self) -> None:
        usage = TokenUsage()
        usage.add(100, 50)
        usage.add(200, 100)
        assert usage.total_tokens == 450


class TestLLMRouterの初期化:
    """LLMRouter の初期化テスト."""

    def test_デフォルト設定で初期化できる(self) -> None:
        config = LLMConfig()
        router = LLMRouter(config=config)
        assert router.config.provider == "openai"

    def test_token_usageが初期化される(self) -> None:
        config = LLMConfig()
        router = LLMRouter(config=config)
        assert router.token_usage.total_tokens == 0


class TestLLMRouterのinvoke:
    """LLMRouter.invoke のテスト."""

    @pytest.mark.asyncio
    async def test_プライマリモデルで正常にinvokeできる(self) -> None:
        config = LLMConfig()
        router = LLMRouter(config=config)

        mock_response = MagicMock()
        mock_response.content = "テスト回答"
        mock_response.usage_metadata = None

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        router._primary = mock_model

        from langchain_core.messages import HumanMessage

        result = await router.invoke([HumanMessage(content="テスト")])
        assert result.content == "テスト回答"

    @pytest.mark.asyncio
    async def test_プライマリ失敗時にフォールバックに切り替わる(self) -> None:
        config = LLMConfig(max_retries=1)
        router = LLMRouter(config=config)

        mock_primary = AsyncMock()
        mock_primary.ainvoke = AsyncMock(side_effect=Exception("プライマリ失敗"))
        router._primary = mock_primary

        mock_fallback_response = MagicMock()
        mock_fallback_response.content = "フォールバック回答"
        mock_fallback_response.usage_metadata = None

        mock_fallback = AsyncMock()
        mock_fallback.ainvoke = AsyncMock(return_value=mock_fallback_response)
        router._fallback = mock_fallback

        from langchain_core.messages import HumanMessage

        result = await router.invoke([HumanMessage(content="テスト")])
        assert result.content == "フォールバック回答"

    @pytest.mark.asyncio
    async def test_両方失敗時にLLMErrorが発生する(self) -> None:
        config = LLMConfig(max_retries=1)
        router = LLMRouter(config=config)

        mock_primary = AsyncMock()
        mock_primary.ainvoke = AsyncMock(side_effect=Exception("プライマリ失敗"))
        router._primary = mock_primary

        mock_fallback = AsyncMock()
        mock_fallback.ainvoke = AsyncMock(side_effect=Exception("フォールバック失敗"))
        router._fallback = mock_fallback

        from langchain_core.messages import HumanMessage

        with pytest.raises(LLMError):
            await router.invoke([HumanMessage(content="テスト")])

    @pytest.mark.asyncio
    async def test_usage_metadataがあればトークン使用量が追跡される(self) -> None:
        config = LLMConfig()
        router = LLMRouter(config=config)

        mock_response = MagicMock()
        mock_response.content = "回答"
        mock_response.usage_metadata = {"input_tokens": 10, "output_tokens": 20}

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        router._primary = mock_model

        from langchain_core.messages import HumanMessage

        await router.invoke([HumanMessage(content="テスト")])
        assert router.token_usage.prompt_tokens == 10
        assert router.token_usage.completion_tokens == 20
        assert router.token_usage.total_tokens == 30


class TestLLMRouterのstream:
    """LLMRouter.stream のテスト."""

    @pytest.mark.asyncio
    async def test_ストリーミングトークンを取得できる(self) -> None:
        config = LLMConfig()
        router = LLMRouter(config=config)

        async def mock_astream(*args, **kwargs):  # type: ignore[no-untyped-def]
            chunks = ["hello", " ", "world"]
            for chunk in chunks:
                mock_chunk = MagicMock()
                mock_chunk.content = chunk
                yield mock_chunk

        mock_model = MagicMock()
        mock_model.astream = mock_astream
        router._primary = mock_model

        from langchain_core.messages import HumanMessage

        tokens: list[str] = []
        async for token in router.stream([HumanMessage(content="テスト")]):
            tokens.append(token)
        assert "".join(tokens) == "hello world"

    @pytest.mark.asyncio
    async def test_ストリーム失敗時にフォールバックを使用する(self) -> None:
        config = LLMConfig()
        router = LLMRouter(config=config)

        async def failing_astream(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise Exception("ストリームエラー")
            yield  # generator化

        async def fallback_astream(*args, **kwargs):  # type: ignore[no-untyped-def]
            mock_chunk = MagicMock()
            mock_chunk.content = "フォールバック"
            yield mock_chunk

        mock_primary = MagicMock()
        mock_primary.astream = failing_astream
        router._primary = mock_primary

        mock_fallback = MagicMock()
        mock_fallback.astream = fallback_astream
        router._fallback = mock_fallback

        from langchain_core.messages import HumanMessage

        tokens: list[str] = []
        async for token in router.stream([HumanMessage(content="テスト")]):
            tokens.append(token)
        assert tokens == ["フォールバック"]
