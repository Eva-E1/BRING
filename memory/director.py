"""Director agent - provides context for plot generation and antagonist interventions."""

from __future__ import annotations

from datetime import datetime

from .chronicler import Chronicler
from .engine import MemoryEngine


class Director:
    def __init__(self, engine: MemoryEngine):
        self._chronicler = Chronicler(engine)
        self._engine = engine

    async def get_narrative_context(
        self,
        query: str,
        story_time: datetime,
        scope_labels: list[str] | None = None,
        group_id: str = "default",
    ) -> dict:
        current = await self._chronicler.query_state_at(
            query=query,
            story_time=story_time,
            node_labels=scope_labels,
            group_id=group_id,
        )
        timeline = await self._chronicler.get_timeline(subject=query, group_id=group_id)
        return {
            "story_time": story_time.isoformat(),
            "current_state": current,
            "relevant_history": timeline[-self._engine.settings.timeline_window :],
        }

    async def inject_antagonist_event(
        self,
        event_description: str,
        story_time: datetime,
        group_id: str = "default",
    ) -> str:
        return await self._chronicler.log_event(
            description=event_description,
            story_time=story_time,
            group_id=group_id,
        )
