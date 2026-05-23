"""
BRING v2 — Unified entity store with O(1) lookups and batch saves.
Replaces both world_builder/entity_store.py and the store logic in world_explorer/store.py.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .models import EntityNode, EntityType, LayeredProfile
from .utils import atomic_write_json

logger = logging.getLogger(__name__)


class NameIndex:
    """
    Multi-strategy name → UID resolution index.
    O(1) for exact matches, O(k) for token-based fuzzy (where k = entities sharing a token).
    """
    __slots__ = ("_by_uid", "_by_name_lower", "_by_token", "_by_type", "_dirty")

    def __init__(self):
        self._by_uid: Dict[str, str] = {}               # uid → uid (identity map for valid check)
        self._by_name_lower: Dict[str, str] = {}        # lowercase full name → uid
        self._by_token: Dict[str, List[str]] = defaultdict(list)  # token → [uid, ...]
        self._by_type: Dict[str, List[str]] = defaultdict(list)   # entity_type → [uid, ...]
        self._dirty = True

    def add(self, uid: str, name: str, entity_type: str) -> None:
        self._by_uid[uid] = uid
        key = name.strip().lower()
        self._by_name_lower[key] = uid
        for token in key.split():
            self._by_token[token].append(uid)
        self._by_type[entity_type].append(uid)

    def remove(self, uid: str, name: str, entity_type: str) -> None:
        self._by_uid.pop(uid, None)
        key = name.strip().lower()
        self._by_name_lower.pop(key, None)
        for token in key.split():
            lst = self._by_token.get(token)
            if lst and uid in lst:
                lst.remove(uid)
        lst = self._by_type.get(entity_type)
        if lst and uid in lst:
            lst.remove(uid)

    def resolve(self, ref: str) -> Optional[str]:
        """Resolve a name/UID reference to a canonical UID. Returns None if not found."""
        if not ref or not isinstance(ref, str):
            return None
        ref = ref.strip()

        # 1. Direct UID match
        if ref in self._by_uid:
            return ref

        # 2. Case-insensitive full name
        low = ref.lower()
        uid = self._by_name_lower.get(low)
        if uid:
            return uid

        # 3. Strip type prefix and retry
        if ":" in ref and not ref.startswith("__"):
            after_colon = ref.split(":", 1)[1].strip()
            uid = self._by_name_lower.get(after_colon.lower())
            if uid:
                return uid

        # 4. Token-based fuzzy — only if exactly one candidate
        candidates: Set[str] = set()
        for token in low.split():
            for uid in self._by_token.get(token, []):
                candidates.add(uid)
        valid = [u for u in candidates if u in self._by_uid]
        return valid[0] if len(valid) == 1 else None

    def list_by_type(self, entity_type: str) -> List[str]:
        return [u for u in self._by_type.get(entity_type, []) if u in self._by_uid]

    @property
    def valid_uids(self) -> Set[str]:
        return set(self._by_uid.keys())

    def rebuild(self, entities: List[EntityNode]) -> None:
        """Full rebuild from entity list."""
        self._by_uid.clear()
        self._by_name_lower.clear()
        self._by_token.clear()
        self._by_type.clear()
        for node in entities:
            self.add(node.uid, node.name, node.entity_type)
        self._dirty = False


class UnifiedEntityStore:
    """
    Central entity storage with:
    - O(1) UID lookup, O(1) name lookup, O(k) fuzzy lookup
    - Batch save (dirty tracking — only writes when data has changed)
    - Thread-safe operations
    - Event callbacks for mutation notification
    """

    def __init__(self, store_path: Path, auto_save: bool = True):
        self.store_path = store_path
        self.auto_save = auto_save

        self._entities: Dict[str, EntityNode] = {}
        self._name_index = NameIndex()
        self._dirty_uids: Set[str] = set()
        self._deleted_uids: Set[str] = set()
        self._lock = threading.RLock()
        self._mutation_callbacks: List[Callable] = []
        self._last_save_time: float = 0.0

        self._load()

    # ── Loading ────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load entity store: {e}")
            return

        for item in raw:
            node = EntityNode.from_dict(item)
            self._entities[node.uid] = node
        self._name_index.rebuild(list(self._entities.values()))
        logger.info(f"Loaded {len(self._entities)} entities from {self.store_path}")

    # ── Core CRUD ──────────────────────────────────────────────────

    def add(self, node: EntityNode) -> EntityNode:
        with self._lock:
            node.updated_at = time.time()
            self._entities[node.uid] = node
            self._name_index.add(node.uid, node.name, node.entity_type)
            self._dirty_uids.add(node.uid)
            self._notify("add", node.uid)
            if self.auto_save:
                self.save()
        return node

    def get(self, uid: str) -> Optional[EntityNode]:
        return self._entities.get(uid)

    def get_by_name(self, name: str) -> Optional[EntityNode]:
        uid = self._name_index.resolve(name)
        return self._entities.get(uid) if uid else None

    def get_by_name_and_type(self, name: str, entity_type: str) -> Optional[EntityNode]:
        uid = f"{entity_type}:{name}"
        node = self._entities.get(uid)
        if node:
            return node
        # Fallback to name index
        resolved = self._name_index.resolve(name)
        if resolved:
            node = self._entities.get(resolved)
            if node and node.entity_type == entity_type:
                return node
        return None

    def remove(self, uid: str) -> bool:
        with self._lock:
            node = self._entities.pop(uid, None)
            if node is None:
                return False
            self._name_index.remove(uid, node.name, node.entity_type)
            self._deleted_uids.add(uid)
            self._notify("remove", uid)
            if self.auto_save:
                self.save()
        return True

    def update_entity_level(self, uid: str, level: str, data: Dict[str, Any]) -> bool:
        node = self._entities.get(uid)
        if not node:
            return False
        with self._lock:
            setattr(node.profile, level, data)
            node.updated_at = time.time()
            self._dirty_uids.add(uid)
            self._notify("update", uid)
            if self.auto_save:
                self.save()
        return True

    def update_entity_name(self, uid: str, new_name: str) -> bool:
        node = self._entities.get(uid)
        if not node:
            return False
        with self._lock:
            old_name = node.name
            self._name_index.remove(uid, old_name, node.entity_type)
            node.name = new_name
            node.uid = f"{node.entity_type}:{new_name}"
            self._name_index.add(node.uid, new_name, node.entity_type)
            node.updated_at = time.time()
            self._dirty_uids.add(uid)
            self._notify("rename", uid)
            if self.auto_save:
                self.save()
        return True

    # ── Queries ────────────────────────────────────────────────────

    def all_nodes(self) -> List[EntityNode]:
        return list(self._entities.values())

    def list_by_type(self, entity_type: str) -> List[EntityNode]:
        uids = self._name_index.list_by_type(entity_type)
        return [self._entities[u] for u in uids if u in self._entities]

    def search(self, query: str, entity_type: Optional[str] = None, limit: int = 20) -> List[EntityNode]:
        q = query.lower()
        results = []
        for node in self._entities.values():
            if entity_type and node.entity_type != entity_type:
                continue
            if q in node.name.lower():
                results.append(node)
                continue
            if q in str(node.profile.l1.get("summary", "")).lower():
                results.append(node)
                continue
            if any(q in tag.lower() for tag in node.profile.l1.get("tags", [])):
                results.append(node)
                continue
            desc = node.profile.l2.get("description", "")
            if q in str(desc).lower():
                results.append(node)
                continue
            if len(results) >= limit:
                break
        return results

    def count(self) -> int:
        return len(self._entities)

    def count_by_type(self) -> Dict[str, int]:
        result = defaultdict(int)
        for node in self._entities.values():
            result[node.entity_type] += 1
        return dict(result)

    def resolve_uid(self, ref: str) -> Optional[str]:
        """Public name resolution delegate."""
        return self._name_index.resolve(ref)

    @property
    def name_index(self) -> NameIndex:
        return self._name_index

    @property
    def valid_uids(self) -> Set[str]:
        return self._name_index.valid_uids

    # ── Persistence ────────────────────────────────────────────────

    def save(self) -> None:
        """Atomic write to disk. Only called when dirty."""
        serialized = [node.to_dict() for node in self._entities.values()]
        try:
            atomic_write_json(self.store_path, serialized)
            self._dirty_uids.clear()
            self._deleted_uids.clear()
            self._last_save_time = time.time()
        except OSError as e:
            logger.error(f"Failed to save entity store: {e}")

    def save_if_dirty(self) -> bool:
        if self._dirty_uids or self._deleted_uids:
            self.save()
            return True
        return False

    def batch_update(self, updates: List[tuple]) -> None:
        """
        Apply multiple updates in a single batch.
        updates: list of (uid, level, data) tuples.
        Only saves once at the end.
        """
        was_auto = self.auto_save
        self.auto_save = False
        try:
            for uid, level, data in updates:
                self.update_entity_level(uid, level, data)
        finally:
            self.auto_save = was_auto
            if was_auto:
                self.save()

    # ── Mutation Callbacks ─────────────────────────────────────────

    def on_mutation(self, callback: Callable) -> None:
        self._mutation_callbacks.append(callback)

    def _notify(self, action: str, uid: str) -> None:
        for cb in self._mutation_callbacks:
            try:
                cb(action, uid)
            except Exception as e:
                logger.warning(f"Mutation callback error: {e}")

