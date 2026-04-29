"""
Construct multi-layer graph payloads from merged extraction results.

Layering is intentionally conservative: factual entities stay in `fact`,
world/system abstractions stay in `rule` or `concept`, and explicit narrative
containers stay in `story`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List
from uuid import uuid4

# ── Layer constants ─────────────────────────────────────────────
LAYER_FACT = "fact"
LAYER_RULE = "rule"
LAYER_STORY = "story"
LAYER_CONCEPT = "concept"

LAYER_BY_TYPE = {
    "Character": LAYER_FACT,
    "Location": LAYER_FACT,
    "Item": LAYER_FACT,
    "Event": LAYER_STORY,
    "Faction": LAYER_FACT,
    "Ability": LAYER_RULE,
    "WorldRule": LAYER_RULE,
    "HistoricalEvent": LAYER_STORY,
    "Arc": LAYER_STORY,
    "Concept": LAYER_CONCEPT,
}


def build_layered_graph(
    merged_data: List[dict],
    group_id: str = "Mushoku-Tensei",
) -> List[dict]:
    """
    merged_data : list of dicts, each containing raw segment text plus structured extraction.
    Returns a list of episode dicts suitable for MemoryEngine.add_episodes_bulk().
    Structured entities and edges are attached in metadata so the memory layer keeps
    the richer Mushoku annotations available alongside Graphiti ingestion.
    """
    episodes = []
    for idx, segment in enumerate(merged_data):
        entities = segment.get("entities", [])
        edges = segment.get("edges", [])
        raw_text = (segment.get("text") or "").strip()
        story_time = segment.get("story_time", datetime(1, 1, 1) + timedelta(days=idx))

        entity_lookup = {}
        for ent in entities:
            ent_type = ent.get("entity_type", ent.get("type", "Character"))
            layer = determine_entity_layer(ent)
            ent.setdefault("attributes", {})
            ent["attributes"]["layer"] = layer
            entity_lookup[ent["name"]] = ent

        for edge in edges:
            edge.setdefault("attributes", {})
            edge["attributes"]["layer"] = determine_edge_layer(edge, entity_lookup)

        if not raw_text:
            body_lines = [f"Segment {idx + 1} - Story time: {story_time.isoformat()}"]
            body_lines.append("Entities:")
            for ent in entities:
                ent_type = ent.get("entity_type", ent.get("type", "Character"))
                body_lines.append(
                    f"- {ent_type}: {ent['name']} "
                    f"(layer={LAYER_BY_TYPE.get(ent_type, 'fact')})"
                )
            body_lines.append("Relationships:")
            for edge in edges:
                body_lines.append(
                    f"- {edge['edge_type']}: {edge['source_name']} -> {edge['target_name']}"
                )
            raw_text = "\n".join(body_lines)

        episode = {
            "name": f"segment_{idx+1:04d}",
            "body": raw_text,
            "reference_time": story_time,
            "group_id": group_id,
            "uuid": str(uuid4()),
            "metadata": {
                "entities": entities,
                "edges": edges,
                "volume": segment.get("volume"),
                "chapter": segment.get("chapter"),
                "heading": segment.get("heading"),
                "scene_index": segment.get("scene_index"),
                "segment_kind": segment.get("segment_kind"),
                "time_markers": list(segment.get("time_markers", [])),
            },
        }
        episodes.append(episode)
    return episodes


def determine_entity_layer(entity: dict) -> str:
    ent_type = entity.get("entity_type", entity.get("type", "Character"))
    attributes = entity.get("attributes", {}) or {}

    if ent_type in {"WorldRule", "Ability"}:
        return LAYER_RULE
    if ent_type in {"HistoricalEvent", "Arc", "Event"}:
        return LAYER_STORY
    if ent_type == "Concept":
        return LAYER_CONCEPT
    if ent_type == "Faction":
        description = str(attributes.get("description", "")).lower()
        if any(token in description for token in ("religion", "doctrine", "school of thought", "belief")):
            return LAYER_CONCEPT
    return LAYER_BY_TYPE.get(ent_type, LAYER_FACT)


def determine_edge_layer(edge: dict, entity_lookup: dict) -> str:
    edge_type = edge.get("edge_type", "")
    source = entity_lookup.get(edge.get("source_name"))
    target = entity_lookup.get(edge.get("target_name"))
    source_layer = source.get("attributes", {}).get("layer") if source else None
    target_layer = target.get("attributes", {}).get("layer") if target else None

    if edge_type in {"Causes", "PartOfArc", "ParticipatedIn", "OccurredAt"}:
        return LAYER_STORY
    if edge_type in {"HasAbility", "Governs", "InvolvesConcept"}:
        return LAYER_RULE if LAYER_RULE in {source_layer, target_layer} else LAYER_CONCEPT
    if source_layer == target_layer and source_layer is not None:
        return source_layer
    return LAYER_FACT
