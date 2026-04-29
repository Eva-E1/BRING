"""
High-accuracy multi-stage extraction pipeline for Mushoku Tensei.

Accuracy improvements:
- smaller semantic extraction units inside each segment
- typed structured responses for every stage
- deterministic merge/deduplication across units
- domain-specific prompts aimed at narrative fidelity over recall inflation
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from time import perf_counter
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:
    from llm_gateway.client import LLMClient as GatewayLLMClient

logger = logging.getLogger(__name__)

ENTITY_EXTRACTION_PROMPT = """
You are an expert narrative analyst for the light novel Mushoku Tensei.

Extract only entities that are clearly grounded in the excerpt. Prefer precision
over recall. Do not invent full names, backstory, affiliations, or abilities that
are not explicitly supported by the text.

Entity types:
- Character: name, alias, role, description, faction
- Location: name, type (continent, town, building, room, region), description, region
- Item: name, type (weapon, tool, artifact, clothing, object), description
- Event: name, description, event_type (battle, meeting, training, ceremony, travel, conflict, discovery)
- Faction: name, description
- Ability: name, category (attack, healing, summoning, barrier, unique, elemental, swordsmanship), description, prerequisites
- WorldRule: name, category (magic_system, racial_trait, historical_law, geography, social_norm), description
- HistoricalEvent: name, year_start, year_end, description
- Arc: name, volume, description
- Concept: name, description

Rules:
- Use the exact surface form from the text when possible.
- If a mention is generic and cannot be resolved safely, keep it generic rather than hallucinating.
- Put all extracted properties inside `attributes`.
- Omit empty attributes.

Return ONLY a JSON object:
{
  "entities": [
    { "name": "Rudeus", "type": "Character", "attributes": { "role": "young magician" } }
  ]
}
"""

RELATIONSHIP_EXTRACTION_PROMPT = """
You are an expert narrative analyst for Mushoku Tensei.

Given the excerpt and the entity list, extract only relationships that are
explicitly stated or strongly implied within the excerpt itself.

Relationship types:
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
- InvolvesConcept(source, target)   : Character|Event|Arc|WorldRule|Ability -> Concept (attributes: relevance)

Rules:
- Only emit relationships where both source and target are present in the provided entity list.
- Prefer no edge over a weak or speculative edge.
- If trust_level is unknown, omit it.
- Keep attributes concise and text-grounded.

Return ONLY a JSON object:
{
  "relationships": [
    { "source": "Rudeus", "target": "Roxy", "type": "Knows", "attributes": { "relationship": "student-teacher" } }
  ]
}
"""

TIME_MARKER_PROMPT = """
You are extracting temporal evidence from a Mushoku Tensei excerpt.

Extract only phrases that directly indicate time, age, sequence, duration, or
calendar reference. Preserve the wording closely.

