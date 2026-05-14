from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from world_builder.graph_manager import GraphManager
from world_core.llm_queue import GlobalLLMQueue
from world_director.models import TaskPriority
from world_explorer.store import GraphStore
from .memory_optimized import OptimizedMemoryStore
from .chronicler import Chronicler
from .validation import WorldValidator
from .quest_manager import QuestManager
from .social_sim import SocialSimulator
from .world_clock import WorldClock

logger = logging.getLogger(__name__)

PROMPT = """
You manage a living story world called "{world_name}".
Current story time: {story_time}
Category: {category}
Severity: {severity}
Involved entities: {entities}
Recent timeline:
{timeline}

World rules:
{rules}

Generate a story event (JSON):
{{
    "title": "event title",
    "description": "what happens (2-3 sentences)",
    "category": "incident|discovery|conflict|villain_move|npc_event",
    "involved_entities": ["entity1", "entity2"],
    "effects": [
        {{"type": "npc_move", "entity": "name", "location": "place"}},
        {{"type": "relationship_change", "source": "name1", "target": "name2", "delta": 1, "relationship": "knows"}},
        {{"type": "item_discovery", "item": "item_name", "location": "place"}},
        {{"type": "add_quest", "quest": {{"title": "...", "description": "...", "status": "active"}}}}
    ]
}}
Respond with valid JSON only.
"""


