"""
BRING v2 — Orchestrate layered world building.
Batch saves, proper async semaphore usage, and idempotent operations.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from world_core.models import WorldFrame
from world_core.utils import atomic_write_json, safe_names, atomic_read_json
from world_core.event_bus import EventBus, EventTopic, Event, get_event_bus

from .llm import LLMClient
from .generator import WorldGenerator
from .graph_manager import GraphManager
from .entity_profile import LayeredProfile, EntityNode
from .config import DEFAULT_WORLD_FRAME_PATH
from .prompts import PROMPTS

logger = logging.getLogger(__name__)


class WorldBuilder:
    def __init__(
        self,
        llm: LLMClient,
        gm: GraphManager,
        num_episodes: int = 10,
        world_frame: Optional[dict] = None,
        world_frame_path: Optional[Path] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self.llm = llm
        self.gm = gm
        self.gen = WorldGenerator(llm)
        self.num_episodes = num_episodes
        self._world_frame_path = world_frame_path or DEFAULT_WORLD_FRAME_PATH
        self._bus = event_bus or get_event_bus()

        if world_frame:
            self.world_frame = world_frame
        elif self._world_frame_path.exists():
            data = atomic_read_json(self._world_frame_path)
            self.world_frame = data if data else None
        else:
            self.world_frame = None

    async def _save_world_frame(self):
        if self.world_frame:
            atomic_write_json(self._world_frame_path, self.world_frame)

    def _sanitise_world_frame(self):
        """Ensure all expected lists contain dicts, not plain strings."""
        for key in (
            "races", "factions", "characters", "locations",
            "items", "historical_events", "world_rules",
        ):
            lst = self.world_frame.get(key, [])
            if not isinstance(lst, list):
                self.world_frame[key] = []
                continue
            for i, item in enumerate(lst):
                if isinstance(item, str):
                    self.world_frame[key][i] = {"name": item}
                elif isinstance(item, dict):
                    if "name" not in item:
                        item["name"] = f"Unnamed_{key}_{i}"
                else:
                    self.world_frame[key][i] = {"name": str(item)}

    async def load_existing_world(self) -> dict:
        if self.world_frame is None:
            data = atomic_read_json(self._world_frame_path)
            if data is None:
                raise FileNotFoundError(f"World frame not found: {self._world_frame_path}")
            self.world_frame = data
        logger.info("Loaded existing world frame.")
        await self._build_L1()
        await self._save_world_frame()
        return self.world_frame

    # ── Phase 1: World frame & L1 ─────────────────────

    async def create_world(self) -> dict:
        try:
            self.world_frame = await self.gen.generate_world_frame()
        except Exception as e:
            raise RuntimeError(f"Failed to generate world frame: {e}") from e

        self._sanitise_world_frame()
        await self._build_L1()
        await self._save_world_frame()

        await self._bus.publish_simple(
            EventTopic.WORLD_CREATED,
            {"world_name": self.world_frame.get("world_name", "")},
            source="world_builder",
        )
        return self.world_frame

    async def _store_L1(
        self,
        name: str,
        etype: str,
        group: str,
        summary: str = "",
        tags: list = None,
        extra: dict = None,
    ) -> None:
        profile = LayeredProfile(
            l1={
                "name": name,
                "type": etype,
                "group": group,
                "summary": summary,
                "tags": tags or [],
                "relationships": [],
                **(extra or {}),
            },
            l2={},
            l3={},
        )
        await self.gm.add_entity(name, etype, profile, group_id=group)

    async def _build_L1(self):
        logger.info("📊 Building Level 1 (classification) for all entities...")
        start = time.time()

        # Batch: disable auto-save during L1 build
        self.gm.store.unified.auto_save = False
        try:
            for race in self.world_frame.get("races", []):
                await self._store_L1(
                    race["name"], "Race", "races", summary=race.get("traits", "")
                )
            for fac in self.world_frame.get("factions", []):
                await self._store_L1(
                    fac["name"], "Faction", "factions",
                    summary=fac.get("goal", ""),
                    tags=[fac.get("type", "")],
                )
            for ch in self.world_frame.get("characters", []):
                await self._store_L1(
                    ch["name"], "Character", "characters",
                    summary=ch.get("personality", "")[:100],
                    tags=[ch.get("race", ""), ch.get("role", "")],
                )
            for loc in self.world_frame.get("locations", []):
                await self._store_L1(
                    loc["name"], "Location", "locations",
                    summary=loc.get("description", "")[:100],
                    tags=[loc.get("type", "")],
                )
            for item in self.world_frame.get("items", []):
                await self._store_L1(
                    item["name"], "Item", "items",
                    summary=item.get("power", "")[:100],
                    tags=[item.get("type", "")],
                )
            for ev in self.world_frame.get("historical_events", []):
                await self._store_L1(
                    ev["name"], "Event", "events",
                    summary=ev.get("description", "")[:100],
                )
            for rule in self.world_frame.get("world_rules", []):
                await self._store_L1(
                    rule["name"], "WorldRule", "world_rules",
                    summary=rule["description"][:200],
                    tags=[rule.get("category", "")],
                    extra={"category": rule.get("category", "")},
                )
        finally:
            # Single save at the end
            self.gm.store.unified.auto_save = True
            self.gm.store.unified.save()

        elapsed = time.time() - start
        logger.info(f"✅ L1 stored for {self.gm.store.unified.count()} entities in {elapsed:.1f}s")

    # ── Phase 2: Build L2 ─────────────────────────────

    async def build_L2(self):
        logger.info("📖 Building Level 2 (details)...")
        rules_summary = self._get_rules_text()
        all_nodes = self.gm.store.all_nodes()
        existing_names = safe_names(all_nodes)
        sem = asyncio.Semaphore(4)
        tasks = []

        for node in all_nodes:
            if node.profile.l2:
                continue
            tasks.append(self._build_L2_for_node(node, rules_summary, existing_names, sem))

        if not tasks:
            logger.info("✅ All entities already have L2 details.")
            return

        logger.info(f"Generating L2 for {len(tasks)} entities...")

        # Batch save
        self.gm.store.unified.auto_save = False
        try:
            await asyncio.gather(*tasks)
        finally:
            self.gm.store.unified.auto_save = True
            self.gm.store.unified.save()

    async def _build_L2_for_node(
        self,
        node: EntityNode,
        rules_summary: str,
        existing_names: str,
        sem: asyncio.Semaphore,
    ):
        async with sem:
            etype = node.entity_type
            l1 = node.profile.l1
            name = node.name
            try:
                if etype == "Character":
                    l2 = await self.gen.expand_character_L2(l1, rules_summary, existing_names)
                elif etype == "Location":
                    l2 = await self.gen.expand_location_L2(l1, rules_summary, existing_names)
                elif etype == "Item":
                    magic_rules = self.world_frame.get("magic_system", {}).get("rules", "")
                    l2 = await self.gen.expand_item_L2(l1, magic_rules, existing_names)
                elif etype == "Event":
                    l2 = await self.gen.expand_event_L2(l1, existing_names)
                elif etype == "Faction":
                    l2 = await self.gen.expand_faction_L2(l1, existing_names)
                elif etype == "WorldRule":
                    l2 = await self.gen.expand_rule_L2(l1, existing_names)
                else:
                    l2 = {}
                self.gm.store.update_entity_level(node.uid, "l2", l2)
                logger.info(f" ✔ L2 generated for {etype} '{name}'")

                await self._bus.publish_simple(
                    EventTopic.ENTITY_LAYER_COMPLETED,
                    {"uid": node.uid, "layer": "l2"},
                    source="world_builder",
                )
            except Exception as e:
                logger.error(f" ✖ L2 failed for {etype} '{name}': {e}")

    # ── Phase 3: Build L3 ─────────────────────────────

    async def build_L3(self):
        logger.info("🔒 Building Level 3 (secrets)...")
        all_nodes = self.gm.store.all_nodes()
        sem = asyncio.Semaphore(4)
        tasks = []

        for node in all_nodes:
            if not node.profile.l2 or node.profile.l3:
                continue
            tasks.append(self._build_L3_for_node(node, sem))

        if not tasks:
            logger.info("✅ All entities already have L3 secrets.")
            return

        logger.info(f"Generating L3 for {len(tasks)} entities...")

        self.gm.store.unified.auto_save = False
        try:
            await asyncio.gather(*tasks)
        finally:
            self.gm.store.unified.auto_save = True
            self.gm.store.unified.save()

    async def _build_L3_for_node(self, node: EntityNode, sem: asyncio.Semaphore):
        async with sem:
            etype = node.entity_type
            l1 = node.profile.l1
            l2 = node.profile.l2
            name = node.name
            try:
                if etype == "Character":
                    l3 = await self.gen.expand_character_L3(l1, l2)
                elif etype == "Location":
                    l3 = await self.gen.expand_location_L3(l1, l2)
                elif etype == "Item":
                    magic_rules = self.world_frame.get("magic_system", {}).get("rules", "")
                    l3 = await self.gen.expand_item_L3(l1, l2, magic_rules)
                elif etype == "Event":
                    l3 = await self.gen.expand_event_L3(l1, l2)
                elif etype == "Faction":
                    l3 = await self.gen.expand_faction_L3(l1, l2)
                elif etype == "WorldRule":
                    l3 = await self.gen.expand_rule_L3(l1, l2)
                else:
                    l3 = {}
                self.gm.store.update_entity_level(node.uid, "l3", l3)
                logger.info(f" ✔ L3 secrets added for {etype} '{name}'")

                await self._bus.publish_simple(
                    EventTopic.ENTITY_LAYER_COMPLETED,
                    {"uid": node.uid, "layer": "l3"},
                    source="world_builder",
                )
            except Exception as e:
                logger.error(f" ✖ L3 failed for {etype} '{name}': {e}")

    # ── Phase 4: Build Relationships ───────────────────

    async def build_relationships(self):
        logger.info("🔗 Building relationships...")
        all_nodes = self.gm.store.all_nodes()
        nodes_without_rel = [
            n for n in all_nodes if not n.profile.l1.get("relationships")
        ]
        if not nodes_without_rel:
            logger.info("✅ All entities already have relationships.")
            return

        entity_descriptions = []
        for n in all_nodes:
            summary = n.profile.l1.get("summary", "") or ""
            entity_descriptions.append(f"- {n.uid} ({n.entity_type}): {summary}")
        entities_text = "\n".join(entity_descriptions)

        prompt = PROMPTS["relationships"].format(entities_list=entities_text)
        response = await self.gen.llm.generate_json(prompt)

        if isinstance(response, list):
            self.gm.store.unified.auto_save = False
            try:
                for rel in response:
                    src_uid = rel.get("source")
                    tgt_uid = rel.get("target")
                    rel_type = rel.get("type", "related")
                    src_node = self.gm.store.get(src_uid)
                    tgt_node = self.gm.store.get(tgt_uid)
                    if src_node and tgt_node:
                        existing_rels = src_node.profile.l1.setdefault("relationships", [])
                        if not any(r["target"] == tgt_uid for r in existing_rels):
                            existing_rels.append({"target": tgt_uid, "type": rel_type})
                    else:
                        logger.warning(f"Invalid relationship source/target: {rel}")
            finally:
                self.gm.store.unified.auto_save = True
                self.gm.store.unified.save()

            await self._bus.publish_simple(
                EventTopic.RELATIONSHIP_ADDED,
                {"count": len(response)},
                source="world_builder",
            )
        else:
            logger.error("Relationships response was not a list")

        logger.info("✅ Relationships built.")

    # ── Narrative episodes ──

    async def add_narrative_episodes(
        self, progress_callback: Optional[Callable] = None
    ) -> None:
        if not self.world_frame:
            raise RuntimeError("World must be created first.")
        rules = self._get_rules_text()
        sem = asyncio.Semaphore(4)

        async def create_scene(idx: int):
            try:
                char_names = []
                for c in self.world_frame.get("characters", []):
                    char_names.append(c.get("name", str(c)) if isinstance(c, dict) else str(c))
                chars = random.sample(char_names, k=min(3, len(char_names)))
                loc = random.choice(self.world_frame["locations"])
                loc_name = loc.get("name", str(loc)) if isinstance(loc, dict) else str(loc)
                context = f"Characters: {', '.join(chars)}\nLocation: {loc_name}\n"
                async with sem:
                    await self.gen.generate_scene(
                        self.world_frame["world_name"], rules, context
                    )
                logger.info(f"Scene {idx+1} generated")
            except Exception as e:
                logger.error(f"Episode {idx+1} generation failed: {e}")
            finally:
                if progress_callback:
                    progress_callback()

        tasks = [create_scene(i) for i in range(self.num_episodes)]
        await asyncio.gather(*tasks)

    # ── Add single entity methods ──

    async def add_npc(self, faction_or_race: str, auto_repair: bool = True) -> EntityNode:
        if not self.world_frame:
            raise RuntimeError("World must be created first.")
        existing_names = safe_names(self.gm.store.all_nodes())
        rules = self._get_rules_text()
        l1 = {
            "name": f"NPC_{faction_or_race}_{random.randint(100, 999)}",
            "type": "Character",
            "group": faction_or_race,
            "summary": "Newly created NPC",
            "tags": [],
            "relationships": [],
        }
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Character", profile, group_id="characters")
        l2 = await self.gen.expand_character_L2(l1, rules, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_character_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("characters", []).append({"name": l1["name"]})
        await self._save_world_frame()

        await self._bus.publish_simple(
            EventTopic.ENTITY_ADDED,
            {"uid": node.uid, "type": "Character"},
            source="world_builder",
        )

        if auto_repair:
            await self.repair_relationships(intelligent=True)
        return node

    async def add_item(
        self, item_type: str, rarity: str = "uncommon", auto_repair: bool = True
    ) -> EntityNode:
        if not self.world_frame:
            raise RuntimeError("World must be created first.")
        l1 = {
            "name": f"{item_type.capitalize()}_{random.randint(100, 999)}",
            "type": "Item",
            "group": "items",
            "summary": f"{rarity} {item_type}",
            "tags": [item_type, rarity],
            "relationships": [],
        }
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Item", profile, group_id="items")
        magic_rules = self.world_frame.get("magic_system", {}).get("rules", "")
        existing_names = safe_names(self.gm.store.all_nodes())
        l2 = await self.gen.expand_item_L2(l1, magic_rules, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_item_L3(l1, l2, magic_rules)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("items", []).append({"name": l1["name"]})
        await self._save_world_frame()
        if auto_repair:
            await self.repair_relationships(intelligent=True)
        return node

    async def add_faction(self, auto_repair: bool = True) -> EntityNode:
        if not self.world_frame:
            raise RuntimeError("World must be created first.")
        existing_names = safe_names(self.gm.store.all_nodes())
        l1 = {
            "name": f"Faction_{random.randint(100, 999)}",
            "type": "Faction",
            "group": "factions",
            "summary": "Newly created faction",
            "tags": [],
            "relationships": [],
        }
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Faction", profile, group_id="factions")
        l2 = await self.gen.expand_faction_L2(l1, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_faction_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("factions", []).append({"name": l1["name"]})
        await self._save_world_frame()
        if auto_repair:
            await self.repair_relationships(intelligent=True)
        return node

    async def add_location(self, auto_repair: bool = True) -> EntityNode:
        if not self.world_frame:
            raise RuntimeError("World must be created first.")
        rules_summary = self._get_rules_text()
        existing_names = safe_names(self.gm.store.all_nodes())
        l1 = {
            "name": f"Location_{random.randint(100, 999)}",
            "type": "Location",
            "group": "locations",
            "summary": "Newly created location",
            "tags": [],
            "relationships": [],
        }
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Location", profile, group_id="locations")
        l2 = await self.gen.expand_location_L2(l1, rules_summary, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_location_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("locations", []).append({"name": l1["name"]})
        await self._save_world_frame()
        if auto_repair:
            await self.repair_relationships(intelligent=True)
        return node

    async def add_event(self, auto_repair: bool = True) -> EntityNode:
        if not self.world_frame:
            raise RuntimeError("World must be created first.")
        existing_names = safe_names(self.gm.store.all_nodes())
        l1 = {
            "name": f"Event_{random.randint(100, 999)}",
            "type": "Event",
            "group": "events",
            "summary": "Newly created event",
            "tags": [],
            "relationships": [],
        }
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Event", profile, group_id="events")
        l2 = await self.gen.expand_event_L2(l1, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_event_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("historical_events", []).append({"name": l1["name"]})
        await self._save_world_frame()
        if auto_repair:
            await self.repair_relationships(intelligent=True)
        return node

    async def add_rule(self, auto_repair: bool = True) -> EntityNode:
        if not self.world_frame:
            raise RuntimeError("World must be created first.")
        existing_names = safe_names(self.gm.store.all_nodes())
        l1 = {
            "name": f"Rule_{random.randint(100, 999)}",
            "type": "WorldRule",
            "group": "world_rules",
            "summary": "Newly created rule",
            "tags": [],
            "relationships": [],
        }
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "WorldRule", profile, group_id="world_rules")
        l2 = await self.gen.expand_rule_L2(l1, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_rule_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("world_rules", []).append({"name": l1["name"]})
        await self._save_world_frame()
        if auto_repair:
            await self.repair_relationships(intelligent=True)
        return node

    async def repair_relationships(self, intelligent: bool = True) -> dict:
        logger.info("Starting relationship repair...")
        stats = await self.gm.repair_all_relationships(intelligent=intelligent)
        logger.info(f"Repair complete: {stats}")
        return stats

    def _get_rules_text(self) -> str:
        if not self.world_frame:
            return ""
        return "\n".join(
            f"- {r['name']}: {r['description']}"
            for r in self.world_frame.get("world_rules", [])
        )

