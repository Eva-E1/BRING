"""Actor context - what a character knows right now (point-in-time)."""

from __future__ import annotations

from datetime import datetime

from .chronicler import Chronicler
from .engine import MemoryEngine


class ActorContext:
    def __init__(self, engine: MemoryEngine):
        self._chronicler = Chronicler(engine)

    async def get_current_knowledge(
        self,
        character_name: str,
        story_time: datetime,
        group_id: str = "default",
    ) -> list[dict]:
        return await self._chronicler.query_state_at(
            query=character_name,
            story_time=story_time,
            node_labels=["Character", "Location", "Item", "Event"],
            group_id=group_id,
        )
