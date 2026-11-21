"""Model pricing table (USD per 1M tokens) for cost tracking.

Update this table when Azure pricing changes; every LLM call computes its
cost from here and records it in the llm_usage table.
"""

PRICING_PER_1M = {
    # model: (input, output)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-large": (0.13, 0.0),
    "text-embedding-3-small": (0.02, 0.0),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_price, output_price = PRICING_PER_1M.get(model, (0.0, 0.0))
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