class StoryEngine:
    def __init__(
        self,
        llm_queue: GlobalLLMQueue,
        gm: GraphManager,
        npc_mgr: OptimizedMemoryStore,
        chronicler: Chronicler,
        validator: WorldValidator,
        world_name: str,
        world_rules: List[dict],
        quest_mgr: QuestManager,
        social_sim: SocialSimulator,
        clock: WorldClock,
        graph_store: Optional[GraphStore] = None,
    ):
        self.llm_queue = llm_queue
        self.gm = gm
        self.npc_mgr = npc_mgr
        self.chronicler = chronicler
        self.validator = validator
        self.world_name = world_name
        self.world_rules = world_rules
        self.quest_mgr = quest_mgr
        self.social_sim = social_sim
        self.clock = clock
        self.graph_store = graph_store
        self._villain_clocks: Dict[str, int] = {}
        self._villain_clocks_path = chronicler.log_path.parent / "villain_clocks.json"
        self._recommender = None
        self._rule_checker = None
        self._load_villain_clocks()

    def _get_recommender(self):
        """Lazy initialization of Recommender to avoid circular imports."""
        if self._recommender is None and self.graph_store is not None:
            from world_intelligence.recommender import Recommender
            self._recommender = Recommender(self.graph_store)
        return self._recommender

    def _get_rule_checker(self):
        """Lazy initialization of RuleChecker to avoid circular imports."""
        if self._rule_checker is None and self.graph_store is not None:
            from world_intelligence.rule_checker import RuleChecker
            from world_explorer.builder_integration import BuilderInterface
            try:
                builder = BuilderInterface(gm=self.gm)
                self._rule_checker = RuleChecker(self.graph_store, builder, llm_queue=self.llm_queue)
            except Exception as e:
                logger.warning(f"Could not initialize RuleChecker: {e}")
                self._rule_checker = None
        return self._rule_checker

    def _load_villain_clocks(self):
        if self._villain_clocks_path.exists():
            try:
                with open(self._villain_clocks_path) as f:
                    self._villain_clocks = json.load(f)
            except json.JSONDecodeError:
                self._villain_clocks = {}
        else:
            self._villain_clocks = {}

    def _save_villain_clocks(self):
        self._villain_clocks_path.parent.mkdir(parents=True, exist_ok=True)
        self._villain_clocks_path.write_text(json.dumps(self._villain_clocks, indent=2))

    async def generate_event(
        self,
        story_time: datetime,
        involved_entities: List[str],
        category: str = "incident",
        severity: float = 0.5,
    ) -> dict:
        timeline = await self.chronicler.get_timeline(since=story_time - timedelta(days=7), limit=10)
        timeline_text = "\n".join(f"- {e['description']}" for e in timeline)
        rules_text = "\n".join(f"- {r['name']}: {r['description']}" for r in self.world_rules)

        # Integrate with world_intelligence: Use Recommender to add dynamic involved entities
        enriched_entities = list(involved_entities)
        try:
            recommender = self._get_recommender()
            if recommender:
                suggestions = recommender.suggest_missing_relationships(top_k=3)
                suggested_entities = []
                for s in suggestions:
                    suggested_entities.append(s["source_name"])
                    suggested_entities.append(s["target_name"])
                # Add up to 2 suggested entities that aren't already involved
                for ent in suggested_entities:
                    if len(enriched_entities) >= 4:
                        break
                    if ent not in enriched_entities:
                        enriched_entities.append(ent)
                logger.debug(f"Enriched entities with suggestions: {suggested_entities[:2]}")
        except Exception as e:
            logger.warning(f"Intelligence integration failed: {e}")

        prompt = PROMPT.format(
            world_name=self.world_name,
            story_time=story_time.isoformat(),
            category=category,
            severity=severity,
            entities=", ".join(enriched_entities),
            timeline=timeline_text,
            rules=rules_text,
        )
        try:
            result = await self.llm_queue.generate_json(
                prompt, priority=TaskPriority.LOW, temperature=0.8
            )
            # Ensure involved_entities includes our enriched set
            if "involved_entities" not in result:
                result["involved_entities"] = enriched_entities
            else:
                # Merge and deduplicate
                combined = set(result["involved_entities"]) | set(enriched_entities)
                result["involved_entities"] = list(combined)
            return result
        except Exception as e:
            logger.warning(f"Event generation failed: {e}")
            return {
                "title": "Routine incident",
                "description": "Nothing remarkable happens.",
                "category": "incident",
                "involved_entities": enriched_entities,
                "effects": [],
            }

    async def apply_effects(self, effects: List[dict], story_time: datetime, involved_entities: Optional[List[str]] = None) -> None:
        """Apply effects from an event to the world state."""
        for eff in effects:
            etype = eff.get("type")
            try:
                if etype == "npc_move":
                    name = eff["entity"]
                    loc = eff["location"]
                    await self.npc_mgr.move(name, loc, story_time)
                    # Update entity's L2 current_location in the graph
                    node = self.gm.store.get_by_name_and_type(name, "Character")
                    if node:
                        l2 = node.profile.l2
                        l2["current_location"] = loc
                        self.gm.store.update_entity_level(node.uid, "l2", l2)
                        await self.gm.add_entity(node.name, node.entity_type, node.profile, node.group_id)
                    await self.chronicler.log_event(f"{name} moved to {loc}", story_time)

                elif etype == "villain_progress":
                    villain = eff["villain"]
                    delta = eff.get("clock_delta", 1)
                    self._villain_clocks[villain] = self._villain_clocks.get(villain, 0) + delta
                    self._save_villain_clocks()

                elif etype == "relationship_change":
                    source = eff["source"]
                    target = eff["target"]
                    delta = int(eff.get("delta", 0))
                    rel_type = eff.get("relationship", "knows")

                    # Update graph edge strength (store in attributes)
                    if self.graph_store:
                        G = self.graph_store.get_active_graph()
                        if G.has_edge(source, target):
                            # Update existing edge strength
                            edge_data = G.edges[source, target]
                            current_strength = edge_data.get("strength", 0)
                            G.edges[source, target]["strength"] = current_strength + delta
                        else:
                            # Add new edge – use keyword arguments, NOT positional
                            G.add_edge(source, target, type=rel_type, strength=delta)
                        # Persist graph changes to entities
                        self.graph_store.save_graph()

                    await self.chronicler.log_event(
                        f"Relationship {source}↔{target} changed by {delta} ({rel_type})",
                        story_time
                    )

                elif etype == "item_discovery":
                    item_name = eff["item"]
                    location = eff.get("location", "unknown")
                    # Register item in NPCManager inventory of discoverer
                    discoverer = involved_entities[0] if involved_entities else "unknown"
                    await self.npc_mgr.add_item(discoverer, item_name)
                    await self.chronicler.log_event(f"{discoverer} discovered {item_name} at {location}", story_time)

                elif etype == "item_condition":
                    item_name = eff["item"]
                    condition = eff["condition"]
                    # Store condition in items.json (simplified: just log for now)
                    await self.chronicler.log_event(f"{item_name} is now {condition}", story_time)

                elif etype == "item_move":
                    item_name = eff["item"]
                    location = eff["location"]
                    # Move item in world (simplified: just log)
                    await self.chronicler.log_event(f"{item_name} moved to {location}", story_time)

                elif etype == "add_quest":
                    quest_data = eff.get("quest", {})
                    if quest_data:
                        from .quest_manager import Quest
                        # Generate missing fields
                        if "id" not in quest_data:
                            quest_data["id"] = str(uuid4())
                        if "giver" not in quest_data:
                            # Try to get from involved entities
                            quest_data["giver"] = involved_entities[0] if involved_entities else "Unknown"
                        if "objectives" not in quest_data:
                            # Create a simple objective from the description
                            quest_data["objectives"] = [{
                                "type": "complete",
                                "target": quest_data.get("description", ""),
                                "completed": False
                            }]
                        quest = Quest(**quest_data)
                        self.quest_mgr.add_quest(quest)
                        await self.chronicler.log_event(f"New quest: {quest.title}", story_time)

                elif etype == "npc_mood":
                    await self.npc_mgr.set_mood(eff["entity"], eff["mood"])

                elif etype == "npc_health":
                    await self.npc_mgr.adjust_health(eff["entity"], eff["delta"])

                elif etype == "add_goal":
                    await self.npc_mgr.add_goal(eff["entity"], eff["goal"])

                elif etype == "record_incident":
                    await self.chronicler.log_event(eff["label"], story_time)

                else:
                    logger.debug(f"Unknown effect type: {etype}")

            except Exception as e:
                logger.error(f"Failed to apply effect {eff}: {e}")

    async def tick(
        self,
        story_time: datetime,
        involved_entities: Optional[List[str]] = None,
        severity: float = 0.5,
    ) -> dict:
        # Advance world clock
        await self.clock.tick(10)  # 10 minutes per story tick

        # Run social simulation (probability based)
        if random.random() < 0.2:
            await self.social_sim.simulate_turn(story_time)

        if random.random() < 0.45:
            event = await self.generate_event(
                story_time,
                involved_entities or [],
                "incident",
                severity
            )
            await self.apply_effects(event.get("effects", []), story_time, event.get("involved_entities", []))
            await self.chronicler.log_event(event["description"], story_time, group="story_events")
            next_time = story_time + timedelta(minutes=60)

            # Check rule violations after large events
            try:
                rule_checker = self._get_rule_checker()
                if rule_checker and event.get("severity", 0) >= 0.7:
                    affected_entities = event.get("involved_entities", [])
                    # For now, run full check on all entities (can be optimized later)
                    conflicts = await rule_checker.check_all_async(auto_fix=False)
                    if conflicts:
                        logger.info(f"Found {len(conflicts)} rule conflicts after event: {event.get('title')}")
            except Exception as e:
                logger.warning(f"Rule checking failed: {e}")

            return {"event": event, "next_story_time": next_time}

        return {"event": None, "next_story_time": story_time + timedelta(minutes=30)}
