"""Orchestrate layered world building – rule‑first, modular, entity‑centric."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .llm import LLMClient
from .generator import WorldGenerator, _safe_names
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
    ):
        self.llm = llm
        self.gm = gm
        self.gen = WorldGenerator(llm)
        self.num_episodes = num_episodes
        self._world_frame_path = world_frame_path or DEFAULT_WORLD_FRAME_PATH
        if world_frame:
            self.world_frame = world_frame
        elif self._world_frame_path.exists():
            with open(self._world_frame_path) as f:
                self.world_frame = json.load(f)
        else:
            self.world_frame = None

    async def _save_world_frame(self):
        if self.world_frame:
            self._world_frame_path.parent.mkdir(parents=True, exist_ok=True)
            self._world_frame_path.write_text(json.dumps(self.world_frame, indent=2))

    def _sanitise_world_frame(self):
        """Ensure all expected lists contain dicts, not plain strings."""
        for key in ("races", "factions", "characters", "locations", "items",
                    "historical_events", "world_rules"):
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
        """Load the already existing world frame and store missing L1 entities."""
        if self.world_frame is None:
            self.world_frame = json.loads(self._world_frame_path.read_text())
            logger.info("Loaded existing world frame.")

        # Ensure L1 entities exist for every item in the frame.
        # This is idempotent – if an entity already exists it will be updated.
        logger.info("Re‑storing L1 entities (skips already present ones)...")
        await self._build_L1()
        await self._save_world_frame()
        return self.world_frame

    # ── Phase 1: World frame & L1 ─────────────────────
    async def create_world(self) -> dict:
        """Generate world frame, sanitise, store L1 for all entities."""
        try:
            self.world_frame = await self.gen.generate_world_frame()
        except Exception as e:
            raise RuntimeError(f"Failed to generate world frame: {e}") from e

        self._sanitise_world_frame()
        await self._build_L1()
        await self._save_world_frame()
        return self.world_frame

    async def _store_L1(self, name: str, etype: str, group: str,
                        summary: str = "", tags: list = None, extra: dict = None) -> None:
        """Create and persist L1 profile (awaited)."""
        profile = LayeredProfile(
            l1={"name": name, "type": etype, "group": group,
                "summary": summary, "tags": tags or [],
                "relationships": [], **(extra or {})},
            l2={}, l3={}
        )
        await self.gm.add_entity(name, etype, profile, group_id=group)

    async def _build_L1(self):
        """Store L1 for every entity derived from the world frame."""
        logger.info("📊 Building Level 1 (classification) for all entities...")
        start = time.time()

        for race in self.world_frame.get("races", []):
            await self._store_L1(race["name"], "Race", "races",
                                 summary=race.get("traits", ""))
        for fac in self.world_frame.get("factions", []):
            await self._store_L1(fac["name"], "Faction", "factions",
                                 summary=fac.get("goal", ""),
                                 tags=[fac.get("type", "")])
        for ch in self.world_frame.get("characters", []):
            await self._store_L1(ch["name"], "Character", "characters",
                                 summary=ch.get("personality", "")[:100],
                                 tags=[ch.get("race", ""), ch.get("role", "")])
        for loc in self.world_frame.get("locations", []):
            await self._store_L1(loc["name"], "Location", "locations",
                                 summary=loc.get("description", "")[:100],
                                 tags=[loc.get("type", "")])
        for item in self.world_frame.get("items", []):
            await self._store_L1(item["name"], "Item", "items",
                                 summary=item.get("power", "")[:100],
                                 tags=[item.get("type", "")])
        for ev in self.world_frame.get("historical_events", []):
            await self._store_L1(ev["name"], "Event", "events",
                                 summary=ev.get("description", "")[:100])
        for rule in self.world_frame.get("world_rules", []):
            await self._store_L1(rule["name"], "WorldRule", "world_rules",
                                 summary=rule["description"][:200],
                                 tags=[rule.get("category", "")],
                                 extra={"category": rule.get("category", "")})

        elapsed = time.time() - start
        logger.info(f"✅ L1 stored for {len(self.gm.store.all_nodes())} entities in {elapsed:.1f}s")

    # ── Phase 2: Build L2 ─────────────────────────────
    async def build_L2(self):
        """Generate L2 details for all entities that miss them (resumable)."""
        logger.info("📖 Building Level 2 (details) for entities (this may take a while)...")
        rules_summary = self._get_rules_text()
        all_nodes = self.gm.store.all_nodes()
        existing_names = ", ".join(n.name for n in all_nodes)

        sem = asyncio.Semaphore(4)
        tasks = []
        for node in all_nodes:
            if node.profile.l2:  # already has L2
                continue
            tasks.append(self._build_L2_for_node(node, rules_summary, existing_names, sem))

        if not tasks:
            logger.info("✅ All entities already have L2 details.")
            return

        logger.info(f"Generating L2 for {len(tasks)} entities...")
        await asyncio.gather(*tasks)

    async def _build_L2_for_node(self, node: EntityNode, rules_summary: str,
                                 existing_names: str, sem: asyncio.Semaphore):
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
                logger.info(f"  ✔ L2 generated for {etype} '{name}'")
            except Exception as e:
                logger.error(f"  ✖ L2 failed for {etype} '{name}': {e}")

    # ── Phase 3: Build L3 ─────────────────────────────
    async def build_L3(self):
        """Generate L3 secrets for entities that have L2 but miss L3 (resumable)."""
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
        await asyncio.gather(*tasks)

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
                logger.info(f"  ✔ L3 secrets added for {etype} '{name}'")
            except Exception as e:
                logger.error(f"  ✖ L3 failed for {etype} '{name}': {e}")

    # ── Phase 4: Build Relationships ───────────────────
    async def build_relationships(self):
        """
        Generate rich relationships between entities that have L2 data.
        Updates L1 relationships for each entity. Idempotent (skips if already done).
        """
        logger.info("🔗 Building relationships...")
        all_nodes = self.gm.store.all_nodes()
        # Filter out entities that already have relationships
        nodes_without_rel = [n for n in all_nodes if not n.profile.l1.get("relationships")]
        if not nodes_without_rel:
            logger.info("✅ All entities already have relationships.")
            return

        # Prepare the entity list for the prompt
        entity_descriptions = []
        for n in all_nodes:
            l1 = n.profile.l1
            summary = l1.get("summary", "") or ""
            entity_descriptions.append(f"- {n.uid} ({n.entity_type}): {summary}")
        entities_text = "\n".join(entity_descriptions)

        sem = asyncio.Semaphore(1)   # one LLM call for all relationships
        async def _generate():
            async with sem:
                prompt = PROMPTS["relationships"].format(entities_list=entities_text)
                response = await self.gen.llm.generate_json(prompt)
                # response is expected to be a list of relationship dicts
                if isinstance(response, list):
                    # Apply each relationship to the involved entities
                    for rel in response:
                        src_uid = rel.get("source")
                        tgt_uid = rel.get("target")
                        rel_type = rel.get("type", "related")
                        src_node = self.gm.store.get(src_uid)
                        tgt_node = self.gm.store.get(tgt_uid)
                        if src_node and tgt_node:
                            # Add to source's L1 relationships if not already present
                            existing_rels = src_node.profile.l1.setdefault("relationships", [])
                            if not any(r["target"] == tgt_uid for r in existing_rels):
                                existing_rels.append({"target": tgt_uid, "type": rel_type})
                                self.gm.store.save()  # will be saved at end anyway
                            # Also add the inverse relationship for tgt? We can handle that later through graph inference.
                        else:
                            logger.warning(f"Invalid relationship source/target: {rel}")
                    # Save all updates
                    self.gm.store.save()
                    logger.info(f"  ✔ Added relationships from LLM response.")
                else:
                    logger.error("Relationships response was not a list")
        await _generate()
        logger.info("✅ Relationships built.")

    # ── Narrative episodes (with progress callback) ──
    async def add_narrative_episodes(self, progress_callback: Optional[Callable] = None) -> None:
        if not self.world_frame:
            raise RuntimeError("World must be created first.")
        rules = self._get_rules_text()
        sem = asyncio.Semaphore(4)

        async def create_scene(idx: int):
            try:
                char_names = []
                for c in self.world_frame.get("characters", []):
                    if isinstance(c, dict):
                        char_names.append(c.get("name", str(c)))
                    else:
                        char_names.append(str(c))
                chars = random.sample(char_names, k=min(3, len(char_names)))
                loc = random.choice(self.world_frame["locations"])
                loc_name = loc.get("name", str(loc)) if isinstance(loc, dict) else str(loc)
                context = f"Characters: {', '.join(chars)}\nLocation: {loc_name}\n"
                async with sem:
                    await self.gen.generate_scene(self.world_frame["world_name"], rules, context)
                logger.info(f"Scene {idx+1} generated")
            except Exception as e:
                logger.error(f"Episode {idx+1} generation failed: {e}")
            finally:
                if progress_callback:
                    progress_callback()

        tasks = [create_scene(i) for i in range(self.num_episodes)]
        await asyncio.gather(*tasks)

    # ── Add single entity methods (L1 + L2 + L3) ─────
    async def add_npc(self, faction_or_race: str) -> EntityNode:
        if not self.world_frame: raise RuntimeError("World must be created first.")
        existing_chars = [c if isinstance(c, str) else c["name"] for c in self.world_frame["characters"]]
        existing_names_str = ", ".join(existing_chars)
        rules = self._get_rules_text()
        l1 = {"name": f"NPC_{faction_or_race}_{random.randint(100,999)}",
              "type": "Character", "group": faction_or_race,
              "summary": "Newly created NPC", "tags": [], "relationships": []}
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Character", profile, group_id="characters")
        # L2
        l2 = await self.gen.expand_character_L2(l1, rules, existing_names_str)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        # L3
        l3 = await self.gen.expand_character_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("characters", []).append({"name": l1["name"]})
        await self._save_world_frame()
        return node

    async def add_item(self, item_type: str, rarity: str = "uncommon") -> EntityNode:
        if not self.world_frame: raise RuntimeError("World must be created first.")
        l1 = {"name": f"{item_type.capitalize()}_{random.randint(100,999)}",
              "type": "Item", "group": "items",
              "summary": f"{rarity} {item_type}", "tags": [item_type, rarity], "relationships": []}
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Item", profile, group_id="items")
        magic_rules = self.world_frame.get("magic_system", {}).get("rules", "")
        existing_names = _safe_names(self.gm.store.all_nodes())
        l2 = await self.gen.expand_item_L2(l1, magic_rules, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_item_L3(l1, l2, magic_rules)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("items", []).append({"name": l1["name"]})
        await self._save_world_frame()
        return node

    async def add_faction(self) -> EntityNode:
        if not self.world_frame: raise RuntimeError("World must be created first.")
        existing_names = _safe_names(self.gm.store.all_nodes())
        l1 = {"name": f"Faction_{random.randint(100,999)}",
              "type": "Faction", "group": "factions",
              "summary": "Newly created faction", "tags": [], "relationships": []}
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Faction", profile, group_id="factions")
        l2 = await self.gen.expand_faction_L2(l1, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_faction_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("factions", []).append({"name": l1["name"]})
        await self._save_world_frame()
        return node

    async def add_location(self) -> EntityNode:
        if not self.world_frame: raise RuntimeError("World must be created first.")
        rules_summary = self._get_rules_text()
        existing_names = _safe_names(self.gm.store.all_nodes())
        l1 = {"name": f"Location_{random.randint(100,999)}",
              "type": "Location", "group": "locations",
              "summary": "Newly created location", "tags": [], "relationships": []}
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Location", profile, group_id="locations")
        l2 = await self.gen.expand_location_L2(l1, rules_summary, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_location_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("locations", []).append({"name": l1["name"]})
        await self._save_world_frame()
        return node

    async def add_event(self) -> EntityNode:
        if not self.world_frame: raise RuntimeError("World must be created first.")
        existing_names = _safe_names(self.gm.store.all_nodes())
        l1 = {"name": f"Event_{random.randint(100,999)}",
              "type": "Event", "group": "events",
              "summary": "Newly created event", "tags": [], "relationships": []}
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "Event", profile, group_id="events")
        l2 = await self.gen.expand_event_L2(l1, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_event_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("historical_events", []).append({"name": l1["name"]})
        await self._save_world_frame()
        return node

    async def add_rule(self) -> EntityNode:
        if not self.world_frame: raise RuntimeError("World must be created first.")
        existing_names = _safe_names(self.gm.store.all_nodes())
        l1 = {"name": f"Rule_{random.randint(100,999)}",
              "type": "WorldRule", "group": "world_rules",
              "summary": "Newly created rule", "tags": [], "relationships": []}
        profile = LayeredProfile(l1=l1, l2={}, l3={})
        node = await self.gm.add_entity(l1["name"], "WorldRule", profile, group_id="world_rules")
        l2 = await self.gen.expand_rule_L2(l1, existing_names)
        self.gm.store.update_entity_level(node.uid, "l2", l2)
        l3 = await self.gen.expand_rule_L3(l1, l2)
        self.gm.store.update_entity_level(node.uid, "l3", l3)
        self.world_frame.setdefault("world_rules", []).append({"name": l1["name"]})
        await self._save_world_frame()
        return node

    def _get_rules_text(self) -> str:
        if not self.world_frame: return ""
        return "\n".join(f"- {r['name']}: {r['description']}" for r in self.world_frame.get("world_rules", []))
