"""Graph lifecycle wrapper that keeps Graphiti wiring isolated from higher-level memory orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from graphiti_core import Graphiti
from graphiti_core.driver.kuzu_driver import KuzuDriver

from llm_gateway.client import LLMClient

from .config import MemorySettings
from .gateway_adapter import GatewayEmbedder, GatewayLLMClient
from .ontology import ENTITY_TYPES


class MemoryGraph:
    def __init__(self, settings: MemorySettings):
        self._settings = settings
        self._graphiti: Optional[Graphiti] = None

    async def start(self, gateway: LLMClient) -> None:
        if self._graphiti is not None:
            return

        db_path = Path(self._settings.kuzu_db_path)
        db_path.mkdir(parents=True, exist_ok=True)
        driver = KuzuDriver(db_path=str(db_path))
        provider_settings = gateway.config.provider_settings

        self._graphiti = Graphiti(
            graph_driver=driver,
            llm_client=GatewayLLMClient(gateway),
            embedder=GatewayEmbedder(
                provider_settings=provider_settings,
                model=provider_settings.embedding.model,
                dimensions=provider_settings.embedding.dimensions,
            ),
            store_raw_episode_content=self._settings.graphiti_store_raw_episodes,
            max_coroutines=self._settings.graphiti_max_coroutines,
        )
        await self._graphiti.build_indices_and_constraints()
        for entity_type in ENTITY_TYPES.values():
            self._graphiti.add_entity_type(entity_type)

    async def close(self) -> None:
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None

    @property
    def graphiti(self) -> Graphiti:
        if self._graphiti is None:
            raise RuntimeError("Memory graph not started. Call `await engine.start(gateway)` first.")
        return self._graphiti
