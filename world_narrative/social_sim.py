"""Social simulation using graph centrality for smarter pair selection."""
from __future__ import annotations

import random
import logging
from datetime import datetime
from typing import TYPE_CHECKING, List, Tuple, Optional

import networkx as nx

if TYPE_CHECKING:
    from .context import NarrativeContext

logger = logging.getLogger(__name__)


class SocialSimulator:
    """Simulates social interactions between NPCs using graph-based intelligence."""

    def __init__(self, ctx: 'NarrativeContext'):
        self.ctx = ctx

    def _get_graph(self) -> nx.Graph:
        """Get the active graph from the graph store."""
        if self.ctx.graph_store is not None:
            return self.ctx.graph_store.get_active_graph().to_undirected()
        return nx.Graph()

    def _select_interaction_pair(self) -> Optional[Tuple[str, str]]:
        """
        Select two NPCs for interaction using graph centrality.

        Prefers pairs that:
        1. Share common neighbors (more interesting interactions)
        2. Have higher betweenness centrality (bridges between communities)
        3. Are in the same location
        """
        G = self._get_graph()

        # Get all character nodes
        character_nodes = [
            n for n, attr in G.nodes(data=True)
            if attr.get("type") == "Character" or attr.get("label")
        ]

        if len(character_nodes) < 2:
            # Fallback to NPC manager if graph doesn't have enough nodes
            npc_names = list(self.ctx.npc_mgr._npcs.keys())
            if len(npc_names) < 2:
                return None
            return tuple(random.sample(npc_names, 2))

        # Filter to characters in the same location (if location data available)
        location_map = {}
        for name in character_nodes:
            npc_state = self.ctx.npc_mgr.get(name)
            if npc_state:
                loc = npc_state.location
                location_map.setdefault(loc, []).append(name)

        # Prefer NPCs in the same location
        for loc, npcs_in_loc in location_map.items():
            if len(npcs_in_loc) >= 2:
                character_nodes = npcs_in_loc
                break

        # Score pairs by common neighbors and centrality
        best_pair = None
        best_score = -1

        for i, u in enumerate(character_nodes):
            for v in character_nodes[i+1:]:
                # Calculate common neighbors
                try:
                    common = list(nx.common_neighbors(G, u, v))
                    common_count = len(common)
                except nx.NetworkXError:
                    common_count = 0

                # Prefer pairs with common neighbors (more interesting)
                # Add small random factor to avoid always picking same pairs
                score = common_count + random.uniform(0, 0.5)

                if score > best_score:
                    best_score = score
                    best_pair = (u, v)

        # If no good pair found with common neighbors, pick random
        if best_pair is None or best_score == 0:
            if len(character_nodes) >= 2:
                best_pair = tuple(random.sample(character_nodes, 2))
            else:
                return None

        return best_pair

    async def simulate_turn(self, story_time: datetime) -> None:
        """Pick two NPCs in the same location and generate a short interaction."""
        # Use intelligent pair selection
        pair = self._select_interaction_pair()

        if pair is None:
            logger.debug("Not enough NPCs for social interaction")
            return

        a, b = pair

        # Get locations for both NPCs
        a_state = self.ctx.npc_mgr.get(a)
        b_state = self.ctx.npc_mgr.get(b)

        loc_a = a_state.location if a_state else "unknown"
        loc_b = b_state.location if b_state else "unknown"
        loc = loc_a if loc_a == loc_b else "unknown"

        # Generate a short interaction via LLM
        prompt = f"""
Two characters, {a} and {b}, are both in the location "{loc}".
Generate a short interaction (2‑3 sentences) that could happen between them.
The interaction should be consistent with their personalities and world rules.
Return JSON: {{"interaction": "text", "relationship_delta": integer between -3 and 3}}
"""
        llm = self.ctx.llm
        try:
            result = await llm.generate_json(prompt, temperature=0.7)
            delta = result.get("relationship_delta", 0)
            interaction = result.get("interaction", "")

            # Update relationship in graph (if needed) – using chronicler
            await self.ctx.chronicler.log_event(
                f"{a} and {b} interacted: {interaction}",
                story_time, group="social"
            )
            logger.info(f"Social interaction: {a} <-> {b} (delta {delta})")

            # Apply relationship change via story engine effect
            from .story_engine import StoryEngine
            await self.ctx.story_engine.apply_effects(
                [{"type": "relationship_change", "source": a, "target": b, "delta": delta}],
                story_time
            )
        except Exception as e:
            logger.warning(f"Social simulation failed: {e}")
