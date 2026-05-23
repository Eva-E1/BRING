"""
BRING v2 — Graph Manager with O(1) lookups, lazy graph rebuild, and batch operations.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .entity_store import EntityStore
from .entity_profile import EntityNode, LayeredProfile
from .graph_engine import GraphEngine

logger = logging.getLogger(__name__)


class GraphManager:
    """
    Unified API for layered world entities and graph.
    
    v2 improvements:
    - O(1) name resolution via UnifiedEntityStore.name_index
    - Lazy graph rebuild (only rebuilds when entities change)
    - Batch operations to reduce I/O
    - Event notifications via mutation callbacks
    """

    def __init__(
        self,
        entity_store_path: Path,
        graph_engine: Optional[GraphEngine] = None,
        builder=None,
    ):
        self.store = EntityStore(entity_store_path)
        self.graph = graph_engine or GraphEngine()
        self.builder = builder
        self._repairer = None
        self._graph_dirty = True

        # Subscribe to store mutations to flag graph as dirty
        self.store.unified.on_mutation(self._on_store_mutation)

        self._build_graph_from_store()

    def _on_store_mutation(self, action: str, uid: str):
        """Flag graph for rebuild when entities change."""
        self._graph_dirty = True

    def _build_graph_from_store(self):
        """Rebuild graph from current entity state."""
        self.graph.clear()
        valid_uids = self.store.unified.valid_uids

        for node in self.store.all_nodes():
            uid = node.uid
            self.graph.add_node(
                uid,
                entity_type=node.entity_type,
                name=node.name,
                group_id=node.group_id,
            )
            rels = node.profile.l1.get("relationships", [])
            for rel in rels:
                target_uid = self.store.unified.resolve_uid(rel["target"])
                if target_uid:
                    self.graph.add_edge(uid, target_uid, rel["type"], edge_source="l1")
                else:
                    logger.warning(
                        f"Relationship target '{rel['target']}' not found for {uid}"
                    )
            self._add_inferred_edges(node)

        self._graph_dirty = False

    def ensure_graph_fresh(self):
        """Rebuild graph only if dirty."""
        if self._graph_dirty:
            self._build_graph_from_store()

    def _resolve_entity_uid(self, name: str) -> Optional[str]:
        """
        Resolve an entity reference to a UID.
        Now O(1) for exact matches via NameIndex.
        """
        return self.store.unified.resolve_uid(name)

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

    async def add_entity(
        self,
        name: str,
        entity_type: str,
        profile: LayeredProfile,
        group_id: str = "",
    ) -> EntityNode:
        uid = f"{entity_type}:{name}"
        existing = self.store.get(uid)

        if existing:
            existing.profile = profile
            import time
            existing.updated_at = time.time()
            self.store.unified.update_entity_level(uid, "l1", profile.l1)
            if profile.l2:
                self.store.unified.update_entity_level(uid, "l2", profile.l2)
            if profile.l3:
                self.store.unified.update_entity_level(uid, "l3", profile.l3)
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

        # Update graph
        self.graph.add_node(
            uid,
            entity_type=entity_type,
            name=name,
            group_id=group_id,
        )
        self._clear_edges_for_node(uid)
        for rel in profile.l1.get("relationships", []):
            target_uid = self._resolve_entity_uid(rel["target"])
            if target_uid:
                self.graph.add_edge(uid, target_uid, rel["type"], edge_source="l1")
        self._add_inferred_edges(node)

        return node

    def _clear_edges_for_node(self, uid: str):
        for target, _, _ in self.graph.adj.get(uid, []):
            self.graph.rev_adj[target] = [
                e for e in self.graph.rev_adj.get(target, []) if e[0] != uid
            ]
        self.graph.adj[uid] = []
        for src, _, _ in self.graph.rev_adj.get(uid, []):
            self.graph.adj[src] = [
                e for e in self.graph.adj.get(src, []) if e[0] != uid
            ]
        self.graph.rev_adj[uid] = []

    async def get_l1(self, uid: str) -> Optional[Dict]:
        node = self.store.get(uid)
        return node.profile.l1 if node else None

    async def get_l2(self, uid: str) -> Optional[Dict]:
        node = self.store.get(uid)
        return node.profile.l2 if node else None

    async def get_l3(self, uid: str) -> Optional[Dict]:
        node = self.store.get(uid)
        return node.profile.l3 if node else None

    async def get_connected(self, uid: str, direction: str = "out") -> List[Dict]:
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

    async def search(
        self, query: str, entity_type: Optional[str] = None, limit: int = 20
    ) -> List[Dict]:
        nodes = self.store.search(query, entity_type)
        return [
            {
                "uid": n.uid,
                "name": n.name,
                "type": n.entity_type,
                "summary": n.profile.l1.get("summary", ""),
            }
            for n in nodes[:limit]
        ]

    async def entity_exists(self, name: str, entity_type: Optional[str] = None) -> bool:
        uid = f"{entity_type}:{name}" if entity_type else None
        if uid and self.store.get(uid):
            return True
        return self._resolve_entity_uid(name) is not None

    def build_full_graph(self) -> GraphEngine:
        self.ensure_graph_fresh()
        return self.graph

    async def repair_all_relationships(self, intelligent: bool = True) -> Dict[str, int]:
        if intelligent and self.builder:
            from world_intelligence.relationship_repairer import RelationshipRepairer
            if not self._repairer:
                self._repairer = RelationshipRepairer(self, self.builder)
            return await self._repairer.repair_all_relationships()
        else:
            stats = {"resolved": 0, "merged": 0, "created": 0, "failed": 0, "skipped": 0}
            for node in self.store.all_nodes():
                rels = node.profile.l1.get("relationships", [])
                new_rels = []
                for rel in rels:
                    target_ref = rel.get("target")
                    if not target_ref:
                        continue
                    target_uid = self._resolve_entity_uid(target_ref)
                    if target_uid is None:
                        target_uid = await self._create_placeholder(target_ref)
                        if target_uid:
                            stats["created"] += 1
                        else:
                            stats["failed"] += 1
                    if target_uid:
                        new_rels.append({"target": target_uid, "type": rel.get("type")})
                    else:
                        stats["skipped"] += 1
                if len(new_rels) != len(rels):
                    self.store.update_entity_level(node.uid, "l1", node.profile.l1)
            return stats

    async def _create_placeholder(self, target_ref: str) -> Optional[str]:
        name = target_ref.split(":")[-1] if ":" in target_ref else target_ref
        placeholder_uid = f"Unknown:{name}"
        if not self.store.get(placeholder_uid):
            profile = LayeredProfile(
                l1={
                    "name": name,
                    "type": "Unknown",
                    "summary": f"Placeholder for missing entity '{target_ref}'",
                    "tags": ["placeholder"],
                }
            )
            node = await self.add_entity(name, "Unknown", profile, group_id="_placeholders")
            return node.uid
        return placeholder_uid

