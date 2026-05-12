"""Graph‑based recommendations for missing relationships and new entities."""
import networkx as nx
from typing import List, Dict, Any
from rich.console import Console
from world_explorer.navigator import Navigator
from world_explorer.store import GraphStore

console = Console()

class Recommender:
    def __init__(self, store: GraphStore):
        self.store = store
        self.G = store.get_active_graph()
        self.nav = Navigator(store)

    def suggest_missing_relationships(self, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Use common neighbors and structural holes to suggest missing edges.
        """
        G = self.G.to_undirected()          # <-- fix: convert to undirected
        suggestions = []
        nodes = list(G.nodes())
        for i, u in enumerate(nodes):
            for v in nodes[i+1:]:
                if G.has_edge(u, v):
                    continue
                # Only suggest between certain types
                type_u = G.nodes[u].get("type")
                type_v = G.nodes[v].get("type")
                valid_pairs = (
                    (type_u == "Character" and type_v == "Faction") or
                    (type_u == "Faction" and type_v == "Character") or
                    (type_u == "Character" and type_v == "Character") or
                    (type_u == "Location" and type_v == "Faction") or
                    (type_u == "Faction" and type_v == "Location")
                )
                if not valid_pairs:
                    continue

                common = list(nx.common_neighbors(G, u, v))
                if len(common) >= 2:
                    suggestions.append({
                        "source": u,
                        "target": v,
                        "source_name": G.nodes[u].get("label", u),
                        "target_name": G.nodes[v].get("label", v),
                        "common_neighbors": len(common),
                        "score": len(common) / (max(G.degree(u), G.degree(v)) + 1),
                    })
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:top_k]

    def suggest_new_entities(self) -> List[Dict[str, Any]]:
        """
        Look for dense clusters that could form a new faction.
        """
        G = self.G.to_undirected()
        # Find areas with k-core >= 3
        k_core = nx.k_core(G, k=3)
        if len(k_core) < 3:
            return []

        try:
            import community as community_louvain
            partition = community_louvain.best_partition(k_core)
        except ImportError:
            from networkx.algorithms.community import greedy_modularity_communities
            communities = list(greedy_modularity_communities(k_core))
            partition = {}
            for i, comm in enumerate(communities):
                for node in comm:
                    partition[node] = i

        groups = {}
        for node, comm_id in partition.items():
            groups.setdefault(comm_id, []).append(node)

        suggestions = []
        for comm_id, members in groups.items():
            if len(members) >= 3:
                types = [G.nodes[n].get("type") for n in members]
                if types.count("Character") + types.count("Faction") >= len(members):
                    names = [G.nodes[n].get("label", n) for n in members]
                    suggestions.append({
                        "suggested_type": "Faction",
                        "based_on_members": names,
                        "reason": f"Dense community of {len(members)} characters/factions",
                    })
        return suggestions
