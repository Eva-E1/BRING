"""
BRING v2 — Advanced LLM client with connection pooling, response caching, and structured output.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Type

import httpx
import numpy as np
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionToolParam
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LRUCache:
    """Simple LRU cache for LLM responses."""

    def __init__(self, max_size: int = 256):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _make_key(self, prompt: str, temperature: float, json_mode: bool, model: str) -> str:
        raw = f"{model}|{temperature}|{json_mode}|{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    @property
    def stats(self) -> Dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._cache)}


class EmbeddingCache:
    """LRU cache for embedding vectors."""

    def __init__(self, max_size: int = 512):
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._max_size = max_size

    def get(self, text: str) -> Optional[List[float]]:
        key = hashlib.sha256(text.encode()).hexdigest()[:16]
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, text: str, embedding: List[float]) -> None:
        key = hashlib.sha256(text.encode()).hexdigest()[:16]
        self._cache[key] = embedding
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


class LLMClient:
    """
    Async LLM client with:
    - Response caching (LRU)
    - Embedding caching
    - Connection pooling
    - Rate limiting semaphore
    - Retry with exponential backoff
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        *,
        timeout: float = 120.0,
        max_retries: int = 3,
        max_connections: int = 100,
        default_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        cache_size: int = 256,
        max_concurrent: int = 8,
    ):
        self.base_url = base_url or os.environ.get("BASE_URL") or os.environ.get("LLM_BASE_URL")
        if not self.base_url:
            raise ValueError("No base URL provided.")
        self.api_key = api_key or os.environ.get("LIARA_API_KEY") or os.environ.get("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("No API key provided.")
        self.default_model = default_model or os.environ.get("LLM_MODEL", "openai/gpt-4o-mini")
        self.embedding_model = embedding_model or os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-small")

        self._http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=20),
            timeout=httpx.Timeout(timeout),
        )
        self._openai = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            max_retries=max_retries,
            http_client=self._http_client,
        )

        self._response_cache = LRUCache(cache_size)
        self._embedding_cache = EmbeddingCache(cache_size * 2)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        await self._http_client.aclose()

    # ── Core chat ──────────────────────────────────────────

    async def _chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        json_mode: bool = False,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        model = model or self.default_model

        # Check cache
        if use_cache and temperature < 0.1:
            cache_key = self._response_cache._make_key(prompt, temperature, json_mode, model)
            cached = self._response_cache.get(cache_key)
            if cached is not None:
                return cached

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        async with self._semaphore:
            response = await self._openai.chat.completions.create(**kwargs)

        result = {
            "text": response.choices[0].message.content or "",
            "usage": response.usage,
            "response": response,
        }

        # Store in cache
        if use_cache and temperature < 0.1:
            self._response_cache.put(cache_key, result)

        return result

    # ── Public API (backward compatible) ───────────────────

    async def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        result = await self._chat(prompt, temperature=temperature, json_mode=False)
        return result["text"]

    async def generate_json(self, prompt: str, temperature: float = 0.7) -> dict:
        result = await self._chat(prompt, temperature=temperature, json_mode=True)
        try:
            return json.loads(result["text"])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {result['text'][:200]}")
            raise LLMError(f"LLM did not return valid JSON: {e}")

    # ── Structured output ──────────────────────────────────

    async def generate_object(
        self,
        schema: Type[BaseModel],
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> BaseModel:
        clean_schema = self._sanitize_schema(schema.model_json_schema())
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": clean_schema,
            },
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with self._semaphore:
            response = await self._openai.chat.completions.create(
                model=model or self.default_model,
                messages=messages,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens or 4096,
            )
        content = response.choices[0].message.content
        try:
            parsed = json.loads(content)
            return schema.model_validate(parsed)
        except Exception as e:
            raise LLMError(f"Structured output failed: {e}") from e

    # ── Streaming ──────────────────────────────────────────

    async def stream_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with self._semaphore:
            stream = await self._openai.chat.completions.create(
                model=model or self.default_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    # ── Embeddings with cache ──────────────────────────────

    async def embedding(self, text: str) -> List[float]:
        cached = self._embedding_cache.get(text)
        if cached is not None:
            return cached

        try:
            return await self.embed(text)
        except Exception as e:
            logger.warning(f"Embedding API failed, using fallback: {e}")
            from world_core.utils import deterministic_hash
            return deterministic_hash(text)

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        cached = self._embedding_cache.get(text)
        if cached is not None:
            return cached

        async with self._semaphore:
            response = await self._openai.embeddings.create(
                model=model or self.embedding_model,
                input=text,
            )
        embedding = response.data[0].embedding
        self._embedding_cache.put(text, embedding)
        return embedding

    async def embed_many(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        # Check cache for each
        results = []
        uncached_indices = []
        uncached_texts = []

        for i, text in enumerate(texts):
            cached = self._embedding_cache.get(text)
            if cached is not None:
                results.append((i, cached))
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            async with self._semaphore:
                response = await self._openai.embeddings.create(
                    model=model or self.embedding_model,
                    input=uncached_texts,
                )
            for idx, item in zip(uncached_indices, response.data):
                embedding = item.embedding
                self._embedding_cache.put(uncached_texts[uncached_indices.index(idx)], embedding)
                results.append((idx, embedding))

        # Reorder
        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    # ── Utility methods ────────────────────────────────────

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        a_arr, b_arr = np.array(a), np.array(b)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))

    async def classify_enum(
        self, prompt: str, enum_values: List[str], model: Optional[str] = None
    ) -> str:
        system = "You must answer with exactly one of: " + ", ".join(enum_values)
        res = await self._chat(prompt, system=system, model=model, temperature=0.0)
        return res["text"].strip()

    async def run_with_tools(
        self,
        prompt: str,
        tools: List[ChatCompletionToolParam],
        tool_executor: Callable,
        model: Optional[str] = None,
        max_rounds: int = 3,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        for _ in range(max_rounds):
            async with self._semaphore:
                response = await self._openai.chat.completions.create(
                    model=model or self.default_model,
                    messages=messages,
                    tools=tools,
                )
            msg = response.choices[0].message
            if msg.tool_calls:
                messages.append(msg.model_dump())
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments)
                    result = tool_executor(tc.function.name, args)
                    if asyncio.iscoroutine(result):
                        result = await result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
            else:
                return msg.content or ""
        raise LLMError("Tool calling reached maximum rounds without final answer.")

    # ── Schema sanitization ────────────────────────────────

    @staticmethod
    def _sanitize_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        schema = copy.deepcopy(schema)

        def _clean(node: Any) -> Any:
            if not isinstance(node, dict):
                return node
            for forbidden in ("title", "description", "default", "$schema", "$ref", "$defs"):
                node.pop(forbidden, None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                if "properties" not in node:
                    node["properties"] = {}
                for pname, pval in node.get("properties", {}).items():
                    node["properties"][pname] = _clean(pval)
                node["required"] = sorted(node["properties"].keys())
            if node.get("type") == "array" and "items" in node:
                node["items"] = _clean(node["items"])
            for comb in ("allOf", "anyOf", "oneOf"):
                if comb in node:
                    node[comb] = [_clean(sub) for sub in node[comb]]
            return node

        return _clean(schema)

    @property
    def cache_stats(self) -> Dict[str, int]:
        return self._response_cache.stats

