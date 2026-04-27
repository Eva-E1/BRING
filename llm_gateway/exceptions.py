class LLMGatewayError(Exception):
    """Base exception for all gateway errors."""

class ConfigurationError(LLMGatewayError):
    """Invalid provider/model configuration."""

class ProviderNotAvailableError(LLMGatewayError):
    """Provider is temporarily unavailable."""

class RateLimitError(LLMGatewayError):
    """Provider returned a rate‑limit response."""

class EmptyResponseError(LLMGatewayError):
    """LLM returned an empty or unusable response."""
