"""Graph lifecycle wrapper that keeps Graphiti wiring isolated from higher-level memory orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from graphiti_core import Graphiti
from graphiti_core.driver.kuzu_driver import KuzuDriver
from pydantic import BaseModel

from llm_gateway.client import LLMClient

from .config import MemorySettings
from .database import MemoryDatabaseManager
from .gateway_adapter import GatewayCrossEncoder, GatewayEmbedder, GatewayLLMClient
from .ontology import ENTITY_TYPES


class MemoryGraph:
    def __init__(
        self,
        settings: MemorySettings,
        entity_types: Optional[Mapping[str, type[BaseModel]]] = None,
    ):
        self._settings = settings
        self._database_manager = MemoryDatabaseManager(settings)
        self._entity_types = dict(entity_types or ENTITY_TYPES)
        self._graphiti: Optional[Graphiti] = None

    async def start(self, gateway: LLMClient) -> None:
        if self._graphiti is not None:
            return

        self._database_manager.ensure_layout()
        db_path = Path(self._settings.database_path)
        db_path.mkdir(parents=True, exist_ok=True)
        driver = KuzuDriver(db=str(db_path / "graph.kuzu"))
        provider_settings = gateway.config.provider_settings

        self._graphiti = Graphiti(
            graph_driver=driver,
            llm_client=GatewayLLMClient(gateway),
            embedder=GatewayEmbedder(provider_settings.embedding),
            cross_encoder=GatewayCrossEncoder(),
            store_raw_episode_content=self._settings.graphiti_store_raw_episodes,
            max_coroutines=self._settings.graphiti_max_coroutines,
        )
        await self._graphiti.build_indices_and_constraints()

    async def close(self) -> None:
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None

    @property
    def graphiti(self) -> Graphiti:
        if self._graphiti is None:
            raise RuntimeError("Memory graph not started. Call `await engine.start(gateway)` first.")
        return self._graphiti

    @property
    def database_manager(self) -> MemoryDatabaseManager:
        return self._database_manager

    @property
    def entity_types(self) -> dict[str, type[BaseModel]]:
        return dict(self._entity_types)
