"""APIコスト推定モジュール.

モデル名とトークン数からAPIコスト（USD）を推定する。
"""

from __future__ import annotations

# USD per 1,000,000 tokens
_PRICING_USD_PER_1M: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-5-nano": {"input": 0.15, "output": 0.60},
    # Google Gemini
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
}


def _get_pricing(model: str) -> dict[str, float] | None:
    """モデル名から料金テーブルを取得する.

    完全一致を優先し、失敗した場合は部分一致を試みる。

    Args:
        model: モデル名。

    Returns:
        input/output キーを持つ料金辞書。見つからない場合はNone。
    """
    if model in _PRICING_USD_PER_1M:
        return _PRICING_USD_PER_1M[model]

    model_lower = model.lower()
    best_key: str | None = None
    for key in _PRICING_USD_PER_1M:
        if key in model_lower or model_lower in key:
            if best_key is None or len(key) > len(best_key):
                best_key = key

    if best_key is not None:
        return _PRICING_USD_PER_1M[best_key]

    return None


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    """APIコストを推定する（USD）.

    Args:
        model: モデル名（例: "gpt-4o-mini"）。
        prompt_tokens: プロンプトのトークン数。
        completion_tokens: 補完のトークン数。

    Returns:
        推定コスト（USD）。モデルが未知の場合はNone。
    """
    pricing = _get_pricing(model)
    if pricing is None:
        return None

    input_cost = prompt_tokens * pricing["input"] / 1_000_000
    output_cost = completion_tokens * pricing["output"] / 1_000_000
    return input_cost + output_cost
