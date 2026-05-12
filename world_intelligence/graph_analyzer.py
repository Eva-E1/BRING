"""Social network analysis tools for the world graph."""
import networkx as nx
from typing import Dict, Any, List
from rich.console import Console
from world_explorer.navigator import Navigator
from world_explorer.store import GraphStore

console = Console()

class GraphAnalyzer:
    def __init__(self, store: GraphStore):
        self.store = store
        self.G = store.get_active_graph()

    def centrality_report(self, top_n: int = 10) -> Dict[str, Any]:
        """Compute degree, betweenness, and closeness centrality for all nodes."""
        G = self.G
        degree = nx.degree_centrality(G)
        between = nx.betweenness_centrality(G)
        close = nx.closeness_centrality(G)

        # Sort by degree
        sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:top_n]
        report = {
            "top_degree": [],
            "top_betweenness": [],
            "top_closeness": [],
        }
        for node, score in sorted_nodes:
            info = {
                "uid": node,
                "name": G.nodes[node].get("label", node),
                "type": G.nodes[node].get("type", "?"),
                "degree_centrality": round(score, 3),
                "betweenness_centrality": round(between.get(node, 0), 3),
                "closeness_centrality": round(close.get(node, 0), 3),
            }
            report["top_degree"].append(info)

        # Betweenness
        sorted_bet = sorted(between.items(), key=lambda x: x[1], reverse=True)[:top_n]
        for node, score in sorted_bet:
            if node not in [n["uid"] for n in report["top_betweenness"]]:
                info = {
                    "uid": node,
                    "name": G.nodes[node].get("label", node),
                    "type": G.nodes[node].get("type", "?"),
                    "betweenness_centrality": round(score, 3),
                }
                report["top_betweenness"].append(info)

        # Closeness
        sorted_cl = sorted(close.items(), key=lambda x: x[1], reverse=True)[:top_n]
        for node, score in sorted_cl:
            if node not in [n["uid"] for n in report["top_closeness"]]:
                info = {
                    "uid": node,
                    "name": G.nodes[node].get("label", node),
                    "type": G.nodes[node].get("type", "?"),
                    "closeness_centrality": round(score, 3),
                }
                report["top_closeness"].append(info)

        return report

    def community_detection(self) -> Dict[str, Any]:
        """Detect communities using Louvain method (requires python-louvain) or greedy modularity."""
        G = self.G.to_undirected()
        try:
            import community as community_louvain
            partition = community_louvain.best_partition(G)
        except ImportError:
            # Fallback to greedy modularity
            from networkx.algorithms.community import greedy_modularity_communities
            communities = list(greedy_modularity_communities(G))
            partition = {}
            for i, comm in enumerate(communities):
                for node in comm:
                    partition[node] = i

        # Group by community
        groups = {}
        for node, comm_id in partition.items():
            groups.setdefault(comm_id, []).append({
                "uid": node,
                "name": G.nodes[node].get("label", node),
                "type": G.nodes[node].get("type", "?"),
            })
        return {"communities": {str(k): v for k, v in groups.items()}}

    def path_stats(self) -> Dict[str, Any]:
        """Calculate average path length and diameter (if connected)."""
        G = self.G.to_undirected()
        if nx.is_connected(G):
            avg_path = nx.average_shortest_path_length(G)
            diameter = nx.diameter(G)
        else:
            # For the largest component
            largest_cc = max(nx.connected_components(G), key=len)
            sub = G.subgraph(largest_cc)
            avg_path = nx.average_shortest_path_length(sub)
            diameter = nx.diameter(sub)
        return {
            "average_shortest_path_length": round(avg_path, 3),
            "diameter": diameter,
            "is_connected": nx.is_connected(G),
        }
