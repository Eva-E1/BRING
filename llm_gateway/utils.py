import tiktoken

def num_tokens_from_string(string: str, model: str = "gpt-3.5-turbo") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(string))

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
