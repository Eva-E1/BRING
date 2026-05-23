"""
BRING v2 — Unified query interface with O(1) entity lookups.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import networkx as nx

from .store import GraphStore


class Navigator:
    def __init__(self, store: GraphStore):
        self.store = store

    def get_entity(
        self, uid: str, layers: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        ent = self.store.entities_by_uid.get(uid)
        if not ent:
            return None

        if layers:
            data = ent.profile.get_effective_data(layers)
        else:
            data = {"l1": ent.profile.l1, "l2": ent.profile.l2, "l3": ent.profile.l3}

        return {
            "uid": ent.uid,
            "name": ent.name,
            "entity_type": ent.entity_type,
            "group_id": ent.group_id,
            **data,
        }

    def get_neighbors(
        self,
        uid: str,
        depth: int = 1,
        direction: str = "out",
        layers: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        G = self.store.get_active_graph()
        if uid not in G:
            return []

        lengths: Dict[str, int] = {}
        if direction in ("out", "both"):
            lengths.update(nx.single_source_shortest_path_length(G, uid, cutoff=depth))
        if direction in ("in", "both"):
            lengths.update(
                nx.single_source_shortest_path_length(G.reverse(), uid, cutoff=depth)
            )
        lengths.pop(uid, None)

        nodes = sorted(lengths.keys(), key=lambda n: (lengths[n], G.nodes[n].get("label", "")))
        results = []
        for nid in nodes:
            ent = self.store.entities_by_uid.get(nid)
            if not ent:
                continue
            entry = {
                "uid": nid,
                "name": ent.name,
                "type": ent.entity_type,
                "distance": lengths[nid],
            }
            if layers:
                entry.update(ent.profile.get_effective_data(layers))
            results.append(entry)
        return results

    def find_path(
        self, source: str, target: str, layers: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        G = self.store.get_active_graph()
        try:
            path = nx.shortest_path(G, source, target)
        except (nx.NodeNotFound, nx.NetworkXNoPath):
            return []
        return [self.get_entity(uid, layers) for uid in path]

    def search_by_name(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        # Use unified store's optimized search
        if self.store._unified_store:
            nodes = self.store._unified_store.search(query, entity_type, limit)
        else:
            q = query.lower()
            nodes = [
                e for e in self.store.entities
                if (not entity_type or e.entity_type == entity_type)
                and (q in e.name.lower() or q in e.profile.l1.get("summary", "").lower())
            ][:limit]

        return [
            {
                "uid": n.uid,
                "name": n.name,
                "type": n.entity_type,
                "summary": n.profile.l1.get("summary", ""),
            }
            for n in nodes
        ]

    def semantic_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        hits = self.store.embeddings.search(query, top_k)
        results = []
        for uid, score in hits:
            ent = self.store.entities_by_uid.get(uid)
            if ent:
                results.append({
                    "uid": uid,
                    "name": ent.name,
                    "type": ent.entity_type,
                    "score": round(score, 3),
                    "summary": ent.profile.l1.get("summary", ""),
                })
        return results

