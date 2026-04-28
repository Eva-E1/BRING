import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Type

from .cache import AsyncTTLCache
from .config import AnyLLMConfig
from .exceptions import (
    ConfigurationError,
    EmptyResponseError,
    LLMGatewayError,
    ProviderNotAvailableError,
    RateLimitError,
)
from .retry import build_retry_decorator
from .settings import GatewaySettings
from .utils import cost_estimate

logger = logging.getLogger(__name__)

_INSTRUCTOR_SUPPORTED_PROVIDERS = {"openai", "azure", "anthropic", "cohere"}


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str = ""
    provider: str = ""
    tokens_used: int = 0
    cost: float = 0.0


class LLMClient:
    """
    Single-entry LLM gateway.

    Plain text uses an OpenAI-style client (supports any OpenAI-compatible endpoint).
    Structured output uses Instructor with the same provider/model configuration and
    falls back to schema-guided prompting when Instructor is unavailable.
    """

    def __init__(
        self,
        config: Optional[AnyLLMConfig] = None,
        cache: Optional[AsyncTTLCache] = None,
        enable_cache: bool = True,
        max_retries: int = 3,
    ):
        self.config = config or AnyLLMConfig.from_settings()
        self._cache = cache or AsyncTTLCache()
        self._enable_cache = enable_cache
        self._retry = build_retry_decorator(max_retries)
        self._instructor_client: Any = None
        self._plain_client: Any = None
        self._instructor_lock = asyncio.Lock()
        self._plain_lock = asyncio.Lock()

    @classmethod
    def from_settings(
        cls,
        settings: Optional[GatewaySettings] = None,
        *,
        settings_file: Optional[str | Path] = None,
        cache: Optional[AsyncTTLCache] = None,
        enable_cache: bool = True,
        max_retries: int = 3,
        **config_overrides: Any,
    ) -> "LLMClient":
        config = AnyLLMConfig.from_settings(
            settings=settings,
            settings_file=settings_file,
            **config_overrides,
        )
        return cls(
            config=config,
            cache=cache,
            enable_cache=enable_cache,
            max_retries=max_retries,
        )

    async def _get_plain_client(self) -> Any:
        """Return an AsyncOpenAI (or AsyncAzureOpenAI) client for plain text calls."""
        if self._plain_client is not None:
            return self._plain_client

        async with self._plain_lock:
            if self._plain_client is not None:
                return self._plain_client

            provider = self.config.runtime_provider
            provider_settings = self.config.provider_settings
            client_kwargs = provider_settings.build_client_kwargs()

            if provider in {"openai", "azure"}:
                import openai

                if provider == "azure":
                    self._plain_client = openai.AsyncAzureOpenAI(
                        api_key=provider_settings.api_key,
                        **client_kwargs,
                    )
                else:
                    self._plain_client = openai.AsyncOpenAI(
                        api_key=provider_settings.api_key,
                        **client_kwargs,
                    )
            elif provider == "anthropic":
                import openai

                logger.warning(
                    "Provider '%s' is not OpenAI-compatible; attempting to use AsyncOpenAI anyway.",
                    provider,
                )
                self._plain_client = openai.AsyncOpenAI(
                    api_key=provider_settings.api_key,
                    **client_kwargs,
                )
            else:
                import openai

                self._plain_client = openai.AsyncOpenAI(
                    api_key=provider_settings.api_key,
                    **client_kwargs,
                )
            return self._plain_client

    async def _text_call(self, prompt: str) -> str:
        @self._retry
        async def _attempt() -> str:
            try:
                client = await self._get_plain_client()
                resp = await client.chat.completions.create(
                    model=self.config.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
                content = resp.choices[0].message.content
                if content is None:
                    raise EmptyResponseError("LLM returned empty content")
                return content
            except Exception as exc:
                err = str(exc).lower()
                if "rate limit" in err:
                    raise RateLimitError(f"Rate limited by {self.config.provider}") from exc
                if "not available" in err or "service unavailable" in err:
                    raise ProviderNotAvailableError(f"{self.config.provider} unavailable") from exc
                if "invalid" in err or "auth" in err:
                    raise ConfigurationError(f"Config error with {self.config.provider}") from exc
                raise LLMGatewayError(f"Provider call failed: {exc}") from exc

        return await _attempt()

    def _supports_instructor(self) -> bool:
        return self.config.runtime_provider in _INSTRUCTOR_SUPPORTED_PROVIDERS

    @staticmethod
    def _is_instructor_response_model(response_model: Any) -> bool:
        return isinstance(response_model, type) and (
            hasattr(response_model, "model_json_schema") or hasattr(response_model, "schema")
        )

    async def _get_instructor_client(self) -> Any:
        if self._instructor_client is not None:
            return self._instructor_client

        if not self._supports_instructor():
            raise ConfigurationError(
                f"Provider '{self.config.provider}' does not support Instructor structured generation."
            )

        async with self._instructor_lock:
            if self._instructor_client is not None:
                return self._instructor_client

            provider = self.config.runtime_provider
            provider_settings = self.config.provider_settings
            client_kwargs = provider_settings.build_client_kwargs()
            request_kwargs = dict(self.config.provider_settings.request_kwargs)
            if provider in {"openai", "azure"}:
                import instructor
                import openai

                if provider == "azure":
                    client = openai.AsyncAzureOpenAI(
                        api_key=provider_settings.api_key,
                        **client_kwargs,
                    )
                else:
                    client = openai.AsyncOpenAI(
                        api_key=provider_settings.api_key,
                        **client_kwargs,
                    )
                self._instructor_client = instructor.from_openai(client)
            elif provider == "anthropic":
                import anthropic
                import instructor

                client = anthropic.AsyncAnthropic(
                    api_key=provider_settings.api_key,
                    **client_kwargs,
                )
                self._instructor_client = instructor.from_anthropic(client)
            elif provider == "cohere":
                import cohere
                import instructor

                client = cohere.AsyncClient(
                    api_key=provider_settings.api_key,
                    **client_kwargs,
                )
                self._instructor_client = instructor.from_cohere(client)
            else:
                raise ConfigurationError(
                    f"Provider '{provider}' is not supported for structured generation."
                )

            if request_kwargs:
                logger.debug(
                    "Instructor request kwargs are configured and will be merged per call: %s",
                    sorted(request_kwargs),
                )
            return self._instructor_client

    @staticmethod
    def _schema_hash(response_model: Type[Any]) -> str:
        if hasattr(response_model, "model_json_schema"):
            schema = response_model.model_json_schema()
        elif hasattr(response_model, "schema"):
            schema = response_model.schema()
        else:
            schema = str(response_model)
        return hashlib.md5(
            json.dumps(schema, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _schema_description(response_model: Type[Any]) -> str:
        if hasattr(response_model, "model_json_schema"):
            schema = response_model.model_json_schema()
        elif hasattr(response_model, "schema"):
            schema = response_model.schema()
        else:
            schema = str(response_model)
        return json.dumps(schema, indent=2, sort_keys=True, default=str)

    async def _structured_call(self, prompt: str, response_model: Type[Any]) -> str:
        client = await self._get_instructor_client()
        request_kwargs = dict(self.config.provider_settings.request_kwargs)
        messages = [{"role": "user", "content": prompt}]

        try:
            result = await client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                response_model=response_model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                **request_kwargs,
            )
        except Exception as exc:
            err = str(exc).lower()
            if "rate limit" in err:
                raise RateLimitError(f"Rate limited by {self.config.provider}") from exc
            if "not available" in err or "service unavailable" in err:
                raise ProviderNotAvailableError(f"{self.config.provider} unavailable") from exc
            if "invalid" in err or "auth" in err:
                raise ConfigurationError(f"Config error with {self.config.provider}") from exc
            raise LLMGatewayError(f"Instructor structured call failed: {exc}") from exc

        if hasattr(result, "model_dump_json"):
            return result.model_dump_json()
        if hasattr(result, "json"):
            return result.json()
        return str(result)

    async def generate(
        self,
        prompt: str,
        response_model: Optional[Type[Any]] = None,
    ) -> LLMResponse:
        schema_hash = self._schema_hash(response_model) if response_model is not None else ""
        cache_key = (
            f"{self.config.model_id}:{prompt}:{schema_hash}"
            if self._enable_cache
            else None
        )

        if cache_key is not None:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return LLMResponse(
                    text=str(cached),
                    model=self.config.model,
                    provider="cache",
                )

        use_instructor = (
            response_model is not None
            and self._supports_instructor()
            and self._is_instructor_response_model(response_model)
        )
        final_prompt = prompt
        effective_response_model = response_model

        if response_model is not None and not use_instructor:
            logger.warning(
                "Falling back to schema-guided prompting for provider=%s response_model=%s.",
                self.config.provider,
                getattr(response_model, "__name__", type(response_model).__name__),
            )
            final_prompt = (
                f"{prompt}\n\nPlease respond with JSON that matches this schema:\n"
                f"{self._schema_description(response_model)}"
            )
            effective_response_model = None

        if effective_response_model is None:
            raw_text = await self._text_call(final_prompt)
        else:
            raw_text = await self._structured_call(final_prompt, effective_response_model)

        if not raw_text or not raw_text.strip():
            raise EmptyResponseError("Empty response")

        tokens_used = 0
        cost = 0.0
        if effective_response_model is None:
            try:
                tokens_used = len(raw_text.split())
                cost = cost_estimate(final_prompt, raw_text, self.config.model)
            except Exception:
                logger.debug("Unable to estimate token usage for %s", self.config.model_id, exc_info=True)

        if cache_key is not None:
            await self._cache.set(cache_key, raw_text)

        return LLMResponse(
            text=raw_text,
            model=self.config.model,
            provider=self.config.provider,
            tokens_used=tokens_used,
            cost=cost,
        )

    def generate_sync(
        self,
        prompt: str,
        response_model: Optional[Type[Any]] = None,
    ) -> LLMResponse:
        return asyncio.run(self.generate(prompt, response_model=response_model))
