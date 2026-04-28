"""Adapters that make llm_gateway.LLMClient work as Graphiti's LLM client and embedder."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from graphiti_core.embedder import EmbedderClient as GraphitiEmbedderBase
from graphiti_core.cross_encoder.client import CrossEncoderClient

from graphiti_core.llm_client import LLMClient as GraphitiLLMClientBase
from graphiti_core.llm_client.config import ModelSize
from graphiti_core.prompts.models import Message

from llm_gateway.settings import EmbeddingSettings

if TYPE_CHECKING:
    from llm_gateway.client import LLMClient as GatewayLLMClient

logger = logging.getLogger(__name__)


class GatewayLLMClient(GraphitiLLMClientBase):
    def __init__(self, gateway: GatewayLLMClient):
        super().__init__(config=None, cache=False)
        self._gateway = gateway
        self.model = gateway.config.model
        self.max_tokens = gateway.config.max_tokens

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type | None = None,
        max_tokens: int = 16384,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, str]:
        del max_tokens, model_size

        prompt = "\n".join(message.content for message in messages)
        llm_response = await self._gateway.generate(prompt, response_model=response_model)

        if response_model is None:
            return {"content": llm_response.text}

        if hasattr(response_model, "model_validate_json"):
            return response_model.model_validate_json(llm_response.text).model_dump()
        return json.loads(llm_response.text)

    def _get_provider_type(self) -> str:
        return self._gateway.config.runtime_provider


class GatewayEmbedder(GraphitiEmbedderBase):
    def __init__(self, settings: EmbeddingSettings):
        self._settings = settings
        self._openai = None

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        if isinstance(input_data, str):
            payload = [input_data]
        elif isinstance(input_data, list):
            payload = input_data
        else:
            payload = list(input_data)

        try:
            client = self._get_openai_client()
            resp = await client.embeddings.create(input=payload, model=self._settings.model)
            return resp.data[0].embedding[: self._settings.dimensions]
        except Exception:
            logger.exception("Embedding call failed. Falling back to local zeros.")
            return [0.0] * self._settings.dimensions

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        try:
            client = self._get_openai_client()
            resp = await client.embeddings.create(
                input=input_data_list,
                model=self._settings.model,
            )
            return [item.embedding[: self._settings.dimensions] for item in resp.data]
        except Exception:
            logger.exception("Batch embedding call failed. Falling back to local zeros.")
            return [[0.0] * self._settings.dimensions for _ in input_data_list]

    def _get_openai_client(self):
        if self._openai is not None:
            return self._openai

        import openai

        client_kwargs = self._settings.build_client_kwargs()
        runtime_provider = self._settings.runtime_type
        if runtime_provider == "azure":
            self._openai = openai.AsyncAzureOpenAI(
                api_key=self._settings.api_key,
                **client_kwargs,
            )
        else:
            self._openai = openai.AsyncOpenAI(
                api_key=self._settings.api_key,
                **client_kwargs,
            )
        return self._openai


class GatewayCrossEncoder(CrossEncoderClient):
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        del query
        # Preserve input order when no dedicated reranker is configured.
        return [(passage, float(len(passages) - index)) for index, passage in enumerate(passages)]
