"""
BRING v2 — Progressive fuzzy matching engine for entity references.
Uses a Trie for O(m) prefix lookups instead of O(n) linear scans.
"""
from __future__ import annotations

import asyncio
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


# ── Trie for prefix-based matching ─────────────────────────────────

class TrieNode:
    __slots__ = ("children", "uids", "is_end")

    def __init__(self):
        self.children: Dict[str, "TrieNode"] = {}
        self.uids: List[str] = []
        self.is_end: bool = False


class EntityTrie:
    """
    Trie index for fast prefix-based entity name matching.
    Insert: O(m) where m = name length.
    Prefix search: O(m + k) where k = number of matching entities.
    """

    def __init__(self):
        self.root = TrieNode()

    def insert(self, name: str, uid: str) -> None:
        node = self.root
        for char in name.lower():
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
            node.uids.append(uid)
        node.is_end = True

    def search_prefix(self, prefix: str, limit: int = 10) -> List[str]:
        """Find all UIDs whose names start with the given prefix."""
        node = self.root
        for char in prefix.lower():
            if char not in node.children:
                return []
            node = node.children[char]
        return list(dict.fromkeys(node.uids[:limit * 3]))[:limit]

    def search_fuzzy_prefix(self, query: str, max_edit_distance: int = 2) -> List[str]:
        """Find UIDs with names that fuzzy-match the query prefix."""
        # Start with exact prefix
        results = set(self.search_prefix(query, limit=20))

        # Also try first 2-3 characters for fuzzy
        for length in range(max(1, len(query) - 1), len(query) + 1):
            prefix = query[:length].lower()
            results.update(self.search_prefix(prefix, limit=10))

        return list(results)


# ── Thresholds ──────────────────────────────────────────────────────

DEFAULT_EXACT_THRESHOLD = 0.95
DEFAULT_HIGH_THRESHOLD = 0.85
DEFAULT_MEDIUM_THRESHOLD = 0.65
DEFAULT_LOW_THRESHOLD = 0.45


