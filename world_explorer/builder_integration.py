"""
Integration layer for world_builder.
Provides a synchronous API so the explorer can call the builder easily.
Reuses the explorer's EntityStore to avoid reloading and sync instantly.
"""

import sys
import asyncio
from pathlib import Path
from typing import Optional, Union
from rich.console import Console

# Ensure the parent directory (Lab) is on the Python path
_LAB_DIR = Path(__file__).resolve().parent.parent
if str(_LAB_DIR) not in sys.path:
    sys.path.insert(0, str(_LAB_DIR))

from world_builder.llm import LLMClient
from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_builder.config import get_entity_store_path, get_world_frame_path, DATABASE_PATH as BUILDER_DB_PATH
from world_builder.entity_store import EntityStore

console = Console()

class BuilderInterface:
    """
    Wraps the async builder and exposes common operations.
    Can optionally reuse an existing GraphManager (and its EntityStore) to
    avoid reloading the database and to keep the explorer's graph in sync.
    """

    def __init__(self, db_path: Optional[Path] = None,
                 gm: Optional[GraphManager] = None,
                 existing_builder: Optional[WorldBuilder] = None):
        self.db_path = db_path or BUILDER_DB_PATH
        if existing_builder:
            self.builder = existing_builder
            self.gm = existing_builder.gm
        elif gm:
            self.gm = gm
            self.llm_client = LLMClient()
            self.builder = WorldBuilder(
                llm=self.llm_client,
                gm=self.gm,
                num_episodes=0,
                world_frame_path=get_world_frame_path(self.db_path),
            )
        else:
            self.llm_client = LLMClient()
            self.gm = GraphManager(entity_store_path=get_entity_store_path(self.db_path))
            self.builder = WorldBuilder(
                llm=self.llm_client,
                gm=self.gm,
                num_episodes=0,
                world_frame_path=get_world_frame_path(self.db_path),
            )
        console.log(f"BuilderInterface ready (world: {self.builder.world_frame and self.builder.world_frame.get('world_name', '?') or 'no frame yet'})")

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()

    def create_world(self) -> dict:
        console.log("Creating world from scratch...")
        return self._run_async(self.builder.create_world())

    def build_L1(self):
        return self.create_world()

    def build_L2(self):
        console.log("Building L2 details for all entities...")
        self._run_async(self.builder.build_L2())

    def build_L3(self):
        console.log("Building L3 secrets for all entities...")
        self._run_async(self.builder.build_L3())

    def complete_relationships(self):
        """Generate missing relationships for all entities (idempotent)."""
        console.log("Generating missing relationships...")
        self._run_async(self.builder.build_relationships())

    def complete_entity(self, uid: str, target_layer: str = "l2"):
        """
        Generate missing layer (L2 or L3) for a single entity.
        The shared store is updated directly; no reload needed.
        """
        node = self.gm.store.get(uid)
        if not node:
            raise ValueError(f"Entity {uid} not found")

        console.log(f"Completing {target_layer.upper()} for [bold]{uid}[/]...")
        rules_summary = "\n".join(
            f"- {r['name']}: {r['description']}" for r in self.builder.world_frame.get("world_rules", [])
        ) if self.builder.world_frame else ""

        all_nodes = self.gm.store.all_nodes()
        existing_names = ", ".join(n.name for n in all_nodes)

        sem = asyncio.Semaphore(1)

        async def _do():
            async with sem:
                if target_layer == "l2":
                    if node.profile.l2:
                        console.log(f"  L2 already exists for {uid}")
                        return
                    console.log(f"  Generating L2 for {uid}...")
                    await self.builder._build_L2_for_node(node, rules_summary, existing_names, sem)
                elif target_layer == "l3":
                    if not node.profile.l2:
                        raise ValueError("L2 must exist before generating L3")
                    if node.profile.l3:
                        console.log(f"  L3 already exists for {uid}")
                        return
                    console.log(f"  Generating L3 for {uid}...")
                    await self.builder._build_L3_for_node(node, sem)
                else:
                    raise ValueError("target_layer must be 'l2' or 'l3'")
        self._run_async(_do())
        console.log(f"  [green]Done[/]")
        return node

    def add_npc(self, faction_or_race: str):
        console.log(f"Adding NPC for {faction_or_race}...")
        return self._run_async(self.builder.add_npc(faction_or_race))

    def add_item(self, item_type: str, rarity: str = "uncommon"):
        console.log(f"Adding {rarity} {item_type}...")
        return self._run_async(self.builder.add_item(item_type, rarity))

    def add_faction(self):
        console.log("Adding faction...")
        return self._run_async(self.builder.add_faction())

    def add_location(self):
        console.log("Adding location...")
        return self._run_async(self.builder.add_location())

    def add_event(self):
        console.log("Adding event...")
        return self._run_async(self.builder.add_event())

    def add_rule(self):
        console.log("Adding rule...")
        return self._run_async(self.builder.add_rule())
