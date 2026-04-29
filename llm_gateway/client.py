import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Optional, Type
from urllib.parse import urlparse

from .cache import AsyncTTLCache, default_cache_dir
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
_OFFICIAL_OPENAI_HOSTS = {"api.openai.com"}
_TOOL_FRAGILE_MODEL_TOKENS = (
    "gemma",
    "llama",
    "mistral",
    "mixtral",
    "qwen",
    "deepseek",
    "phi",
    "yi-",
    "rwkv",
    "vicuna",
    "alpaca",
)


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str = ""
    provider: str = ""
    tokens_used: int = 0
    cost: float = 0.0


@dataclass(slots=True)
class ProviderRuntimeMetrics:
    current_parallelism: int
    max_parallelism: int
    in_flight: int
    successes: int
    failures: int
    rate_limits: int
    ewma_latency: float | None = None


@dataclass(slots=True)
class CalibrationProbeResult:
    level: int
    successes: int
    total: int
    elapsed: float

    @property
    def per_request_latency(self) -> float:
        return self.elapsed / max(1, self.total)

    @property
    def succeeded(self) -> bool:
        return self.successes == self.total


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
        self._cache = cache or AsyncTTLCache(
            ttl=7 * 24 * 3600,
            maxsize=4096,
            persist_dir=default_cache_dir(),
        )
        self._enable_cache = enable_cache
        self._retry = build_retry_decorator(max_retries)
        self._instructor_client: Any = None
        self._plain_client: Any = None
        self._instructor_lock = asyncio.Lock()
        self._plain_lock = asyncio.Lock()
        self._provider_settings = self.config.provider_settings
        self._client_kwargs = self._provider_settings.build_client_kwargs()
        if self.config.request_timeout_seconds and "timeout" not in self._client_kwargs:
            self._client_kwargs["timeout"] = self.config.request_timeout_seconds
        self._request_kwargs = {
            key: value for key, value in self._provider_settings.request_kwargs.items() if value is not None
        }
        self._runtime_provider = self.config.runtime_provider
        self._bypass_instructor = self._compute_should_bypass_instructor()
        self._parallelism_limit = 1
        self._parallelism_min = 1
        self._parallelism_max = 8
        self._parallelism_in_flight = 0
        self._parallelism_success_streak = 0
        self._parallelism_successes = 0
        self._parallelism_failures = 0
        self._parallelism_rate_limits = 0
        self._parallelism_ewma_latency: float | None = None
        self._parallelism_condition = asyncio.Condition()
        self._inflight_cache: dict[str, asyncio.Future[LLMResponse]] = {}
        self._inflight_cache_lock = asyncio.Lock()
        self.configure_parallelism(
            initial=self.config.startup_parallelism,
            maximum=max(self.config.startup_parallelism, self.config.startup_parallelism_max),
        )

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

            provider = self._runtime_provider
            provider_settings = self._provider_settings
            client_kwargs = self._client_kwargs

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

    def _build_chat_payload(self, prompt: str, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        payload.update(self._request_kwargs)
        payload.update(extra)
        return {key: value for key, value in payload.items() if value is not None}

    @staticmethod
    def _classify_provider_error(exc: Exception, provider: str, *, structured: bool = False) -> Exception:
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return RateLimitError(f"Rate limited by {provider}")
        if status_code in {401, 403}:
            return ConfigurationError(f"Config error with {provider}")
        if status_code in {408, 409, 500, 502, 503, 504, 529}:
            return ProviderNotAvailableError(f"{provider} unavailable")

        err = str(exc).lower()
        if any(token in err for token in ("rate limit", "too many requests", "quota")):
            return RateLimitError(f"Rate limited by {provider}")
        if any(token in err for token in ("not available", "service unavailable", "overloaded", "temporarily unavailable")):
            return ProviderNotAvailableError(f"{provider} unavailable")
        if any(token in err for token in ("invalid", "auth", "unauthorized", "forbidden", "api key")):
            return ConfigurationError(f"Config error with {provider}")

        prefix = "Instructor structured call failed" if structured else "Provider call failed"
        return LLMGatewayError(f"{prefix}: {exc}")

    async def _text_call(self, prompt: str) -> str:
        @self._retry
        async def _attempt() -> str:
            try:
                client = await self._get_plain_client()
                resp = await client.chat.completions.create(**self._build_chat_payload(prompt))
                content = resp.choices[0].message.content
                if content is None:
                    raise EmptyResponseError("LLM returned empty content")
                return content
            except Exception as exc:
                raise self._classify_provider_error(exc, self.config.provider) from exc

        return await _attempt()

    def _supports_instructor(self) -> bool:
        return self._runtime_provider in _INSTRUCTOR_SUPPORTED_PROVIDERS

    @property
    def recommended_parallelism(self) -> int:
        return self._parallelism_limit

    def runtime_metrics(self) -> ProviderRuntimeMetrics:
        return ProviderRuntimeMetrics(
            current_parallelism=self._parallelism_limit,
            max_parallelism=self._parallelism_max,
            in_flight=self._parallelism_in_flight,
            successes=self._parallelism_successes,
            failures=self._parallelism_failures,
            rate_limits=self._parallelism_rate_limits,
            ewma_latency=self._parallelism_ewma_latency,
        )

    def configure_parallelism(
        self,
        *,
        initial: int | None = None,
        minimum: int = 1,
        maximum: int = 8,
    ) -> None:
        maximum = max(minimum, maximum)
        self._parallelism_min = max(1, minimum)
        self._parallelism_max = maximum
        if initial is None:
            initial = min(self._parallelism_limit, self._parallelism_max)
        self._parallelism_limit = max(self._parallelism_min, min(initial, self._parallelism_max))

    async def _acquire_parallelism_slot(self) -> None:
        async with self._parallelism_condition:
            while self._parallelism_in_flight >= self._parallelism_limit:
                await self._parallelism_condition.wait()
            self._parallelism_in_flight += 1

    async def _release_parallelism_slot(self, *, latency: float, error: Exception | None = None) -> None:
        async with self._parallelism_condition:
            self._parallelism_in_flight = max(0, self._parallelism_in_flight - 1)
            self._update_parallelism_state(latency=latency, error=error)
            self._parallelism_condition.notify_all()

    def _update_parallelism_state(self, *, latency: float, error: Exception | None = None) -> None:
        if self._parallelism_ewma_latency is None:
            self._parallelism_ewma_latency = latency
        else:
            self._parallelism_ewma_latency = (self._parallelism_ewma_latency * 0.8) + (latency * 0.2)

        if error is None:
            self._parallelism_successes += 1
            self._parallelism_success_streak += 1
            if (
                self._parallelism_limit < self._parallelism_max
                and self._parallelism_success_streak >= max(2, self._parallelism_limit)
                and latency <= (self._parallelism_ewma_latency or latency) * 1.35
            ):
                self._parallelism_limit += 1
                self._parallelism_success_streak = 0
                logger.debug(
                    "Adaptive concurrency increased to %d for provider=%s model=%s.",
                    self._parallelism_limit,
                    self.config.provider,
                    self.config.model,
                )
            return

        self._parallelism_failures += 1
        self._parallelism_success_streak = 0
        if isinstance(error, RateLimitError):
            self._parallelism_rate_limits += 1

        should_reduce = isinstance(error, (RateLimitError, ProviderNotAvailableError, LLMGatewayError))
        if should_reduce and self._parallelism_limit > self._parallelism_min:
            next_limit = max(self._parallelism_min, max(1, self._parallelism_limit // 2))
            if next_limit < self._parallelism_limit:
                self._parallelism_limit = next_limit
                logger.warning(
                    "Adaptive concurrency reduced to %d for provider=%s model=%s after %s.",
                    self._parallelism_limit,
                    self.config.provider,
                    self.config.model,
                    type(error).__name__,
                )

    async def calibrate_parallelism(
        self,
        *,
        max_parallelism: int = 6,
        samples_per_level: int = 2,
        probe_prompt: str = "Reply with exactly OK.",
        progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> int:
        max_parallelism = max(1, max_parallelism)
        samples_per_level = max(1, samples_per_level)
        best_parallelism = 1
        baseline_latency: float | None = None

        original_limit = self._parallelism_limit
        self.configure_parallelism(initial=max_parallelism, maximum=max_parallelism)

        try:
            search_levels: list[int] = []
            level = 1
            while level <= max_parallelism:
                search_levels.append(level)
                if level == max_parallelism:
                    break
                level = min(max_parallelism, level * 2)

            low = 1
            high: int | None = None

            for level in search_levels:
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "calibration_start",
                            "level": level,
                            "max_parallelism": max_parallelism,
                            "samples": samples_per_level * level,
                        }
                    )
                probe = await self._probe_parallelism_level(
                    level=level,
                    rounds=samples_per_level,
                    probe_prompt=probe_prompt,
                    progress_callback=progress_callback,
                )
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "calibration_result",
                            "level": probe.level,
                            "max_parallelism": max_parallelism,
                            "samples": probe.total,
                            "successes": probe.successes,
                            "elapsed": probe.elapsed,
                        }
                    )
                if not probe.succeeded:
                    high = probe.level - 1
                    break

                per_request_latency = probe.per_request_latency
                if baseline_latency is None:
                    baseline_latency = per_request_latency
                    best_parallelism = probe.level
                    low = probe.level
                    continue

                if per_request_latency > baseline_latency * 2.25:
                    high = probe.level - 1
                    break
                best_parallelism = probe.level
                low = probe.level
            else:
                high = max_parallelism

            if high is None:
                high = max_parallelism

            left = max(low + 1, 2)
            right = high
            while left <= right:
                level = (left + right) // 2
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "calibration_start",
                            "level": level,
                            "max_parallelism": max_parallelism,
                            "samples": samples_per_level * level,
                        }
                    )
                probe = await self._probe_parallelism_level(
                    level=level,
                    rounds=samples_per_level,
                    probe_prompt=probe_prompt,
                    progress_callback=progress_callback,
                )
                if progress_callback is not None:
                    progress_callback(
                        {
                            "event": "calibration_result",
                            "level": probe.level,
                            "max_parallelism": max_parallelism,
                            "samples": probe.total,
                            "successes": probe.successes,
                            "elapsed": probe.elapsed,
                        }
                    )

                if probe.succeeded and (
                    baseline_latency is None or probe.per_request_latency <= baseline_latency * 2.25
                ):
                    best_parallelism = probe.level
                    left = probe.level + 1
                else:
                    right = probe.level - 1

            self.configure_parallelism(initial=best_parallelism, maximum=max_parallelism)
            logger.info(
                "Adaptive concurrency calibrated to %d for provider=%s model=%s.",
                best_parallelism,
                self.config.provider,
                self.config.model,
            )
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "calibration_complete",
                        "parallelism": best_parallelism,
                        "max_parallelism": max_parallelism,
                    }
                )
            return best_parallelism
        finally:
            if best_parallelism == 1 and original_limit > 1:
                self.configure_parallelism(initial=1, maximum=max_parallelism)

    def _model_likely_needs_schema_prompt(self) -> bool:
        model_name = (self.config.model or "").strip().lower()
        if not model_name:
            return False
        return any(token in model_name for token in _TOOL_FRAGILE_MODEL_TOKENS)

    def _is_custom_openai_compatible_endpoint(self) -> bool:
        if self._runtime_provider != "openai":
            return False

        base_url = self._provider_settings.base_url
        if not base_url:
            return False

        try:
            hostname = urlparse(base_url).hostname
        except ValueError:
            logger.debug("Invalid base_url for Instructor detection: %s", base_url)
            return False

        if not hostname:
            return False
        if hostname in {"127.0.0.1", "localhost", "0.0.0.0"}:
            return True
        return hostname not in _OFFICIAL_OPENAI_HOSTS

    def _compute_should_bypass_instructor(self) -> bool:
        mode = (self.config.structured_output_mode or "auto").strip().lower()
        if mode == "schema":
            return True
        if mode == "instructor":
            return False
        return self._is_custom_openai_compatible_endpoint() or self._model_likely_needs_schema_prompt()

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

            provider = self._runtime_provider
            provider_settings = self._provider_settings
            client_kwargs = self._client_kwargs
            request_kwargs = self._request_kwargs
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
    @lru_cache(maxsize=128)
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
    @lru_cache(maxsize=128)
    def _schema_description(response_model: Type[Any]) -> str:
        if hasattr(response_model, "model_json_schema"):
            schema = response_model.model_json_schema()
        elif hasattr(response_model, "schema"):
            schema = response_model.schema()
        else:
            schema = str(response_model)
        return json.dumps(schema, indent=2, sort_keys=True, default=str)

    def _build_schema_prompt(self, prompt: str, response_model: Type[Any]) -> str:
        return (
            f"{prompt}\n\nReturn only valid JSON with no markdown fences, commentary, or extra text.\n"
            f"Please respond with JSON that matches this schema:\n"
            f"{self._schema_description(response_model)}"
        )

    def _build_repair_prompt(
        self,
        prompt: str,
        response_model: Type[Any],
        invalid_output: str,
        validation_error: str,
    ) -> str:
        return (
            f"{prompt}\n\n"
            "The previous response did not validate against the required schema. "
            "Repair it and return only valid JSON with no markdown fences or commentary.\n\n"
            f"Validation error:\n{validation_error}\n\n"
            f"Required schema:\n{self._schema_description(response_model)}\n\n"
            f"Previous response:\n{invalid_output}"
        )

    @staticmethod
    def _normalize_structured_output(raw_text: str) -> str:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()
                if text.lower().startswith("json"):
                    text = text[4:].lstrip()

        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end != -1 and start < end:
                candidate = text[start : end + 1].strip()
                try:
                    json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                return candidate
        return text

    @staticmethod
    def _validate_response_model_json(response_model: Type[Any], raw_text: str) -> tuple[bool, str]:
        try:
            if hasattr(response_model, "model_validate_json"):
                response_model.model_validate_json(raw_text)
            elif hasattr(response_model, "parse_raw"):
                response_model.parse_raw(raw_text)
            else:
                json.loads(raw_text)
            return True, ""
        except Exception as exc:  # pragma: no cover - exact exception type varies by pydantic version
            return False, str(exc)

    async def _coerce_structured_response(
        self,
        prompt: str,
        response_model: Type[Any],
        raw_text: str,
    ) -> str:
        normalized = self._normalize_structured_output(raw_text)
        is_valid, validation_error = self._validate_response_model_json(response_model, normalized)
        if is_valid:
            return normalized

        logger.warning(
            "Structured output did not validate for provider=%s model=%s; retrying with repair prompt.",
            self.config.provider,
            self.config.model,
        )
        repaired = await self._text_call(
            self._build_repair_prompt(prompt, response_model, normalized, validation_error)
        )
        repaired_normalized = self._normalize_structured_output(repaired)
        repaired_valid, repaired_error = self._validate_response_model_json(
            response_model,
            repaired_normalized,
        )
        if repaired_valid:
            return repaired_normalized

        raise LLMGatewayError(
            "Structured generation produced invalid JSON after repair attempt: "
            f"{repaired_error or validation_error}"
        )

    async def _structured_call(self, prompt: str, response_model: Type[Any]) -> str:
        client = await self._get_instructor_client()

        try:
            result = await client.chat.completions.create(
                **self._build_chat_payload(prompt),
                response_model=response_model,
            )
        except Exception as exc:
            raise self._classify_provider_error(
                exc,
                self.config.provider,
                structured=True,
            ) from exc

        if hasattr(result, "model_dump_json"):
            return result.model_dump_json()
        if hasattr(result, "json"):
            return result.json()
        return str(result)

    async def _load_cached_response(self, cache_key: str | None) -> LLMResponse | None:
        if cache_key is None:
            return None
        cached = await self._cache.get(cache_key)
        if cached is None:
            return None
        return LLMResponse(
            text=str(cached),
            model=self.config.model,
            provider="cache",
        )

    async def _acquire_inflight_cache(self, cache_key: str | None) -> tuple[asyncio.Future[LLMResponse] | None, bool]:
        if cache_key is None:
            return None, True

        async with self._inflight_cache_lock:
            existing = self._inflight_cache.get(cache_key)
            if existing is not None:
                return existing, False

            future: asyncio.Future[LLMResponse] = asyncio.get_running_loop().create_future()
            self._inflight_cache[cache_key] = future
            return future, True

    async def _resolve_inflight_cache(
        self,
        cache_key: str | None,
        future: asyncio.Future[LLMResponse] | None,
        *,
        response: LLMResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        if cache_key is None or future is None:
            return

        async with self._inflight_cache_lock:
            self._inflight_cache.pop(cache_key, None)

        if future.done():
            return
        if error is not None:
            future.set_exception(error)
            return
        if response is not None:
            future.set_result(response)

    async def _probe_parallelism_level(
        self,
        *,
        level: int,
        rounds: int,
        probe_prompt: str,
        progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> CalibrationProbeResult:
        started = perf_counter()
        successes = 0
        total = 0

        for round_index in range(rounds):
            tasks = [
                asyncio.create_task(
                    self._text_call(f"{probe_prompt} probe={level}-{round_index}-{slot}-{perf_counter():.6f}")
                )
                for slot in range(level)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_successes = sum(1 for item in results if isinstance(item, str) and item.strip())
            successes += batch_successes
            total += len(results)

            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "calibration_round",
                        "level": level,
                        "round": round_index + 1,
                        "rounds": rounds,
                        "successes": batch_successes,
                        "samples": len(results),
                    }
                )

            if batch_successes != len(results):
                break

        return CalibrationProbeResult(
            level=level,
            successes=successes,
            total=total,
            elapsed=max(0.0, perf_counter() - started),
        )

    async def generate(
        self,
        prompt: str,
        response_model: Optional[Type[Any]] = None,
    ) -> LLMResponse:
        schema_hash = self._schema_hash(response_model) if response_model is not None else ""
        cache_key = f"{self.config.model_id}:{prompt}:{schema_hash}" if self._enable_cache else None
        cached = await self._load_cached_response(cache_key)
        if cached is not None:
            return cached

        inflight_future, should_execute = await self._acquire_inflight_cache(cache_key)
        if not should_execute and inflight_future is not None:
            return await asyncio.shield(inflight_future)

        await self._acquire_parallelism_slot()
        started = perf_counter()
        caught_error: Exception | None = None
        try:
            use_instructor = (
                response_model is not None
                and self._supports_instructor()
                and self._is_instructor_response_model(response_model)
                and not self._bypass_instructor
            )
            final_prompt = prompt
            effective_response_model = response_model

            if response_model is not None and not use_instructor:
                if self._bypass_instructor:
                    logger.debug(
                        "Bypassing Instructor for provider=%s model=%s response_model=%s to favor schema-guided prompting.",
                        self.config.provider,
                        self.config.model,
                        getattr(response_model, "__name__", type(response_model).__name__),
                    )
                else:
                    logger.warning(
                        "Falling back to schema-guided prompting for provider=%s response_model=%s.",
                        self.config.provider,
                        getattr(response_model, "__name__", type(response_model).__name__),
                    )
                final_prompt = self._build_schema_prompt(prompt, response_model)
                effective_response_model = None

            if effective_response_model is None:
                raw_text = await self._text_call(final_prompt)
            else:
                try:
                    raw_text = await self._structured_call(final_prompt, effective_response_model)
                except LLMGatewayError:
                    logger.warning(
                        "Structured generation failed for provider=%s model=%s; retrying with schema-guided prompting.",
                        self.config.provider,
                        self.config.model,
                    )
                    logger.debug("Structured generation failure details", exc_info=True)
                    raw_text = await self._text_call(
                        self._build_schema_prompt(prompt, effective_response_model)
                    )
                    effective_response_model = None

            if response_model is not None:
                raw_text = await self._coerce_structured_response(prompt, response_model, raw_text)

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

            response = LLMResponse(
                text=raw_text,
                model=self.config.model,
                provider=self.config.provider,
                tokens_used=tokens_used,
                cost=cost,
            )
            await self._resolve_inflight_cache(cache_key, inflight_future, response=response)
            return response
        except Exception as exc:
            caught_error = exc if isinstance(exc, Exception) else Exception(str(exc))
            await self._resolve_inflight_cache(cache_key, inflight_future, error=caught_error)
            raise
        finally:
            await self._release_parallelism_slot(
                latency=max(0.0, perf_counter() - started),
                error=caught_error,
            )

    def generate_sync(
        self,
        prompt: str,
        response_model: Optional[Type[Any]] = None,
    ) -> LLMResponse:
        return asyncio.run(self.generate(prompt, response_model=response_model))
