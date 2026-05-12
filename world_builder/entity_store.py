"""In-memory store for EntityNode objects with JSON persistence."""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from .entity_profile import EntityNode, LayeredProfile

class EntityStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self._entities: Dict[str, EntityNode] = {}
        self._by_type: Dict[str, List[str]] = {}  # type -> list of uids
        self._load()

    def _load(self):
        if self.store_path.exists():
            data = json.loads(self.store_path.read_text(encoding='utf-8'))
            for item in data:
                node = EntityNode(
                    uid=item["uid"],
                    name=item["name"],
                    entity_type=item["entity_type"],
                    profile=LayeredProfile.from_dict(item["profile"]),
                    group_id=item.get("group_id", ""),
                    created_at=item.get("created_at", 0.0),
                    updated_at=item.get("updated_at", 0.0),
                )
                self._entities[node.uid] = node
                self._by_type.setdefault(node.entity_type, []).append(node.uid)
            self._rebuild_indices()

    def _rebuild_indices(self):
        self._by_type.clear()
        for uid, node in self._entities.items():
            self._by_type.setdefault(node.entity_type, []).append(uid)

    def save(self):
        serialized = []
        for node in self._entities.values():
            serialized.append({
                "uid": node.uid,
                "name": node.name,
                "entity_type": node.entity_type,
                "profile": node.profile.to_dict(),
                "group_id": node.group_id,
                "created_at": node.created_at,
                "updated_at": node.updated_at,
            })
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding='utf-8')

    def add(self, node: EntityNode):
        node.updated_at = time.time()
        self._entities[node.uid] = node
        self._by_type.setdefault(node.entity_type, []).append(node.uid)
        self.save()

    def get(self, uid: str) -> Optional[EntityNode]:
        return self._entities.get(uid)

    def get_by_name_and_type(self, name: str, entity_type: str) -> Optional[EntityNode]:
        uid = f"{entity_type}:{name}"
        return self.get(uid)

    def list_by_type(self, entity_type: str) -> List[EntityNode]:
        uids = self._by_type.get(entity_type, [])
        return [self._entities[uid] for uid in uids if uid in self._entities]

    def all_nodes(self) -> List[EntityNode]:
        return list(self._entities.values())

    def update_entity_level(self, uid: str, level: str, data: dict):
        """Update a single level (l1, l2, l3) of an entity's profile and save."""
        node = self._entities.get(uid)
        if not node:
            return False
        setattr(node.profile, level, data)
        node.updated_at = time.time()
        self.save()
        return True

    def search(self, query: str, entity_type: Optional[str] = None) -> List[EntityNode]:
        q = query.lower()
        results = []
        for node in self.all_nodes():
            if entity_type and node.entity_type != entity_type:
                continue
            if q in node.name.lower():
                results.append(node)
                continue
            l1 = node.profile.l1
            if q in str(l1.get("summary", "")).lower():
                results.append(node)
                continue
            tags = l1.get("tags", [])
            if any(q in tag.lower() for tag in tags):
                results.append(node)
                continue
            desc = node.profile.l2.get("description", "")
            if q in str(desc).lower():
                results.append(node)
                continue
        return results
