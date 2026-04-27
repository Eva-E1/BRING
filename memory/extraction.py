"""
Custom extraction pipeline that uses llm_gateway’s Instructor capability
to produce typed entities and edges from an episode body.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from llm_gateway.client import LLMClient as GatewayLLMClient

logger = logging.getLogger(__name__)


# ── Pydantic models that the LLM will output ──────────────────────

class ExtractedEntity(BaseModel):
    name: str
    entity_type: str  # one of the keys from ENTITY_TYPES
    attributes: dict = Field(default_factory=dict)  # flexible attributes


class ExtractedEdge(BaseModel):
    source_name: str
    target_name: str
    edge_type: str  # e.g. "LocatedAt", "Knows"
    attributes: dict = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    entities: List[ExtractedEntity] = Field(default_factory=list)
    edges: List[ExtractedEdge] = Field(default_factory=list)


# ── Prompt builder ───────────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = """
You are an expert narrative analyst. From the following story excerpt, extract all 
significant entities and relationships using this ontology:

Entity types: Character, Location, Item, Event, Faction

For each entity, include its name and any attributes you find (e.g. for Character: alias, role, description, faction).

Edge types (relationships):
- LocatedAt(source: Character|Item, target: Location, since?, circumstance?)
- Knows(source: Character, target: Character, relationship?, trust_level?)
- Possesses(source: Character, target: Item, acquired_at?)
- ParticipatedIn(source: Character, target: Event, role?, outcome?)
- MemberOf(source: Character, target: Faction, joined_at?, rank?)
- OccurredAt(source: Event, target: Location)

Return a JSON object with "entities" and "edges" lists.
""".strip()


def build_extraction_prompt(episode_body: str) -> str:
    return f"{_EXTRACTION_SYSTEM_PROMPT}\n\nStory excerpt:\n{episode_body}"


# ── Conversion to Graphiti’s internal format ────────────────────

def convert_to_graphiti_entities_edges(
    result: ExtractionResult,
) -> tuple[list[dict], list[dict]]:
    """
    Convert our structured extraction result into the dictionaries that
    Graphiti’s add_episode expects when using `extraction_function`.
    (Graphiti expects list of node dicts and list of edge dicts.)
    """
    nodes = []
    for ent in result.entities:
        node = {
            "name": ent.name,
            "type": ent.entity_type,
            **ent.attributes,  # flattened
        }
        nodes.append(node)

    edges = []
    for edge in result.edges:
        edge_dict = {
            "source_name": edge.source_name,
            "target_name": edge.target_name,
            "edge_type": edge.edge_type,
            **edge.attributes,
        }
        edges.append(edge_dict)

    return nodes, edges


# ── Extraction function signature expected by Graphiti ──────────

async def structured_extraction(
    episode_body: str,
    gateway: GatewayLLMClient,
) -> tuple[list[dict], list[dict]]:
    """
    Call the gateway with Instructor to get a typed ExtractionResult,
    then convert to the format understood by Graphiti.
    """
    prompt = build_extraction_prompt(episode_body)
    llm_response = await gateway.generate(
        prompt,
        response_model=ExtractionResult,
    )
    if not llm_response.text:
        raise ValueError("Empty extraction response")
    # The gateway with Instructor returns a JSON string that we can parse
    result = ExtractionResult.model_validate_json(llm_response.text)
    return convert_to_graphiti_entities_edges(result)
