"""Simulates complex NPC interactions: betrayals, lies, alliances, etc."""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from world_builder.graph_manager import GraphManager
from world_narrative.chronicler import Chronicler
from world_narrative.memory_optimized import OptimizedMemoryStore
from world_builder.llm import LLMClient

logger = logging.getLogger(__name__)


class NPCSimulator:
    def __init__(
        self,
        gm: GraphManager,
        chronicler: Chronicler,
        npc_mgr: OptimizedMemoryStore,
        state_path: Path,
    ):
        self.gm = gm
        self.chronicler = chronicler
        self.npc_mgr = npc_mgr
        self.state_path = state_path
        self.llm = LLMClient()
        self._npc_memories: Dict[str, List[dict]] = {}  # name -> list of memory entries
        self._load()

    def _load(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self._npc_memories = data.get("memories", {})
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load NPC memories: {e}")
                self._npc_memories = {}

    def _save(self):
        data = {"memories": self._npc_memories}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=2))

    async def tick(self, current_time: datetime) -> List[Dict[str, Any]]:
        """Run one turn of NPC social simulation, returning any events."""
        events = []
        # Get all NPCs
        npc_names = list(self.npc_mgr.list_all().keys())
        if len(npc_names) < 2:
            return events

        # 10% chance per tick to generate a complex interaction
        if random.random() < 0.1:
            # Pick two NPCs that are likely to interact (using graph if available)
            pair = self._select_interaction_pair(npc_names)
            if pair:
                event = await self._generate_interaction(pair[0], pair[1], current_time)
                if event:
                    events.append(event)

        # 5% chance to generate a betrayal or lie
        if random.random() < 0.05:
            event = await self._generate_betrayal_event(npc_names, current_time)
            if event:
                events.append(event)

        self._save()
        return events

    def _select_interaction_pair(self, npc_names: List[str]) -> Optional[Tuple[str, str]]:
        """Select two NPCs that have some relationship in the graph (if available)."""
        try:
            G = self.gm.store.get_active_graph()
            relationships = []
            for node in G.nodes:
                node_name = G.nodes[node].get("label", G.nodes[node].get("name", ""))
                if node_name in npc_names:
                    for neighbor in G.adj.get(node, {}):
                        neigh_name = G.nodes[neighbor].get("label", G.nodes[neighbor].get("name", ""))
                        if neigh_name in npc_names and neigh_name != node_name:
                            relationships.append((node_name, neigh_name))
            if relationships:
                return random.choice(relationships)
        except Exception as e:
            logger.debug(f"Could not use graph for NPC selection: {e}")

        # Fallback to random
        if len(npc_names) >= 2:
            return random.sample(npc_names, 2)
        return None

    async def _generate_interaction(
        self, a: str, b: str, current_time: datetime
    ) -> Optional[Dict[str, Any]]:
        """Generate a complex interaction (debate, partnership, rivalry)."""
        interaction_types = ["debate", "alliance", "rivalry", "confession", "argument", "plot_together"]
        itype = random.choice(interaction_types)
        prompt = f"""
Two characters: {a} and {b}.
Generate a short narrative of an interaction where they {itype}.
Return JSON: {{"description": "2-3 sentence narrative", "relationship_change": integer between -3 and 3}}
"""
        try:
            result = await self.llm.generate_json(prompt, temperature=0.8)
            change = result.get("relationship_change", 0)
            desc = result.get("description", f"{a} and {b} interacted.")

            # Store memory for both NPCs
            memory_entry = {
                "timestamp": current_time.isoformat(),
                "other": b,
                "description": desc,
                "type": itype,
                "relationship_change": change,
            }
            self._npc_memories.setdefault(a, []).append(memory_entry)
            memory_entry2 = {**memory_entry, "other": a}
            self._npc_memories.setdefault(b, []).append(memory_entry2)

            # Trim memories to last 20 per NPC
            for name in [a, b]:
                if len(self._npc_memories[name]) > 20:
                    self._npc_memories[name] = self._npc_memories[name][-20:]

            return {
                "type": "npc_interaction",
                "source": a,
                "target": b,
                "description": desc,
                "effects": [{"type": "relationship_change", "source": a, "target": b, "delta": change}],
                "involved_entities": [a, b],
            }
        except Exception as e:
            logger.warning(f"NPC interaction generation failed: {e}")
            return None

    async def _generate_betrayal_event(
        self, npc_names: List[str], current_time: datetime
    ) -> Optional[Dict[str, Any]]:
        """Generate a betrayal or lie event where one NPC deceives another."""
        if len(npc_names) < 2:
            return None
        betrayer, victim = random.sample(npc_names, 2)
        prompt = f"""
{betrayer} decides to deceive {victim}.
Describe a short betrayal (lie, theft of secret, framing, or backstabbing).
Return JSON: {{"description": "2-3 sentences", "outcome_effect": "negative", "severity": 0.0-1.0}}
"""
        try:
            result = await self.llm.generate_json(prompt, temperature=0.8)
            desc = result.get("description", f"{betrayer} betrayed {victim}.")
            severity = result.get("severity", 0.5)

            # Apply negative relationship change
            delta = -int(severity * 5)

            # Store memory
            memory_entry = {
                "timestamp": current_time.isoformat(),
                "other": victim,
                "description": desc,
                "type": "betrayal",
                "relationship_change": delta,
            }
            self._npc_memories.setdefault(betrayer, []).append(memory_entry)

            return {
                "type": "betrayal",
                "source": betrayer,
                "target": victim,
                "description": desc,
                "severity": severity,
                "effects": [
                    {
                        "type": "relationship_change",
                        "source": betrayer,
                        "target": victim,
                        "delta": delta,
                    }
                ],
                "involved_entities": [betrayer, victim],
            }
        except Exception as e:
            logger.warning(f"Betrayal generation failed: {e}")
            return None

    async def get_npc_memory(self, npc_name: str) -> List[dict]:
        """Get all memories for a specific NPC."""
        return self._npc_memories.get(npc_name, [])

    async def get_interaction_history(self, npc_name: str, limit: int = 10) -> List[dict]:
        """Get recent interaction history for an NPC."""
        memories = self._npc_memories.get(npc_name, [])
        return memories[-limit:]

    def get_memories_path(self) -> Path:
        """Return the state file path for external access."""
        return self.state_path
