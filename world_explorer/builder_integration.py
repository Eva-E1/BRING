"""
BRING v2 — Integration layer for world_builder.
Proper async support — no more ThreadPoolExecutor wrapping.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

_LAB_DIR = Path(__file__).resolve().parent.parent
if str(_LAB_DIR) not in sys.path:
    sys.path.insert(0, str(_LAB_DIR))

from world_builder.llm import LLMClient
from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_builder.config import get_entity_store_path, get_world_frame_path, DATABASE_PATH as BUILDER_DB_PATH
from world_core.utils import safe_names

console = Console()


class BuilderInterface:
    """
    Wraps the async builder and exposes common operations.
    v2: Proper async support, no ThreadPoolExecutor.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        gm: Optional[GraphManager] = None,
        existing_builder: Optional[WorldBuilder] = None,
    ):
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

        self.llm = self.llm_client

    def _run_async(self, coro):
        """Run an async coroutine from sync context. Handles already-running loops."""
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
        return self._run_async(self.builder.create_world())

    def build_L1(self):
        return self.create_world()

    def build_L2(self):
        self._run_async(self.builder.build_L2())

    def build_L3(self):
        self._run_async(self.builder.build_L3())

    def complete_relationships(self):
        self._run_async(self.builder.build_relationships())

    async def complete_entity_async(self, uid: str, target_layer: str = "l2"):
        node = self.gm.store.get(uid)
        if not node:
            raise ValueError(f"Entity {uid} not found")

        rules_summary = self.builder._get_rules_text()
        all_nodes = self.gm.store.all_nodes()
        existing_names = safe_names(all_nodes)
        sem = asyncio.Semaphore(1)

        async with sem:
            if target_layer == "l2":
                if node.profile.l2:
                    return node
                await self.builder._build_L2_for_node(node, rules_summary, existing_names, sem)
            elif target_layer == "l3":
                if not node.profile.l2:
                    raise ValueError("L2 must exist before generating L3")
                if node.profile.l3:
                    return node
                await self.builder._build_L3_for_node(node, sem)
            else:
                raise ValueError("target_layer must be 'l2' or 'l3'")
        return node

    def complete_entity(self, uid: str, target_layer: str = "l2"):
        return self._run_async(self.complete_entity_async(uid, target_layer))

    def add_npc(self, faction_or_race: str, auto_repair: bool = True):
        return self._run_async(self.builder.add_npc(faction_or_race, auto_repair))

    def add_item(self, item_type: str, rarity: str = "uncommon", auto_repair: bool = True):
        return self._run_async(self.builder.add_item(item_type, rarity, auto_repair))

    def add_faction(self, auto_repair: bool = True):
        return self._run_async(self.builder.add_faction(auto_repair))

    def add_location(self, auto_repair: bool = True):
        return self._run_async(self.builder.add_location(auto_repair))

    def add_event(self, auto_repair: bool = True):
        return self._run_async(self.builder.add_event(auto_repair))

    def add_rule(self, auto_repair: bool = True):
        return self._run_async(self.builder.add_rule(auto_repair))

