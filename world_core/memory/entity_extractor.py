"""Entity extraction and resolution for cognitive memory system."""
import logging
from typing import Dict, List, Optional, Set
from uuid import uuid4
from datetime import datetime

from world_builder.llm import LLMClient
from .world_memory import WorldMemory, WorldMemoryEntry, MemoryMetadata

logger = logging.getLogger(__name__)

class EntityExtractor:
    """Extracts typed entities from text and resolves aliases."""

    def __init__(self, llm: LLMClient, memory: "WorldMemory"):
        self.llm = llm
        self.memory = memory
        self.canonical_map: Dict[str, str] = {}  # alias -> canonical
        self.entity_attributes: Dict[str, dict] = {}  # canonical -> attributes

    async def extract_from_text(
        self,
        text: str,
        source_id: str
    ) -> List[WorldMemoryEntry]:
        """Extract entities from a text and return memory entries for them."""
        prompt = f"""
Extract all named entities from the following text. For each entity, provide:
- name (the exact mention)
- type (person, pet, place, event, item, organization, concept)
- attributes (dictionary of relevant properties, e.g., {{"breed": "Golden Retriever"}} for a pet)

Return a JSON array of objects. If no entities are found, return an empty array.
Text: {text}
"""
        try:
            result = await self.llm.generate_json(prompt, temperature=0.2)
            if not isinstance(result, list):
                logger.warning(f"Entity extraction returned non-list: {type(result)}")
                return []

            entries = []
            for obj in result:
                if not isinstance(obj, dict):
                    continue

                name = obj.get("name")
                if not name:
                    continue

                etype = obj.get("type", "unknown")
                attrs = obj.get("attributes", {})

                canonical = await self._resolve_entity(name, etype, attrs)

                entry = WorldMemoryEntry(
                    id=str(uuid4()),
                    content=f"{canonical} is a {etype}" + (
                        f" with {attrs}" if attrs else ""
                    ),
                    timestamp=datetime.now(),
                    source_type="entity",
                    source_id=source_id,
                    memory_type="entity",
                    entity_uid=canonical,
                    tags=[etype],
                    metadata=MemoryMetadata(
                        immutable=False,
                        importance=0.7
                    ),
                    linked_entity_uids=[],
                )
                entries.append(entry)

            return entries

        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return []

    async def _resolve_entity(
        self,
        name: str,
        etype: str,
        attrs: dict
    ) -> str:
        """Resolve alias to canonical name, merging attributes."""
        lower_name = name.lower()

        # Check existing alias map
        if lower_name in self.canonical_map:
            canonical = self.canonical_map[lower_name]
            # Merge attributes
            if canonical in self.entity_attributes:
                self.entity_attributes[canonical].update(attrs)
            return canonical

        # Search existing entity memories for similar name/type
        try:
            similar = await self.memory.retrieve(
                query=name,
                top_k=5,
                source_type_filter={"entity"},
                min_importance=0.0
            )

            for mem in similar:
                if mem.get("source_type") == "entity":
                    cand = mem.get("source")  # entity_uid stored in source
                    if cand and (cand.lower() == lower_name or self._similar_name(name, cand)):
                        self.canonical_map[lower_name] = cand
                        # Merge any new attributes
                        if cand in self.entity_attributes:
                            self.entity_attributes[cand].update(attrs)
                        return cand
        except Exception as e:
            logger.debug(f"Entity resolution search failed: {e}")

        # New entity - use original name as canonical
        canonical = name
        self.canonical_map[lower_name] = canonical
        self.entity_attributes[canonical] = attrs
        return canonical

    @staticmethod
    def _similar_name(a: str, b: str) -> bool:
        """Check if two names are similar (one contains the other)."""
        return a.lower() in b.lower() or b.lower() in a.lower()

    async def update_entity_attributes(
        self,
        entity_uid: str,
        attributes: dict
    ):
        """Update attributes for an existing entity."""
        if entity_uid in self.entity_attributes:
            self.entity_attributes[entity_uid].update(attributes)
        else:
            self.entity_attributes[entity_uid] = attributes

    def get_entity_info(self, entity_uid: str) -> Optional[dict]:
        """Get stored information about an entity."""
        return self.entity_attributes.get(entity_uid)

    def get_canonical_name(self, alias: str) -> Optional[str]:
        """Get the canonical name for an alias."""
        return self.canonical_map.get(alias.lower())