Return ONLY a JSON object:
{
  "time_markers": ["Rudeus was five years old", "two years later"]
}
"""


class ExtractedEntity(BaseModel):
    name: str
    type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class EntityExtractionResult(BaseModel):
    entities: List[ExtractedEntity] = Field(default_factory=list)


class ExtractedEdge(BaseModel):
    source: str
    target: str
    type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class RelationshipExtractionResult(BaseModel):
    relationships: List[ExtractedEdge] = Field(default_factory=list)


class TimeMarkerExtractionResult(BaseModel):
    time_markers: List[str] = Field(default_factory=list)


class ExtractionResultV2(BaseModel):
    entities: List[Any] = Field(default_factory=list)
    edges: List[Any] = Field(default_factory=list)
    time_markers: List[str] = Field(default_factory=list)


async def structured_extraction_v2(
    episode_body: str,
    gateway: GatewayLLMClient,
    *,
    max_unit_chars: int = 700,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
) -> ExtractionResultV2:
    """
    Perform multi-stage extraction over smaller semantic units and merge results.
    """
    extraction_units = _build_extraction_units(episode_body, max_unit_chars=max_unit_chars)
    if not extraction_units:
        return ExtractionResultV2()

    merged_entities: "OrderedDict[tuple[str, str], dict]" = OrderedDict()
    merged_edges: "OrderedDict[str, dict]" = OrderedDict()
    merged_markers: List[str] = []

    total_units = len(extraction_units)
    for unit_index, unit in enumerate(extraction_units, start=1):
        unit_started = perf_counter()
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "unit_start",
                    "unit_index": unit_index,
                    "unit_total": total_units,
                    "unit_length": len(unit),
                }
            )

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage_start",
                    "unit_index": unit_index,
                    "unit_total": total_units,
                    "stage": "entities",
                }
            )
        entities = await _extract_entities(unit, gateway)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage_end",
                    "unit_index": unit_index,
                    "unit_total": total_units,
                    "stage": "entities",
                    "count": len(entities),
                }
            )
        for entity in entities:
            _merge_entity(merged_entities, entity)

        if entities:
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "stage_start",
                        "unit_index": unit_index,
                        "unit_total": total_units,
                        "stage": "relationships",
                    }
                )
            relationships = await _extract_relationships(unit, entities, gateway)
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "stage_end",
                        "unit_index": unit_index,
                        "unit_total": total_units,
                        "stage": "relationships",
                        "count": len(relationships),
                    }
                )
            for edge in relationships:
                _merge_edge(merged_edges, edge)
        elif progress_callback is not None:
            progress_callback(
                {
                    "event": "stage_skip",
                    "unit_index": unit_index,
                    "unit_total": total_units,
                    "stage": "relationships",
                    "reason": "no_entities",
                }
            )

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage_start",
                    "unit_index": unit_index,
                    "unit_total": total_units,
                    "stage": "time",
                }
            )
        time_markers = await _extract_time_markers(unit, gateway)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "stage_end",
                    "unit_index": unit_index,
                    "unit_total": total_units,
                    "stage": "time",
                    "count": len(time_markers),
                }
            )
        merged_markers.extend(time_markers)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "unit_end",
                    "unit_index": unit_index,
                    "unit_total": total_units,
                    "elapsed": perf_counter() - unit_started,
                    "entity_total": len(merged_entities),
                    "edge_total": len(merged_edges),
                    "time_total": len(merged_markers),
                }
            )

    final_entities = list(merged_entities.values())
    final_edges = _filter_edges_by_known_entities(list(merged_edges.values()), final_entities)
    final_markers = _dedupe_strings(merged_markers)

    if progress_callback is not None:
        progress_callback(
            {
                "event": "segment_complete",
                "unit_total": total_units,
                "entity_total": len(final_entities),
                "edge_total": len(final_edges),
                "time_total": len(final_markers),
            }
        )

    return ExtractionResultV2(
        entities=final_entities,
        edges=final_edges,
        time_markers=final_markers,
    )


async def _extract_entities(unit_text: str, gateway: GatewayLLMClient) -> List[dict]:
    prompt = f"{ENTITY_EXTRACTION_PROMPT}\n\nExcerpt:\n{unit_text}"
    response = await gateway.generate(prompt, response_model=EntityExtractionResult)
    try:
        entities = EntityExtractionResult.model_validate_json(response.text).entities
    except ValidationError as exc:
        logger.error("Failed to parse entities: %s", exc)
        return []

    cleaned: List[dict] = []
    for entity in entities:
        name = entity.name.strip()
        entity_type = entity.type.strip()
        if not name or not entity_type:
            continue
        cleaned.append(
            {
                "name": name,
                "entity_type": entity_type,
                "attributes": _clean_attributes(entity.attributes),
            }
        )
    return cleaned


async def _extract_relationships(
    unit_text: str,
    entities: List[dict],
    gateway: GatewayLLMClient,
) -> List[dict]:
    entity_list_str = ", ".join(entity["name"] for entity in entities[:50])
    prompt = (
        f"{RELATIONSHIP_EXTRACTION_PROMPT}\n\n"
        f"Entities in this excerpt:\n{entity_list_str}\n\n"
        f"Excerpt:\n{unit_text}"
    )
    response = await gateway.generate(prompt, response_model=RelationshipExtractionResult)
    try:
        relationships = RelationshipExtractionResult.model_validate_json(response.text).relationships
    except ValidationError as exc:
        logger.error("Failed to parse relationships: %s", exc)
        return []

    entity_names = {entity["name"] for entity in entities}
    cleaned: List[dict] = []
    for edge in relationships:
        source = edge.source.strip()
        target = edge.target.strip()
        edge_type = edge.type.strip()
        if not source or not target or not edge_type:
            continue
        if source not in entity_names or target not in entity_names:
            continue
        cleaned.append(
            {
                "source_name": source,
                "target_name": target,
                "edge_type": edge_type,
                "attributes": _clean_attributes(edge.attributes),
            }
        )
    return cleaned


async def _extract_time_markers(unit_text: str, gateway: GatewayLLMClient) -> List[str]:
    prompt = f"{TIME_MARKER_PROMPT}\n\nExcerpt:\n{unit_text}"
    response = await gateway.generate(prompt, response_model=TimeMarkerExtractionResult)
    try:
        time_markers = TimeMarkerExtractionResult.model_validate_json(response.text).time_markers
    except ValidationError:
        return []
    return [marker.strip() for marker in time_markers if marker and marker.strip()]


def _build_extraction_units(text: str, *, max_unit_chars: int) -> List[str]:
    text = text.strip()
    if not text:
        return []

    heading, remainder = _split_heading(text)
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n+", remainder) if block.strip()]
    if not paragraphs:
        paragraphs = [remainder.strip()]

    units: List[str] = []
    current_parts: List[str] = []
    current_len = 0

    for paragraph in paragraphs:
        pieces = [paragraph] if len(paragraph) <= max_unit_chars else _split_long_text(paragraph, max_unit_chars)
        for piece in pieces:
            projected = current_len + len(piece) + (2 if current_parts else 0)
            if current_parts and projected > max_unit_chars:
                units.append(_format_unit_text(heading, current_parts))
                current_parts = [piece]
                current_len = len(piece)
            else:
                current_parts.append(piece)
                current_len = projected

    if current_parts:
        units.append(_format_unit_text(heading, current_parts))

    return [unit for unit in units if unit.strip()]


def _split_heading(text: str) -> tuple[Optional[str], str]:
    lines = [line.rstrip() for line in text.splitlines()]
    if not lines:
        return None, ""

    heading_lines: List[str] = []
    body_start = 0
    for index, line in enumerate(lines[:3]):
        if re.match(r"^(Volume\s+\d+|Chapter\s+\d+|Prologue|Epilogue|Interlude|Extra(?:\s+Chapter)?)\b", line, re.I):
            heading_lines.append(line.strip())
            body_start = index + 1
        elif heading_lines:
            break
        else:
            break

    if not heading_lines:
        return None, text
    heading = "\n".join(heading_lines).strip()
    remainder = "\n".join(lines[body_start:]).strip()
    return heading, remainder


def _format_unit_text(heading: Optional[str], parts: List[str]) -> str:
    body = "\n\n".join(part.strip() for part in parts if part.strip()).strip()
    if heading:
        return f"{heading}\n\n{body}".strip()
    return body


def _split_long_text(text: str, max_unit_chars: int) -> List[str]:
    sentences = [item.strip() for item in re.split(r"(?<=[.!?\"'])\s+", text) if item.strip()]
    if len(sentences) <= 1:
        return _split_by_words(text, max_unit_chars)

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for sentence in sentences:
        if len(sentence) > max_unit_chars:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_len = 0
            chunks.extend(_split_by_words(sentence, max_unit_chars))
            continue

        projected = current_len + len(sentence) + (1 if current else 0)
        if current and projected > max_unit_chars:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len = projected
    if current:
        chunks.append(" ".join(current).strip())
    return chunks


def _split_by_words(text: str, max_unit_chars: int) -> List[str]:
    words = text.split()
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for word in words:
        if len(word) > max_unit_chars:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_len = 0
            chunks.extend(word[index : index + max_unit_chars] for index in range(0, len(word), max_unit_chars))
            continue

        projected = current_len + len(word) + (1 if current else 0)
        if current and projected > max_unit_chars:
            chunks.append(" ".join(current).strip())
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = projected
    if current:
        chunks.append(" ".join(current).strip())
    return chunks


def _merge_entity(merged_entities: "OrderedDict[tuple[str, str], dict]", entity: dict) -> None:
    key = (_normalize_name(entity["name"]), entity["entity_type"])
    existing = merged_entities.get(key)
    if existing is None:
        merged_entities[key] = entity
        return

    existing["name"] = _prefer_name(existing["name"], entity["name"])
    existing["attributes"] = _merge_attributes(existing["attributes"], entity["attributes"])


def _merge_edge(merged_edges: "OrderedDict[str, dict]", edge: dict) -> None:
    edge_key = _edge_key(edge)
    existing = merged_edges.get(edge_key)
    if existing is None:
        merged_edges[edge_key] = edge
        return
    existing["attributes"] = _merge_attributes(existing["attributes"], edge["attributes"])


def _filter_edges_by_known_entities(edges: List[dict], entities: List[dict]) -> List[dict]:
    known_names = {_normalize_name(entity["name"]) for entity in entities}
    filtered: List[dict] = []
    for edge in edges:
        if _normalize_name(edge["source_name"]) not in known_names:
            continue
        if _normalize_name(edge["target_name"]) not in known_names:
            continue
        filtered.append(edge)
    return filtered


def _edge_key(edge: dict) -> str:
    normalized_attrs = tuple(sorted((str(k), str(v)) for k, v in edge.get("attributes", {}).items()))
    return repr(
        (
            _normalize_name(edge["source_name"]),
            _normalize_name(edge["target_name"]),
            edge["edge_type"],
            normalized_attrs,
        )
    )


def _clean_attributes(attributes: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if value is None:
            continue
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                continue
            cleaned[key] = normalized
        else:
            cleaned[key] = value
    return cleaned


def _merge_attributes(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if key not in merged:
            merged[key] = value
            continue
        if merged[key] == value:
            continue
        merged[key] = _prefer_attribute_value(merged[key], value)
    return merged


def _prefer_attribute_value(current: Any, candidate: Any) -> Any:
    if current in (None, "", []):
        return candidate
    if candidate in (None, "", []):
        return current
    if isinstance(current, str) and isinstance(candidate, str):
        return candidate if len(candidate) > len(current) else current
    return current


def _prefer_name(current: str, candidate: str) -> str:
    if _normalize_name(current) == _normalize_name(candidate):
        return candidate if len(candidate) > len(current) else current
    return current


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _dedupe_strings(values: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", value.strip().lower())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value.strip())
    return result
