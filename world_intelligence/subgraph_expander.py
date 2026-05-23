"""Expand a subgraph around an entity, complete missing data, check rules, and generate scenes."""
import asyncio
from typing import Dict, Any, List
from rich.console import Console
from world_explorer.store import GraphStore
from world_explorer.builder_integration import BuilderInterface
from .rule_checker import RuleChecker
from .scene_generator import SceneGenerator

console = Console()


class SubgraphExpander:
    def __init__(self, store: GraphStore, builder: BuilderInterface):
        self.store = store
        self.builder = builder
        self.checker = RuleChecker(store, builder)
        self.scene_gen = SceneGenerator(store, builder)

    def expand(self, center_uid: str, depth: int = 2, complete_layers: bool = True,
               check_rules: bool = True, fix_rules: bool = False, generate_scene: bool = True) -> Dict[str, Any]:
        """Synchronous wrapper for async expand method."""
        return asyncio.run(self.expand_async(center_uid, depth, complete_layers, check_rules, fix_rules, generate_scene))

    async def expand_async(self, center_uid: str, depth: int = 2, complete_layers: bool = True,
                           check_rules: bool = True, fix_rules: bool = False, generate_scene: bool = True) -> Dict[str, Any]:
        """
        1. Ensure all entities in subgraph have L2/L3 (complete via builder).
        2. Check rule consistency for them.
        3. Optionally auto‑fix rule violations.
        4. Generate a narrative scene from the subgraph.
        """
        G = self.store.get_active_graph()
        if center_uid not in G:
            return {"error": "Entity not found"}

        import networkx as nx
        lengths = nx.single_source_shortest_path_length(G, center_uid, cutoff=depth)
        sub_nodes = list(lengths.keys())

        report = {"nodes_in_subgraph": len(sub_nodes), "completed": [], "rule_conflicts": [], "scene": None}

        # 1. Complete missing layers
        if complete_layers:
            for uid in sub_nodes:
                ent = self.store.entities_by_uid.get(uid)
                if not ent:
                    continue
                if not ent.profile.l2:
                    console.log(f"  Completing L2 for {uid}")
                    await self.builder.complete_entity_async(uid, "l2")
                    report["completed"].append(f"{uid} L2")
                if not ent.profile.l3:
                    console.log(f"  Completing L3 for {uid}")
                    await self.builder.complete_entity_async(uid, "l3")
                    report["completed"].append(f"{uid} L3")

        # 2. Rule check (on subgraph entities)
        if check_rules:
            conflicts = await self.checker.check_all_async(auto_fix=fix_rules)
            report["rule_conflicts"] = conflicts

        # 3. Generate scene (now async)
        if generate_scene:
            scene = await self.scene_gen.generate_scene_from_cluster(center_uid)
            report["scene"] = scene

        return report
