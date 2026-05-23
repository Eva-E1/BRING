"""Load entities from JSON and return a list."""
import json
from pathlib import Path
from typing import List
from world_core.utils import atomic_write_json
from .models import Entity, LayeredProfile

def load_entities(db_path: Path) -> List[Entity]:
    file_path = db_path / "entities.json"
    if not file_path.exists():
        raise FileNotFoundError(f"entities.json not found at {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    entities = []
    for item in raw:
        profile = LayeredProfile.from_dict(item["profile"])
        entities.append(Entity(
            uid=item["uid"],
            name=item["name"],
            entity_type=item["entity_type"],
            profile=profile,
            group_id=item.get("group_id", ""),
            created_at=item.get("created_at", 0.0),
            updated_at=item.get("updated_at", 0.0),
        ))
    return entities


def save_entities(db_path: Path, entities: List[Entity]) -> None:
    """Save entities back to JSON file."""
    file_path = db_path / "entities.json"
    data = []
    for e in entities:
        data.append({
            "uid": e.uid,
            "name": e.name,
            "entity_type": e.entity_type,
            "profile": e.profile.to_dict(),
            "group_id": e.group_id,
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        })
    atomic_write_json(file_path, data)
