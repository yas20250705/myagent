"""APIコスト推定モジュールのテスト."""

from __future__ import annotations

from myagent.llm.cost import estimate_cost_usd


class TestEstimateCostUsd:
    """estimate_cost_usd 関数のテスト."""

    def test_既知モデルgpt4o_miniで正しいコストを計算する(self) -> None:
        # gpt-4o-mini: input=$0.15/1M, output=$0.60/1M
        cost = estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000)
        assert cost is not None
        assert abs(cost - 0.75) < 1e-9

    def test_既知モデルgpt4oで正しいコストを計算する(self) -> None:
        # gpt-4o: input=$2.50/1M, output=$10.00/1M
        cost = estimate_cost_usd("gpt-4o", 1_000_000, 1_000_000)
        assert cost is not None
        assert abs(cost - 12.50) < 1e-9

    def test_部分一致でフォールバックする(self) -> None:
        # "gpt-4o-mini-2024" は "gpt-4o-mini" に部分一致
        cost = estimate_cost_usd("gpt-4o-mini-2024", 1_000_000, 0)
        assert cost is not None
        assert abs(cost - 0.15) < 1e-9

    def test_未知モデルでNoneを返す(self) -> None:
        cost = estimate_cost_usd("unknown-model-xyz", 1000, 1000)
        assert cost is None

    def test_トークン数0のときコスト0を返す(self) -> None:
        cost = estimate_cost_usd("gpt-4o-mini", 0, 0)
        assert cost is not None
        assert cost == 0.0

    def test_プロンプトトークンのみのコストを計算する(self) -> None:
        cost = estimate_cost_usd("gpt-4o-mini", 1_000_000, 0)
        assert cost is not None
        assert abs(cost - 0.15) < 1e-9

    def test_補完トークンのみのコストを計算する(self) -> None:
        cost = estimate_cost_usd("gpt-4o-mini", 0, 1_000_000)
        assert cost is not None
        assert abs(cost - 0.60) < 1e-9

    def test_gemini_2_5_flashのコストを計算する(self) -> None:
        # gemini-2.5-flash: input=$0.075/1M, output=$0.30/1M
        cost = estimate_cost_usd("gemini-2.5-flash", 1_000_000, 1_000_000)
        assert cost is not None
        assert abs(cost - 0.375) < 1e-9
