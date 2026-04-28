"""
Multi‑stage extraction pipeline for English light novels.
Stage 1: Extract entities (all types)
Stage 2: Extract relationships between extracted entities
Stage 3: Extract time markers
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, List, Optional, Dict, Any

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:
    from llm_gateway.client import LLMClient as GatewayLLMClient

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Stage 1: Entity extraction
# ------------------------------------------------------------------

ENTITY_EXTRACTION_PROMPT = """
You are an expert narrative analyst. From the story excerpt below, extract all **entities** of the following types:

- Character: name, alias, role, description, faction
- Location: name, type (continent, town, building), description, region
- Item: name, type (weapon, tool, artifact), description
- Event: name, description, event_type (battle, meeting, training, ceremony)
- Faction: name, description
- Ability: name, category (attack, healing, summoning, barrier, unique), description, prerequisites
- WorldRule: name, category (magic_system, racial_trait, historical_law, geography), description
- HistoricalEvent: name, year_start, year_end, summary
- Arc: name, volume, description
- Concept: name, description

Return a JSON array with the following structure:
[
  { "name": "entity name", "type": "Character", "attributes": { "alias": "...", "role": "..." } },
  ...
]

**IMPORTANT:** Return ONLY the JSON array. Do NOT wrap it in backticks or markdown.
"""

class ExtractedEntity(BaseModel):
    name: str
    type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)

# ------------------------------------------------------------------
# Stage 2: Relationship extraction
# ------------------------------------------------------------------

RELATIONSHIP_EXTRACTION_PROMPT = """
Given the following story excerpt and a list of entities that appear in it, extract all **relationships** between them using these types:

- LocatedAt(source, target)         : Character|Item -> Location
- Knows(source, target)             : Character -> Character (attributes: relationship, trust_level)
- Possesses(source, target)         : Character -> Item (attributes: acquired_at)
- ParticipatedIn(source, target)    : Character -> Event (attributes: role, outcome)
- MemberOf(source, target)          : Character -> Faction (attributes: joined_at, rank)
- OccurredAt(source, target)        : Event -> Location
- HasAbility(source, target)        : Character -> Ability (attributes: acquired_at, proficiency)
- Governs(source, target)           : WorldRule -> Ability|Event|Faction|Character|Location
- PartOfArc(source, target)         : Event|HistoricalEvent|Character -> Arc (attributes: role)
- Causes(source, target)            : Event|HistoricalEvent|Ability -> Event|HistoricalEvent
- InvolvesConcept(source, target)   : any entity -> Concept (attributes: relevance)

Return a JSON array with objects:
[
  { "source": "entity name", "target": "entity name", "type": "Knows", "attributes": { "trust_level": "high" } },
  ...
]

**IMPORTANT:** Only include relationships where both source and target are in the provided entity list.
Return ONLY the JSON array.
"""

class ExtractedEdge(BaseModel):
    source: str
    target: str
    type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)

# ------------------------------------------------------------------
# Stage 3: Time marker extraction
# ------------------------------------------------------------------

TIME_MARKER_PROMPT = """
From the story excerpt below, extract all **time markers** – phrases that indicate when events happen.

Examples: "Rudeus is 5 years old", "Year 401 of the Armored Dragon Calendar", "two years later", "a month passed".

Return a JSON array of strings:
[ "marker 1", "marker 2", ... ]

**IMPORTANT:** Return ONLY the JSON array.
"""

# ------------------------------------------------------------------
# Helper: Clean JSON from markdown / extra text
# ------------------------------------------------------------------

def clean_json_response(text: str) -> str:
    text = text.strip()
    # Remove markdown code blocks
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # If array, find first '[' and last ']'
    if text.startswith('['):
        # find matching closing bracket
        bracket_count = 0
        for i, ch in enumerate(text):
            if ch == '[':
                bracket_count += 1
            elif ch == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    return text[:i+1]
    return text

# ------------------------------------------------------------------
# Main extraction orchestrator
# ------------------------------------------------------------------

async def structured_extraction_v2(
    episode_body: str,
    gateway: GatewayLLMClient,
) -> 'ExtractionResultV2':
    """
    Perform multi‑stage extraction: entities → relationships → time markers.
    Returns combined result.
    """
    # Stage 1: Entities
    entity_prompt = f"{ENTITY_EXTRACTION_PROMPT}\n\nStory excerpt:\n{episode_body}"
    entity_response = await gateway.generate(entity_prompt, response_model=None)
    clean_entities = clean_json_response(entity_response.text)
    try:
        entities_data = json.loads(clean_entities)
        if not isinstance(entities_data, list):
            raise ValueError("Entity extraction did not return a list")
        entities = [ExtractedEntity(**item) for item in entities_data]
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Failed to parse entities: {e}\nRaw: {entity_response.text[:200]}")
        entities = []

    # Stage 2: Relationships (only if we have entities)
    edges = []
    if entities:
        entity_names = [e.name for e in entities]
        entity_list_str = ", ".join(entity_names[:50])  # limit prompt size
        rel_prompt = (
            f"{RELATIONSHIP_EXTRACTION_PROMPT}\n\n"
            f"Entities in this excerpt:\n{entity_list_str}\n\n"
            f"Story excerpt:\n{episode_body}"
        )
        rel_response = await gateway.generate(rel_prompt, response_model=None)
        clean_rels = clean_json_response(rel_response.text)
        try:
            edges_data = json.loads(clean_rels)
            if isinstance(edges_data, list):
                edges = [ExtractedEdge(**item) for item in edges_data]
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Failed to parse relationships: {e}\nRaw: {rel_response.text[:200]}")

    # Stage 3: Time markers
    time_prompt = f"{TIME_MARKER_PROMPT}\n\nStory excerpt:\n{episode_body}"
    time_response = await gateway.generate(time_prompt, response_model=None)
    clean_time = clean_json_response(time_response.text)
    time_markers = []
    try:
        markers = json.loads(clean_time)
        if isinstance(markers, list):
            time_markers = [str(m) for m in markers]
    except json.JSONDecodeError:
        pass

    # Convert to final format expected by graph_builder
    # ExtractedEntity -> ExtEntityV2 (compatible with old schema)
    final_entities = []
    for ent in entities:
        final_entities.append({
            "name": ent.name,
            "entity_type": ent.type,
            "attributes": ent.attributes,
        })
    final_edges = []
    for edge in edges:
        final_edges.append({
            "source_name": edge.source,
            "target_name": edge.target,
            "edge_type": edge.type,
            "attributes": edge.attributes,
        })

    # Create a result object (mimics ExtractionResultV2 from previous version)
    class TempResult:
        def __init__(self, entities, edges, time_markers):
            self.entities = entities
            self.edges = edges
            self.time_markers = time_markers

    return TempResult(final_entities, final_edges, time_markers)


# For backward compatibility we keep ExtractionResultV2 as a dummy class
class ExtractionResultV2(BaseModel):
    entities: List[Any] = []
    edges: List[Any] = []
    time_markers: List[str] = []
