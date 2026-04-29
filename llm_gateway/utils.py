from functools import lru_cache

import tiktoken


@lru_cache(maxsize=32)
def _encoding_for_model(model: str):
    normalized_model = model or "gpt-3.5-turbo"
    try:
        return tiktoken.encoding_for_model(normalized_model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def num_tokens_from_string(string: str, model: str = "gpt-3.5-turbo") -> int:
    return len(_encoding_for_model(model).encode(string))

def cost_estimate(prompt: str, response: str, model: str) -> float:
    # Pricing per 1k tokens (input, output)
    pricing = {
        "gpt-3.5-turbo": (0.0015, 0.002),
        "gpt-4": (0.03, 0.06),
        # extend as needed
    }
    input_price, output_price = pricing.get(model, (0.0, 0.0))
    input_tokens = num_tokens_from_string(prompt, model)
    output_tokens = num_tokens_from_string(response, model)
    return (input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price
