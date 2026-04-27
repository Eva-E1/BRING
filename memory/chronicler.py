"""Chronicler agent - manages the bi-temporal timeline of the narrative."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from .engine import MemoryEngine

logger = logging.getLogger(__name__)


class Chronicler:
    def __init__(self, engine: MemoryEngine):
        self._engine = engine

    async def log_event(
        self,
        description: str,
        story_time: datetime,
        group_id: str = "default",
    ) -> str:
        episode_uuid = str(uuid4())
        await self._engine._add_single_episode(
            name=f"event-{episode_uuid[:8]}",
            body=description,
            reference_time=story_time,
            group_id=group_id,
            uuid=episode_uuid,
        )
        logger.info("Chronicler logged event at story time %s", story_time)
        return episode_uuid

    async def query_state_at(
        self,
        query: str,
        story_time: datetime,
        node_labels: list[str] | None = None,
        group_id: str = "default",
    ) -> list[dict]:
        from graphiti_core.search.search_filters import DateFilter, SearchFilters

        valid = DateFilter(comparison="less_than_equal", value=story_time)
        invalid_gt = DateFilter(comparison="greater_than", value=story_time)
        invalid_null = DateFilter(comparison="is_null", value=None)

        filters = SearchFilters(
            node_labels=node_labels,
            valid_at=[[valid]],
            invalid_at=[[invalid_gt], [invalid_null]],
        )

        results = await self._engine.graphiti.search(
            query=query,
            group_ids=[group_id],
            search_filter=filters,
        )
        return self._engine._maintenance.normalize_search_results(results)

    async def get_timeline(
        self,
        subject: str,
        group_id: str = "default",
    ) -> list[dict]:
        results = await self._engine.search(query=subject, group_ids=[group_id])
        sorted_results = sorted(results, key=lambda item: item.get("valid_at") or "")
        return sorted_results[-self._engine.settings.timeline_window :]
