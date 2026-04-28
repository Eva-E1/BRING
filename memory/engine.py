"""Memory engine - lifecycle, ingestion, search, and maintenance orchestration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Mapping, Optional
from uuid import uuid4

from pydantic import BaseModel

from llm_gateway.client import LLMClient

from .config import MemorySettings, get_settings
from .database import MemoryDatabaseManager
from .extraction import structured_extraction
from .graph import MemoryGraph
from .maintenance import MemoryMaintenance

logger = logging.getLogger(__name__)


class MemoryEngine:
    """Entry point for the BRING memory system."""

    def __init__(
        self,
        settings: Optional[MemorySettings] = None,
        *,
        entity_types: Optional[Mapping[str, type[BaseModel]]] = None,
    ):
        self.settings = settings or get_settings()
        self._graph = MemoryGraph(self.settings, entity_types=entity_types)
        self._maintenance = MemoryMaintenance(self.settings)
        self._gateway: Optional[LLMClient] = None
        self._started = False

    async def start(self, gateway: LLMClient) -> None:
        if self._started:
            return

        self._gateway = gateway
        await self._graph.start(gateway)
        self._graph.database_manager.write_manifest(gateway=gateway)
        self._started = True
        logger.info(
            "Memory engine started (database=%s, Kuzu at %s)",
            self.settings.normalized_database_id,
            self.settings.database_path,
        )

    async def stop(self) -> None:
        await self._graph.close()
        self._started = False
        logger.info("Memory engine stopped")

    @property
    def graphiti(self):
        return self._graph.graphiti

    @property
    def gateway(self) -> LLMClient:
        if self._gateway is None:
            raise RuntimeError("Memory engine not started.")
        return self._gateway

    @property
    def database_manager(self) -> MemoryDatabaseManager:
        return self._graph.database_manager

    @property
    def entity_types(self) -> dict[str, type[BaseModel]]:
        return self._graph.entity_types

    def export_database(self, destination: Optional[str] = None) -> str:
        return str(self.database_manager.export_archive(destination))

    def clone_database(self, database_id: str) -> MemoryDatabaseManager:
        return self.database_manager.clone_database(database_id)

    async def add_episodes_bulk(
        self,
        episodes: list[dict],
        group_id: str = "default",
    ) -> None:
        semaphore = asyncio.Semaphore(self.settings.bulk_ingestion_batch_size)
        prepared = self._maintenance.prepare_episode_batch(episodes, group_id)

        async def ingest_one(episode):
            async with semaphore:
                await self._add_single_episode(
                    name=episode.name,
                    body=episode.body,
                    reference_time=episode.reference_time,
                    group_id=episode.group_id,
                    uuid=episode.uuid,
                    metadata=episode.metadata,
                )

        await asyncio.gather(*(ingest_one(episode) for episode in prepared))

    async def _add_single_episode(
        self,
        name: str,
        body: str,
        reference_time: datetime,
        group_id: str = "default",
        uuid: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        episode_uuid = uuid or str(uuid4())
        source_description = "BRING memory ingestion"
        if metadata:
            volume = metadata.get("volume")
            chapter = metadata.get("chapter")
            parts = [source_description]
            if volume is not None:
                parts.append(f"volume={volume}")
            if chapter is not None:
                parts.append(f"chapter={chapter}")
            source_description = ", ".join(parts)

        await self.graphiti.add_episode(
            name=name,
            episode_body=body,
            source_description=source_description,
            reference_time=reference_time,
            group_id=group_id,
            uuid=episode_uuid,
            entity_types=self.entity_types,
        )
        self._maintenance.invalidate_search_cache()
        return episode_uuid

    async def search(
        self,
        query: str,
        group_ids: Optional[list[str]] = None,
        node_labels: Optional[list[str]] = None,
        center_node_uuid: Optional[str] = None,
    ) -> list[dict]:
        from graphiti_core.search.search_filters import SearchFilters

        cache_key = self._maintenance.build_search_cache_key(
            query=query,
            group_ids=group_ids,
            node_labels=node_labels,
            center_node_uuid=center_node_uuid,
        )
        cached = await self._maintenance.get_cached_search(cache_key)
        if cached is not None:
            return cached

        filters = SearchFilters()
        if node_labels:
            filters.node_labels = node_labels

        results = await self.graphiti.search(
            query=query,
            group_ids=group_ids or ["default"],
            search_filter=filters,
            center_node_uuid=center_node_uuid,
        )
        normalized = self._maintenance.normalize_search_results(results)
        await self._maintenance.cache_search(cache_key, normalized)
        return normalized
