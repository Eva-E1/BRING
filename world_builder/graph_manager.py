# graph_manager.py (fixed)
"""Unified API for layered world entities and graph."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .entity_store import EntityStore
from .entity_profile import EntityNode, LayeredProfile
from .graph_engine import GraphEngine

logger = logging.getLogger(__name__)


class GraphManager:
    def __init__(self, entity_store_path: Path, graph_engine: Optional[GraphEngine] = None):
        self.store = EntityStore(entity_store_path)
        self.graph = graph_engine or GraphEngine()
        self._build_graph_from_store()

    def _build_graph_from_store(self):
        self.graph.clear()
        for node in self.store.all_nodes():
            uid = node.uid
            self.graph.add_node(uid, entity_type=node.entity_type, name=node.name, group_id=node.group_id)
            rels = node.profile.l1.get("relationships", [])
            for rel in rels:
                target_uid = self._resolve_entity_uid(rel["target"])
                if target_uid:
                    self.graph.add_edge(uid, target_uid, rel["type"], edge_source="l1")
                else:
                    logger.warning(f"Relationship target '{rel['target']}' not found for {uid}")
            self._add_inferred_edges(node)

    def _resolve_entity_uid(self, name: str) -> Optional[str]:
        """Resolve an entity reference to a UID.
        Accepts plain names (case‑insensitive) and full UIDs like 'Faction:Order of the Echo'.
        """
        name = name.strip()
        if not name:
            return None

        # 1. Direct UID match
        if name in self.graph.nodes:
            return name

        # 2. Case‑insensitive full name
        low = name.lower()
        for node in self.store.all_nodes():
            if node.name.lower() == low:
                return node.uid

        # 3. Token‑based fuzzy match (if exactly one candidate)
        candidates = set()
        for token in low.split():
            for node in self.store.all_nodes():
                if token in node.name.lower():
                    candidates.add(node.uid)
        valid_candidates = [u for u in candidates if u in self.graph.nodes]
        if len(valid_candidates) == 1:
            return valid_candidates[0]

        return None

    def _add_inferred_edges(self, node: EntityNode):
        uid = node.uid
        if node.entity_type == "Character":
            for aff in node.profile.l2.get("affiliations", []):
                aff_uid = self._resolve_entity_uid(aff)
                if aff_uid:
                    self.graph.add_edge(uid, aff_uid, "member_of", edge_source="l2")
            loc = node.profile.l2.get("current_location")
            if loc:
                loc_uid = self._resolve_entity_uid(loc)
                if loc_uid:
                    self.graph.add_edge(uid, loc_uid, "located_at", edge_source="l2")
        elif node.entity_type == "Location":
            ruling = node.profile.l2.get("ruling_faction")
            if ruling:
                fact_uid = self._resolve_entity_uid(ruling)
                if fact_uid:
                    self.graph.add_edge(fact_uid, uid, "controls", edge_source="l2")

    async def add_entity(self, name: str, entity_type: str, profile: LayeredProfile,
                         group_id: str = "") -> EntityNode:
        uid = f"{entity_type}:{name}"
        existing = self.store.get(uid)
        if existing:
            existing.profile = profile
            existing.updated_at = __import__('time').time()
            self.store.save()
            node = existing
        else:
            node = EntityNode(
                uid=uid,
                name=name,
                entity_type=entity_type,
                profile=profile,
                group_id=group_id,
            )
            self.store.add(node)
        self.graph.add_node(uid, entity_type=entity_type, name=name, group_id=group_id)
        self._clear_edges_for_node(uid)
        for rel in profile.l1.get("relationships", []):
            target_uid = self._resolve_entity_uid(rel["target"])
            if target_uid:
                self.graph.add_edge(uid, target_uid, rel["type"], edge_source="l1")
        self._add_inferred_edges(node)
        self.store.save()
        return node

    def _clear_edges_for_node(self, uid: str):
        for target, _, _ in self.graph.adj.get(uid, []):
            self.graph.rev_adj[target] = [e for e in self.graph.rev_adj.get(target, []) if e[0] != uid]
        self.graph.adj[uid].clear()
        for src, _, _ in self.graph.rev_adj.get(uid, []):
            self.graph.adj[src] = [e for e in self.graph.adj.get(src, []) if e[0] != uid]
        self.graph.rev_adj[uid].clear()

    async def get_l1(self, uid: str) -> Optional[Dict]:
        node = self.store.get(uid)
        return node.profile.l1 if node else None

    async def get_l2(self, uid: str) -> Optional[Dict]:
        node = self.store.get(uid)
        return node.profile.l2 if node else None

    async def get_l3(self, uid: str) -> Optional[Dict]:
        node = self.store.get(uid)
        return node.profile.l3 if node else None

    async def get_connected(self, uid: str, direction: str = 'out') -> List[Dict]:
        neighbors = self.graph.get_neighbors(uid, direction)
        result = []
        for neighbor_uid, etype, attrs in neighbors:
            node = self.store.get(neighbor_uid)
            if node:
                result.append({
                    "uid": neighbor_uid,
                    "name": node.name,
                    "type": node.entity_type,
                    "edge_type": etype,
                    "l1_summary": node.profile.l1.get("summary", ""),
                })
        return result

    async def search(self, query: str, entity_type: Optional[str] = None, limit: int = 20) -> List[Dict]:
        nodes = self.store.search(query, entity_type)
        return [{"uid": n.uid, "name": n.name, "type": n.entity_type,
                 "summary": n.profile.l1.get("summary", "")} for n in nodes[:limit]]

    async def entity_exists(self, name: str, entity_type: Optional[str] = None) -> bool:
        uid = f"{entity_type}:{name}" if entity_type else None
        if uid and self.store.get(uid):
            return True
        return self._resolve_entity_uid(name) is not None

    def build_full_graph(self) -> GraphEngine:
        return self.graph
