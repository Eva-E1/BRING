"""
Constructs multi‑layer graph payloads from merged extraction results,
ready for ingestion into MemoryEngine.
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
    "Event": LAYER_FACT,
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
    Structured entities and edges are attached in metadata so ingestion can reuse
    the precomputed extraction without re-calling the LLM or leaking schema details.
    """
    episodes = []
    for idx, segment in enumerate(merged_data):
        entities = segment.get("entities", [])
        edges = segment.get("edges", [])
        raw_text = (segment.get("text") or "").strip()
        story_time = segment.get("story_time", datetime(1, 1, 1) + timedelta(days=idx))

        # Attach layer to each entity
        for ent in entities:
            ent_type = ent.get("entity_type", ent.get("type", "Character"))
            layer = LAYER_BY_TYPE.get(ent_type, "fact")
            ent.setdefault("attributes", {})
            ent["attributes"]["layer"] = layer

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
                "time_markers": list(segment.get("time_markers", [])),
            },
        }
        episodes.append(episode)
    return episodes
