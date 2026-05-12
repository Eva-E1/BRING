/home/ali/Lab/world_director/world_evolver.py
```

```python
from __future__ import annotations
import logging
import random
from typing import Optional
from datetime import datetime

from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_builder.llm import LLMClient
from world_narrative.memory_optimized import OptimizedMemoryStore
from world_narrative.chronicler import Chronicler

logger = logging.getLogger(__name__)


class WorldEvolver:
    def __init__(
        self,
        gm: GraphManager,
        builder: WorldBuilder,
        npc_mgr: OptimizedMemoryStore,
        chronicler: Chronicler,
        llm: LLMClient,
    ):
        self.gm = gm
        self.builder = builder
        self.npc_mgr = npc_mgr
        self.chronicler = chronicler
        self.llm = llm

    async def add_random_npc(self, faction_or_race: str = None) -> str:
        """Add a new NPC to the world."""
        if not faction_or_race:
            # Pick a random existing faction or race from world frame
            factions = self.builder.world_frame.get("factions", [])
            races = self.builder.world_frame.get("races", [])
            candidates = [f["name"] for f in factions] + [r["name"] for r in races]
            if candidates:
                faction_or_race = random.choice(candidates)
            else:
                faction_or_race = "unknown"
        node = await self.builder.add_npc(faction_or_race)
        await self.chronicler.log_event(f"New NPC {node.name} appeared in the world.", datetime.now(), group="evolution")
        return node.name

    async def add_random_location(self) -> str:
        """Add a new location, optionally connected to existing ones."""
        node = await self.builder.add_location()
        await self.chronicler.log_event(f"New location discovered: {node.name}", datetime.now(), group="evolution")
        return node.name

    async def add_random_item(self, item_type: str = "artifact") -> str:
        node = await self.builder.add_item(item_type, rarity=random.choice(["common", "uncommon", "rare"]))
        await self.chronicler.log_event(f"New item: {node.name} appears in the world.", datetime.now(), group="evolution")
        return node.name

    async def evolve_world(self, story_time: datetime):
        """Called periodically to add new elements based on story progression."""
        # 20% chance to add a new NPC
        if random.random() < 0.2:
            await self.add_random_npc()
        # 10% chance to add a new location
        if random.random() < 0.1:
            await self.add_random_location()
        # 15% chance to add a new item
        if random.random() < 0.15:
            await self.add_random_item()
