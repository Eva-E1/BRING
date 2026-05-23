"""Automatic narrative scene generation from subgraphs."""
import asyncio
import random
from typing import List, Dict, Any
from rich.console import Console
from world_explorer.store import GraphStore
from world_explorer.builder_integration import BuilderInterface

console = Console()

class SceneGenerator:
    def __init__(self, store: GraphStore, builder: BuilderInterface):
        self.store = store
        self.builder = builder
        self.G = store.get_active_graph()

    async def generate_scene_from_cluster(self, center_uid: str, num_characters: int = 3) -> dict:
        """
        Pick a cluster around `center_uid`, extract characters and location,
        and call the world_builder to generate a narrative scene.
        """
        G = self.G
        if center_uid not in G:
            return {"error": "Entity not found"}

        # Get neighbours up to distance 2
        import networkx as nx
        lengths = nx.single_source_shortest_path_length(G, center_uid, cutoff=2)
        neighbours = [n for n in lengths if n != center_uid]

        # Select characters from neighbours
        chars = [n for n in neighbours if G.nodes[n].get("type") == "Character"][:num_characters]
        if len(chars) < 2:
            # Include the center if it's a character
            if G.nodes[center_uid].get("type") == "Character":
                chars.append(center_uid)
        if len(chars) < 2:
            chars = [center_uid] + random.sample(neighbours, min(num_characters - 1, len(neighbours)))

        # Pick a location from neighbours
        locs = [n for n in neighbours if G.nodes[n].get("type") == "Location"]
        if not locs:
            # Fallback: any location in graph
            locs = [n for n in G.nodes if G.nodes[n].get("type") == "Location"]
        loc = random.choice(locs) if locs else None

        char_names = [G.nodes[c].get("label", c) for c in chars]
        loc_name = G.nodes[loc].get("label", loc) if loc else "an unknown place"

        # Get backstories from entity data
        backstories = {}
        for c in chars:
            ent = self.store.entities_by_uid.get(c)
            if ent:
                l2 = ent.profile.l2
                backstories[c] = l2.get("backstory_short", "") or l2.get("personality", "")

        context = (
            f"Characters: {', '.join(char_names)}\n"
            f"Location: {loc_name}\n"
            f"Known backstories: {backstories}\n"
        )

        # Use the builder's scene generation prompt - now async
        rules = self._get_rules_text()
        scene = await self.builder.builder.gen.generate_scene(
            self.builder.builder.world_frame["world_name"],
            rules,
            context
        )
        return {
            "scene_text": scene.get("scene_text", ""),
            "entities_mentioned": scene.get("entities_mentioned", []),
            "relationships_mentioned": scene.get("relationships_mentioned", []),
        }

    def _get_rules_text(self) -> str:
        wf = self.builder.builder.world_frame
        if not wf:
            return ""
        return "\n".join(f"- {r['name']}: {r['description']}" for r in wf.get("world_rules", []))
