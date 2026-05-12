from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Optional
import json

from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_narrative.memory_optimized import OptimizedMemoryStore, NPCProfile
from world_narrative.chronicler import Chronicler


class NewbornScenario:
    """
    Prepares the world for a character born into it:
    - Minimal initial knowledge
    - No pre‑existing relationships
    - The world already exists, but the character is new.
    """

    @staticmethod
    async def prepare(
        character_name: str,
        gm: GraphManager,
        builder: WorldBuilder,
        npc_mgr: OptimizedMemoryStore,
        chronicler: Chronicler,
    ) -> None:
        """Reset the character's memory and graph connections."""
        # 1. Ensure character exists in the graph
        node = gm.store.get_by_name_and_type(character_name, "Character")
        if not node:
            node = await builder.add_npc("default")
            # Rename to desired name? Not easily; we'll assume the name matches.

        # 2. Clear NPC's memory in OptimizedMemoryStore
        if character_name in npc_mgr._npcs:
            profile = npc_mgr._npcs[character_name]
            profile.short_term.clear()
            profile.long_term_episodic.clear()
            profile.semantic.clear()
            profile.location = "unknown"
            profile.health = 100
            profile.mood = "neutral"
            profile.goals = []
            profile.inventory.clear()
            npc_mgr._save()

        # 3. Remove all incoming/outgoing edges for this character in the graph
        G = gm.graph
        if node:
            uid = node.uid
            # Remove edges in adjacency and reverse adjacency
            for target, _, _ in G.adj.get(uid, []):
                G.rev_adj[target] = [e for e in G.rev_adj.get(target, []) if e[0] != uid]
            G.adj[uid].clear()
            for src, _, _ in G.rev_adj.get(uid, []):
                G.adj[src] = [e for e in G.adj.get(src, []) if e[0] != uid]
            G.rev_adj[uid].clear()

        # 4. Log the birth event
        await chronicler.log_event(f"{character_name} is born into the world.", datetime.now(), group="birth")
