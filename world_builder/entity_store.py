"""
BRING v2 — EntityStore is now a thin adapter over world_core.store.UnifiedEntityStore.
Maintains backward compatibility while using the optimized core.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from world_core.models import EntityNode, LayeredProfile
from world_core.store import UnifiedEntityStore


class EntityStore:
    """
    Backward-compatible adapter over UnifiedEntityStore.
    Delegates all operations to the unified store with O(1) lookups.
    """

    def __init__(self, store_path: Path):
        self._unified = UnifiedEntityStore(store_path, auto_save=True)

    @property
    def unified(self) -> UnifiedEntityStore:
        return self._unified

    def _load(self):
        pass  # UnifiedEntityStore loads on init

    def save(self):
        self._unified.save()

    def add(self, node: EntityNode) -> EntityNode:
        return self._unified.add(node)

    def get(self, uid: str) -> Optional[EntityNode]:
        return self._unified.get(uid)

    def get_by_name_and_type(self, name: str, entity_type: str) -> Optional[EntityNode]:
        return self._unified.get_by_name_and_type(name, entity_type)

    def list_by_type(self, entity_type: str) -> List[EntityNode]:
        return self._unified.list_by_type(entity_type)

    def all_nodes(self) -> List[EntityNode]:
        return self._unified.all_nodes()

    def update_entity_level(self, uid: str, level: str, data: dict) -> bool:
        return self._unified.update_entity_level(uid, level, data)

    def search(self, query: str, entity_type: Optional[str] = None) -> List[EntityNode]:
        return self._unified.search(query, entity_type)

