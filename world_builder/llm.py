"""Async wrapper around an OpenAI‑compatible chat API with rate limiting, adaptive retries, and timeouts."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Optional

import httpx
from openai import AsyncOpenAI

from .config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_MAX_RETRIES,
    LLM_RATE_LIMIT_RPS,
    LLM_MAX_CONCURRENT,
    LLM_TIMEOUT,
    LLM_CONNECT_TIMEOUT,
    LLM_READ_TIMEOUT,
)

logger = logging.getLogger("world_builder.llm")

# ── Token bucket rate limiter for weak APIs ──────────────────────
class RateLimiter:
    """Async token bucket that limits requests per second."""
    def __init__(self, rate: float):
        self.rate = rate                # requests per second
        self.tokens = rate
        self.last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            # need to wait until a token is available
            wait = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait)
            self.tokens = 0
            self.last = time.monotonic()


class LLMClient:
    """Handles all LLM communication with exponential backoff, error resilience, and timeouts."""

    def __init__(self):
        # Build a custom httpx client with connection pooling and proper timeouts
        # httpx.Timeout does not accept a 'total' parameter – we use the wrapper timeout for that
        timeout = httpx.Timeout(
            connect=LLM_CONNECT_TIMEOUT,
            read=LLM_READ_TIMEOUT,
            write=10.0,
            pool=10.0,
        )
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)

        self.client = AsyncOpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            max_retries=0,          # we handle retries ourselves
            timeout=timeout,
            http_client=httpx.AsyncClient(limits=limits, timeout=timeout),
        )
        self.model = LLM_MODEL
        self.rate_limiter = RateLimiter(LLM_RATE_LIMIT_RPS)
        self._sem = asyncio.Semaphore(LLM_MAX_CONCURRENT)

    async def _chat_with_retries(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        json_mode: bool = False,
    ):
        """Send a chat completion request with retries, rate limiting, and a hard timeout."""
        last_exception = None
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                # obey global rate limit
                await self.rate_limiter.acquire()

                async with self._sem:   # limit concurrency
                    kwargs = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    # total timeout enforced by asyncio.wait_for
                    return await asyncio.wait_for(
                        self.client.chat.completions.create(**kwargs),
                        timeout=LLM_TIMEOUT,
                    )
            except asyncio.TimeoutError:
                last_exception = TimeoutError("LLM request timed out")
                logger.warning(f"Timeout (attempt {attempt+1}/{LLM_MAX_RETRIES+1})")
            except Exception as e:
                last_exception = e
                # Check for 429 Too Many Requests and honour Retry-After header
                if hasattr(e, 'status_code') and e.status_code == 429:
                    retry_after = None
                    if hasattr(e, 'headers'):
                        retry_after = e.headers.get("Retry-After")
                    if retry_after is not None:
                        try:
                            wait = float(retry_after)
                        except ValueError:
                            wait = 5.0
                    else:
                        wait = random.uniform(1, 5)
                    logger.warning(
                        f"Rate limited (429). Retrying after {wait:.1f}s "
                        f"(attempt {attempt+1}/{LLM_MAX_RETRIES+1})"
                    )
                    await asyncio.sleep(wait)
                    continue
                if attempt == LLM_MAX_RETRIES:
                    raise
                # Exponential backoff with jitter for other errors
                base_wait = 2 ** attempt
                jitter = random.uniform(0, base_wait * 0.5)
                wait = base_wait + jitter
                logger.warning(
                    f"LLM error: {e}. Retrying in {wait:.1f}s "
                    f"(attempt {attempt+1}/{LLM_MAX_RETRIES+1})"
                )
                await asyncio.sleep(wait)
        raise last_exception

    async def generate_json(self, prompt: str, temperature: float = 0.7) -> dict:
        """Send a prompt and return the parsed JSON response.
        Includes fallback retries if the initial output is not valid JSON.
        """
        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self._chat_with_retries(messages, temperature=temperature, json_mode=True)
            content = response.choices[0].message.content
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            # Try one more time with explicit instruction
            try:
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "Your last response was not valid JSON. Return ONLY a valid JSON object this time."
                })
                response = await self._chat_with_retries(messages, temperature=0.3, json_mode=True)
                return json.loads(response.choices[0].message.content)
            except Exception:
                raise ValueError("LLM failed to produce valid JSON after retries")
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {e}") from e

    async def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        """Send a prompt and return raw text."""
        messages = [{"role": "user", "content": prompt}]
        response = await self._chat_with_retries(messages, temperature=temperature, json_mode=False)
        return response.choices[0].message.content.strip()
