"""Adapters that make llm_gateway.LLMClient work as Graphiti's LLM client and embedder."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from graphiti_core.embedder import Embedder as GraphitiEmbedderBase
from graphiti_core.llm_client import LLMClient as GraphitiLLMClientBase

from llm_gateway.settings import ProviderSettings

if TYPE_CHECKING:
    from llm_gateway.client import LLMClient as GatewayLLMClient

logger = logging.getLogger(__name__)


class GatewayLLMClient(GraphitiLLMClientBase):
    def __init__(self, gateway: GatewayLLMClient):
        self._gateway = gateway

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict | None = None,
    ) -> dict[str, str]:
        prompt = "\n".join(m["content"] for m in messages)
        llm_response = await self._gateway.generate(prompt)
        return {"content": llm_response.text}


class GatewayEmbedder(GraphitiEmbedderBase):
    def __init__(self, provider_settings: ProviderSettings, model: str, dimensions: int):
        self._provider_settings = provider_settings
        self._model = model
        self._dimensions = dimensions
        self._openai = None

    async def create(self, input: str | list[str]) -> List[List[float]]:
        if isinstance(input, str):
            input = [input]

        try:
            client = self._get_openai_client()
            resp = await client.embeddings.create(input=input, model=self._model)
            return [d.embedding for d in resp.data]
        except Exception:
            logger.exception("Embedding call failed. Falling back to local zeros.")
            return [[0.0] * self._dimensions for _ in input]

    def _get_openai_client(self):
        if self._openai is not None:
            return self._openai

        import openai

        client_kwargs = self._provider_settings.build_client_kwargs()
        runtime_provider = self._provider_settings.runtime_type
        if runtime_provider == "azure":
            self._openai = openai.AsyncAzureOpenAI(
                api_key=self._provider_settings.api_key,
                **client_kwargs,
            )
        else:
            self._openai = openai.AsyncOpenAI(
                api_key=self._provider_settings.api_key,
                **client_kwargs,
            )
        return self._openai
