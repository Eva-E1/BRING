"""Intelligent relationship repair with progressive matching and auto-creation."""
from __future__ import annotations

import asyncio
import logging
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    # fallback to difflib for token set ratio simulation
    def token_set_ratio(a: str, b: str) -> float:
        """Simplified token set ratio using difflib."""
        set_a = set(a.split())
        set_b = set(b.split())
        intersection = set_a & set_b
        if not intersection:
            return 0.0
        union = set_a | set_b
        return len(intersection) / len(union)

from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_builder.entity_profile import LayeredProfile
from world_builder.llm import LLMClient
from world_explorer.store import GraphStore

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_EXACT_THRESHOLD = 0.95
DEFAULT_HIGH_THRESHOLD = 0.85
DEFAULT_MEDIUM_THRESHOLD = 0.65
DEFAULT_LOW_THRESHOLD = 0.45


class RelationshipRepairer:
    """Progressive fuzzy matching engine for entity references."""

    def __init__(
        self,
        gm: GraphManager,
        builder: WorldBuilder,
        graph_store: Optional[GraphStore] = None,
        llm_client: Optional[LLMClient] = None,
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

    def _normalise_name(self, name: str) -> str:
        """Normalise entity reference: strip, lower, remove type prefix."""
        name = name.strip()
        # Remove common prefix like "Faction:" or "Character:"
        if ":" in name and not name.startswith("__"):
            name = name.split(":", 1)[1]
        # Remove common suffixes like " (NPC)"
        name = re.sub(r"\s*\([^)]+\)$", "", name)
        return name.lower()

    def _infer_type_from_ref(self, ref: str) -> str:
        """Guess entity type from reference string."""
        ref_lower = ref.lower()
        if ":" in ref:
            prefix = ref.split(":", 1)[0].capitalize()
            if prefix in ["Character", "Faction", "Location", "Item", "Event", "WorldRule", "Race"]:
                return prefix
        if any(word in ref_lower for word in ["character", "npc", "person"]):
            return "Character"
        if any(word in ref_lower for word in ["faction", "guild", "order", "tribe"]):
            return "Faction"
        if any(word in ref_lower for word in ["city", "forest", "mountain", "ruin", "location"]):
            return "Location"
        if any(word in ref_lower for word in ["sword", "artifact", "item", "weapon"]):
            return "Item"
        return "Unknown"

    def _similarity_score(self, a: str, b: str) -> float:
        """Compute similarity using multiple methods."""
        a_norm = self._normalise_name(a)
        b_norm = self._normalise_name(b)

        # Exact match
        if a_norm == b_norm:
            return 1.0

        # Token set ratio (best for partial matches)
        if HAS_RAPIDFUZZ:
            token_score = fuzz.token_set_ratio(a_norm, b_norm) / 100.0
        else:
            token_score = token_set_ratio(a_norm, b_norm)

        # Partial ratio (for substring matches)
        if HAS_RAPIDFUZZ:
            partial_score = fuzz.partial_ratio(a_norm, b_norm) / 100.0
        else:
            # fallback: longest common substring ratio
            matcher = SequenceMatcher(None, a_norm, b_norm)
            partial_score = matcher.find_longest_match(0, len(a_norm), 0, len(b_norm)).size / max(len(a_norm), len(b_norm), 1)

        # Weighted average (token set more important)
        return (token_score * 0.7) + (partial_score * 0.3)

    def _find_best_match(self, clean_ref: str) -> Tuple[Optional[Any], float]:
        """Find best matching entity among all existing entities."""
        entities = self.gm.store.all_nodes()
        if not entities:
            return None, 0.0

        best_entity = None
        best_score = 0.0

        for ent in entities:
            score = self._similarity_score(clean_ref, ent.name)
            if score > best_score:
                best_score = score
                best_entity = ent
                if score >= self.exact_threshold:
                    break  # perfect match, can stop early

        return best_entity, best_score

    async def _merge_entities(self, target_uid: str, source_ref: str, source_uid: str, rel_type: str):
        """Merge the entity referenced by source_ref into target_uid."""
        # Find if source_ref corresponds to an existing entity (partial or placeholder)
        source_entity = None
        for ent in self.gm.store.all_nodes():
            if self._similarity_score(ent.name, source_ref) > self.high_threshold:
                source_entity = ent
                break

        if source_entity and source_entity.uid != target_uid:
            logger.info(f"Merging {source_entity.uid} into {target_uid}")
            # Transfer all relationships from source to target
            for rel in source_entity.profile.l1.get("relationships", []):
                await self.gm.add_relationship(target_uid, rel["target"], rel["type"], intelligent=False)
            # Transfer any L2/L3 data if target missing
            target_entity = self.gm.store.get(target_uid)
            if target_entity:
                for layer in ["l2", "l3"]:
                    src_data = getattr(source_entity.profile, layer, {})
                    tgt_data = getattr(target_entity.profile, layer, {})
                    if src_data and not tgt_data:
                        self.gm.store.update_entity_level(target_uid, layer, src_data)
            # Remove source entity from graph
            if hasattr(self.gm.graph, 'remove_node'):
                self.gm.graph.remove_node(source_entity.uid)
            self.stats["merged"] += 1

        # Add relationship edge
        self.gm.graph.add_edge(source_uid, target_uid, rel_type, edge_source="auto_repair")
        # Update source's L1 relationships
        src_node = self.gm.store.get(source_uid)
        if src_node:
            rels = src_node.profile.l1.setdefault("relationships", [])
            if not any(r.get("target") == target_uid for r in rels):
                rels.append({"target": target_uid, "type": rel_type})
                self.gm.store.update_entity_level(source_uid, "l1", src_node.profile.l1)

    async def _create_entity_from_scratch(self, target_ref: str, source_uid: str, rel_type: str) -> Optional[str]:
        """Create a brand new entity using the builder with appropriate type."""
        etype = self._infer_type_from_ref(target_ref)
        name = target_ref.split(":", 1)[-1] if ":" in target_ref else target_ref
        name = name.strip()

        try:
            # Use builder methods based on inferred type
            if etype == "Character":
                node = await self.builder.add_npc("unknown")
                # Rename after creation
                if node.name != name:
                    node.name = name
                    node.uid = f"{node.entity_type}:{name}"
                    # Update in store
                    old_uid = node.uid
                    if old_uid in self.gm.store._entities:
                        del self.gm.store._entities[old_uid]
                    self.gm.store._entities[node.uid] = node
                    self.gm.store.save()
                    node = self.gm.store.get(node.uid)
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
                # Generic entity with minimal L1
                profile = LayeredProfile(l1={
                    "name": name,
                    "type": etype,
                    "summary": f"Auto-created entity for missing reference '{target_ref}'",
                    "tags": ["auto_created"]
                })
                node = await self.gm.add_entity(name, etype, profile)

            # Add relationship
            await self.gm.add_relationship(source_uid, node.uid, rel_type, intelligent=False)
            self.stats["created"] += 1
            return node.uid

        except Exception as e:
            logger.error(f"Failed to create entity for {target_ref}: {e}")
            self.stats["failed"] += 1
            return None

    async def _create_similar_entity(self, template_entity: Any, target_ref: str, source_uid: str, rel_type: str) -> Optional[str]:
        """Create a new entity that is similar to template but with different name."""
        prompt = f"""
You are an entity generator. Create a new entity similar to the following template but with name "{target_ref}".
Preserve the same entity type ({template_entity.entity_type}).

Template:
Name: {template_entity.name}
Type: {template_entity.entity_type}
L1 Summary: {template_entity.profile.l1.get('summary', '')}
L2: {getattr(template_entity.profile, 'l2', {{}}) or {{}}}

Return a JSON object with keys:
- "l1": {{"name": "{target_ref}", "type": "{template_entity.entity_type}", "summary": "short description", "tags": []}}
- "l2": {{"description": "physical/character details", "personality": "", "goal": ""}}
- "l3": {{"secret": ""}}

Make the entity distinct but plausible within the same world.
"""
        try:
            result = await self.llm.generate_json(prompt, temperature=0.7)
            l1 = result.get("l1", {"name": target_ref, "type": template_entity.entity_type})
            l2 = result.get("l2", {})
            l3 = result.get("l3", {})
            profile = LayeredProfile(l1=l1, l2=l2, l3=l3)
            node = await self.gm.add_entity(l1["name"], l1["type"], profile)
            await self.gm.add_relationship(source_uid, node.uid, rel_type, intelligent=False)
            self.stats["created"] += 1
            return node.uid
        except Exception as e:
            logger.error(f"Failed to create similar entity for {target_ref}: {e}")
            return await self._create_entity_from_scratch(target_ref, source_uid, rel_type)

    async def repair_relationship(self, source_uid: str, target_ref: str, rel_type: str) -> Tuple[bool, Optional[str]]:
        """
        Attempt to resolve target_ref to an actual entity UID.
        Returns (success, resolved_uid_or_None).
        """
        # First, try simple resolution
        existing_uid = self.gm._resolve_entity_uid(target_ref)
        if existing_uid:
            self.stats["resolved"] += 1
            return True, existing_uid

        # Progressive matching
        clean_ref = self._normalise_name(target_ref)
        best_entity, score = self._find_best_match(clean_ref)

        if score >= self.high_threshold:
            # High confidence: treat as same entity
            if self.auto_merge:
                await self._merge_entities(best_entity.uid, target_ref, source_uid, rel_type)
            # Add relationship to best match
            self.gm.graph.add_edge(source_uid, best_entity.uid, rel_type, edge_source="auto_repair")
            self._update_source_relationships(source_uid, best_entity.uid, rel_type)
            self.stats["resolved"] += 1
            return True, best_entity.uid

        elif score >= self.medium_threshold:
            # Medium confidence: create similar entity
            if self.auto_create:
                new_uid = await self._create_similar_entity(best_entity, target_ref, source_uid, rel_type)
                if new_uid:
                    self.stats["resolved"] += 1
                    return True, new_uid
            else:
                # Fallback to using best match
                self.gm.graph.add_edge(source_uid, best_entity.uid, rel_type, edge_source="auto_repair")
                self._update_source_relationships(source_uid, best_entity.uid, rel_type)
                self.stats["resolved"] += 1
                return True, best_entity.uid

        elif score >= self.low_threshold and self.auto_create:
            # Low but non-zero: create new entity from scratch
            new_uid = await self._create_entity_from_scratch(target_ref, source_uid, rel_type)
            if new_uid:
                self.stats["resolved"] += 1
                return True, new_uid

        # Could not resolve
        self.stats["skipped"] += 1
        logger.warning(f"Could not resolve relationship {source_uid} -> {target_ref} (score={score:.2f})")
        return False, None

    def _update_source_relationships(self, source_uid: str, target_uid: str, rel_type: str):
        """Update the source entity's L1 relationships list."""
        src_node = self.gm.store.get(source_uid)
        if src_node:
            rels = src_node.profile.l1.setdefault("relationships", [])
            if not any(r.get("target") == target_uid for r in rels):
                rels.append({"target": target_uid, "type": rel_type})
                self.gm.store.update_entity_level(source_uid, "l1", src_node.profile.l1)

    async def repair_all_relationships(self) -> Dict[str, int]:
        """Scan all entities and repair all relationships."""
        self.stats = {"resolved": 0, "merged": 0, "created": 0, "failed": 0, "skipped": 0}

        for node in self.gm.store.all_nodes():
            rels = node.profile.l1.get("relationships", [])
            if not rels:
                continue

            new_rels = []
            for rel in rels:
                target_ref = rel.get("target")
                if not target_ref:
                    continue

                # Try simple resolution first
                existing_uid = self.gm._resolve_entity_uid(target_ref)
                if existing_uid:
                    new_rels.append({"target": existing_uid, "type": rel.get("type")})
                    continue

                # Attempt intelligent repair
                success, resolved_uid = await self.repair_relationship(node.uid, target_ref, rel.get("type"))
                if success and resolved_uid:
                    new_rels.append({"target": resolved_uid, "type": rel.get("type")})
                else:
                    # Log and skip this relationship
                    logger.debug(f"Skipping broken relationship: {node.uid} -> {target_ref}")

            if len(new_rels) != len(rels):
                node.profile.l1["relationships"] = new_rels
                self.gm.store.update_entity_level(node.uid, "l1", node.profile.l1)

        return self.stats