class RelationshipRepairer:
    """
    Progressive fuzzy matching engine with:
    - Trie-based prefix search for O(m) lookups
    - Cached similarity scores
    - Batch entity creation
    """

    def __init__(
        self,
        gm: Any,
        builder: Any,
        graph_store: Any = None,
        llm_client: Any = None,
        exact_threshold: float = DEFAULT_EXACT_THRESHOLD,
        high_threshold: float = DEFAULT_HIGH_THRESHOLD,
        medium_threshold: float = DEFAULT_MEDIUM_THRESHOLD,
        low_threshold: float = DEFAULT_LOW_THRESHOLD,
        auto_merge: bool = True,
        auto_create: bool = True,
    ):
        self.gm = gm
        self.builder = builder
        self.graph_store = graph_store
        self.llm = llm_client or builder.llm
        self.exact_threshold = exact_threshold
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.low_threshold = low_threshold
        self.auto_merge = auto_merge
        self.auto_create = auto_create

        self.stats = {"resolved": 0, "merged": 0, "created": 0, "failed": 0, "skipped": 0}
        self._similarity_cache: Dict[Tuple[str, str], float] = {}
        self._trie = EntityTrie()
        self._trie_built = False

    def _ensure_trie(self):
        """Build trie index lazily."""
        if self._trie_built:
            return
        self._trie = EntityTrie()
        for node in self.gm.store.all_nodes():
            self._trie.insert(node.name, node.uid)
        self._trie_built = True

    def _normalise_name(self, name: str) -> str:
        name = name.strip()
        if ":" in name and not name.startswith("__"):
            name = name.split(":", 1)[1]
        name = re.sub(r"\s*\([^)]+\)$", "", name)
        return name.lower()

    def _infer_type_from_ref(self, ref: str) -> str:
        ref_lower = ref.lower()
        if ":" in ref:
            prefix = ref.split(":", 1)[0].capitalize()
            if prefix in ["Character", "Faction", "Location", "Item", "Event", "WorldRule", "Race"]:
                return prefix
        if any(w in ref_lower for w in ["character", "npc", "person"]):
            return "Character"
        if any(w in ref_lower for w in ["faction", "guild", "order", "tribe"]):
            return "Faction"
        if any(w in ref_lower for w in ["city", "forest", "mountain", "ruin", "location"]):
            return "Location"
        if any(w in ref_lower for w in ["sword", "artifact", "item", "weapon"]):
            return "Item"
        return "Unknown"

    def _similarity_score(self, a: str, b: str) -> float:
        a_norm = self._normalise_name(a)
        b_norm = self._normalise_name(b)

        if a_norm == b_norm:
            return 1.0

        cache_key = (min(a_norm, b_norm), max(a_norm, b_norm))
        if cache_key in self._similarity_cache:
            return self._similarity_cache[cache_key]

        if HAS_RAPIDFUZZ:
            token_score = fuzz.token_set_ratio(a_norm, b_norm) / 100.0
            partial_score = fuzz.partial_ratio(a_norm, b_norm) / 100.0
        else:
            set_a = set(a_norm.split())
            set_b = set(b_norm.split())
            intersection = set_a & set_b
            union = set_a | set_b
            token_score = len(intersection) / len(union) if union else 0.0
            matcher = SequenceMatcher(None, a_norm, b_norm)
            match = matcher.find_longest_match(0, len(a_norm), 0, len(b_norm))
            partial_score = match.size / max(len(a_norm), len(b_norm), 1)

        score = (token_score * 0.7) + (partial_score * 0.3)
        self._similarity_cache[cache_key] = score
        return score

    def _find_best_match(self, clean_ref: str) -> Tuple[Optional[Any], float]:
        """Find best matching entity using trie-accelerated search."""
        self._ensure_trie()

        # Use trie to narrow candidates
        candidate_uids = self._trie.search_fuzzy_prefix(clean_ref)

        # If trie gave no results, fall back to all entities
        entities = self.gm.store.all_nodes()
        if candidate_uids:
            entities = [
                self.gm.store.get(uid) for uid in candidate_uids
                if self.gm.store.get(uid) is not None
            ] or self.gm.store.all_nodes()

        best_entity = None
        best_score = 0.0
        for ent in entities:
            score = self._similarity_score(clean_ref, ent.name)
            if score > best_score:
                best_score = score
                best_entity = ent
            if score >= self.exact_threshold:
                break

        return best_entity, best_score

    async def _merge_entities(self, target_uid: str, source_ref: str, source_uid: str, rel_type: str):
        source_entity = None
        for ent in self.gm.store.all_nodes():
            if self._similarity_score(ent.name, source_ref) > self.high_threshold:
                source_entity = ent
                break
        if source_entity and source_entity.uid != target_uid:
            for rel in source_entity.profile.l1.get("relationships", []):
                pass  # Relationships handled by graph
            target_entity = self.gm.store.get(target_uid)
            if target_entity:
                for layer in ["l2", "l3"]:
                    src_data = getattr(source_entity.profile, layer, {})
                    tgt_data = getattr(target_entity.profile, layer, {})
                    if src_data and not tgt_data:
                        self.gm.store.update_entity_level(target_uid, layer, src_data)
            if hasattr(self.gm.graph, "remove_node"):
                self.gm.graph.remove_node(source_entity.uid)
            self.stats["merged"] += 1

    async def _create_entity_from_scratch(
        self, target_ref: str, source_uid: str, rel_type: str
    ) -> Optional[str]:
        from world_builder.entity_profile import LayeredProfile

        etype = self._infer_type_from_ref(target_ref)
        name = target_ref.split(":", 1)[-1] if ":" in target_ref else target_ref
        name = name.strip()

        try:
            if etype == "Character":
                node = await self.builder.add_npc("unknown")
            elif etype == "Faction":
                node = await self.builder.add_faction()
            elif etype == "Location":
                node = await self.builder.add_location()
            elif etype == "Item":
                node = await self.builder.add_item("artifact")
            elif etype == "Event":
                node = await self.builder.add_event()
            elif etype == "WorldRule":
                node = await self.builder.add_rule()
            else:
                profile = LayeredProfile(l1={
                    "name": name,
                    "type": etype,
                    "summary": f"Auto-created for missing reference '{target_ref}'",
                    "tags": ["auto_created"],
                })
                node = await self.gm.add_entity(name, etype, profile)

            self.stats["created"] += 1
            # Invalidate trie
            self._trie_built = False
            return node.uid
        except Exception as e:
            logger.error(f"Failed to create entity for {target_ref}: {e}")
            self.stats["failed"] += 1
            return None

    async def _create_similar_entity(
        self, template_entity: Any, target_ref: str, source_uid: str, rel_type: str
    ) -> Optional[str]:
        from world_builder.entity_profile import LayeredProfile

        prompt = f"""Create a new entity similar to this template but named "{target_ref}":
Template: {template_entity.name} ({template_entity.entity_type})
L1: {template_entity.profile.l1}
L2: {template_entity.profile.l2}
Return JSON: {{"l1": {{"name": "{target_ref}", "type": "...", "summary": "...", "tags": []}}, "l2": {{...}}, "l3": {{...}}}}"""

        try:
            result = await self.llm.generate_json(prompt, temperature=0.7)
            l1 = result.get("l1", {"name": target_ref, "type": template_entity.entity_type})
            l2 = result.get("l2", {})
            l3 = result.get("l3", {})
            profile = LayeredProfile(l1=l1, l2=l2, l3=l3)
            node = await self.gm.add_entity(l1["name"], l1["type"], profile)
            self.stats["created"] += 1
            self._trie_built = False
            return node.uid
        except Exception as e:
            logger.error(f"Failed to create similar entity for {target_ref}: {e}")
            return await self._create_entity_from_scratch(target_ref, source_uid, rel_type)

    def _update_source_relationships(self, source_uid: str, target_uid: str, rel_type: str):
        src_node = self.gm.store.get(source_uid)
        if src_node:
            rels = src_node.profile.l1.setdefault("relationships", [])
            if not any(r.get("target") == target_uid for r in rels):
                rels.append({"target": target_uid, "type": rel_type})
                self.gm.store.update_entity_level(source_uid, "l1", src_node.profile.l1)

    async def repair_relationship(
        self, source_uid: str, target_ref: str, rel_type: str
    ) -> Tuple[bool, Optional[str]]:
        existing_uid = self.gm._resolve_entity_uid(target_ref)
        if existing_uid:
            self.stats["resolved"] += 1
            return True, existing_uid

        clean_ref = self._normalise_name(target_ref)
        best_entity, score = self._find_best_match(clean_ref)

        if score >= self.high_threshold:
            if self.auto_merge:
                await self._merge_entities(best_entity.uid, target_ref, source_uid, rel_type)
            self.gm.graph.add_edge(source_uid, best_entity.uid, rel_type, edge_source="auto_repair")
            self._update_source_relationships(source_uid, best_entity.uid, rel_type)
            self.stats["resolved"] += 1
            return True, best_entity.uid

        elif score >= self.medium_threshold:
            if self.auto_create:
                new_uid = await self._create_similar_entity(best_entity, target_ref, source_uid, rel_type)
                if new_uid:
                    self.stats["resolved"] += 1
                    return True, new_uid
            self.gm.graph.add_edge(source_uid, best_entity.uid, rel_type, edge_source="auto_repair")
            self._update_source_relationships(source_uid, best_entity.uid, rel_type)
            self.stats["resolved"] += 1
            return True, best_entity.uid

        elif score >= self.low_threshold and self.auto_create:
            new_uid = await self._create_entity_from_scratch(target_ref, source_uid, rel_type)
            if new_uid:
                self.stats["resolved"] += 1
                return True, new_uid

        self.stats["skipped"] += 1
        logger.warning(f"Could not resolve {source_uid} -> {target_ref} (score={score:.2f})")
        return False, None

    async def repair_all_relationships(self) -> Dict[str, int]:
        self.stats = {"resolved": 0, "merged": 0, "created": 0, "failed": 0, "skipped": 0}
        self._similarity_cache.clear()
        self._trie_built = False

        # Batch mode
        self.gm.store.unified.auto_save = False
        try:
            for node in self.gm.store.all_nodes():
                rels = node.profile.l1.get("relationships", [])
                if not rels:
                    continue
                new_rels = []
                for rel in rels:
                    target_ref = rel.get("target")
                    if not target_ref:
                        continue
                    existing_uid = self.gm._resolve_entity_uid(target_ref)
                    if existing_uid:
                        new_rels.append({"target": existing_uid, "type": rel.get("type")})
                        continue
                    success, resolved_uid = await self.repair_relationship(
                        node.uid, target_ref, rel.get("type")
                    )
                    if success and resolved_uid:
                        new_rels.append({"target": resolved_uid, "type": rel.get("type")})
                    else:
                        logger.debug(f"Skipping broken relationship: {node.uid} -> {target_ref}")
                if len(new_rels) != len(rels):
                    node.profile.l1["relationships"] = new_rels
                    self.gm.store.update_entity_level(node.uid, "l1", node.profile.l1)
        finally:
            self.gm.store.unified.auto_save = True
            self.gm.store.unified.save()

        return self.stats

