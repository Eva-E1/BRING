"""Simple in-memory graph for world entities."""
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

class GraphEngine:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.adj: Dict[str, List[Tuple[str, str, Dict[str, Any]]]] = defaultdict(list)
        self.rev_adj: Dict[str, List[Tuple[str, str, Dict]]] = defaultdict(list)

    def add_node(self, uid: str, **attrs):
        self.nodes[uid] = attrs

    def add_edge(self, source: str, target: str, edge_type: str, **attrs):
        if source not in self.nodes:
            self.add_node(source, name=source)
        if target not in self.nodes:
            self.add_node(target, name=target)
        self.adj[source].append((target, edge_type, attrs))
        self.rev_adj[target].append((source, edge_type, attrs))

    def remove_node(self, uid: str):
        self.adj.pop(uid, None)
        self.rev_adj.pop(uid, None)
        for src, edges in self.adj.items():
            self.adj[src] = [e for e in edges if e[0] != uid]
        for src, edges in self.rev_adj.items():
            self.rev_adj[src] = [e for e in edges if e[0] != uid]
        self.nodes.pop(uid, None)

    def get_neighbors(self, uid: str, direction: str = 'out') -> List[Tuple[str, str, Dict]]:
        if direction == 'out':
            return self.adj.get(uid, [])
        elif direction == 'in':
            return self.rev_adj.get(uid, [])
        else:
            out = self.adj.get(uid, [])
            in_ = self.rev_adj.get(uid, [])
            return out + in_

    def get_edges_between(self, uid1: str, uid2: str) -> List[Tuple[str, Dict]]:
        result = []
        for target, etype, attrs in self.adj.get(uid1, []):
            if target == uid2:
                result.append((etype, attrs))
        for target, etype, attrs in self.adj.get(uid2, []):
            if target == uid1:
                result.append((etype, attrs))
        return result

    def nodes_of_type(self, entity_type: str) -> List[str]:
        return [uid for uid, attrs in self.nodes.items() if attrs.get("entity_type") == entity_type]

    def clear(self):
        self.nodes.clear()
        self.adj.clear()
        self.rev_adj.clear()
