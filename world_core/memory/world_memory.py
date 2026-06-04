"""Revolutionary graph-based self-optimizing memory system."""
from __future__ import annotations

import asyncio
import json
import logging
import math
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

import numpy as np

from world_builder.llm import LLMClient

from .config import MemoryConfig, DEFAULT_CONFIG
from .scoring import MemoryScoringEngine
from .embedding_queue import EmbeddingQueue
from .faiss_index import IncrementalFAISSIndex
from .write_buffer import WriteBehindBuffer
from .partition import MemoryPartitionManager
from .clustering import ClusterEngine
from .optimizer import MemoryOptimizer

logger = logging.getLogger(__name__)

# Try to import FAISS
try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    faiss = None
    logger.warning("FAISS not installed, using linear search for memory retrieval")


# FAISS rebuild thresholds
FAISS_REBUILD_ENTRY_THRESHOLD = 200  # Rebuild after 200 new entries (was 50)
FAISS_REBUILD_FRAGMENTATION_THRESHOLD = 0.2  # Rebuild if fragmentation > 20%


class MemoryMetadata:
    """Enhanced metadata for memory entries with cognitive fields."""

    __slots__ = (
        'access_count', 'last_accessed', 'emotional_valence', 'story_relevance',
        'cluster_id', 'cluster_representative', 'immutable', 'importance'
    )

    def __init__(
        self,
        access_count: int = 0,
        last_accessed: Optional[datetime] = None,
        emotional_valence: float = 0.0,
        story_relevance: float = 0.5,
        cluster_id: Optional[str] = None,
        cluster_representative: bool = False,
        immutable: bool = False,
        importance: float = 0.5,
    ):
        self.access_count = access_count
        self.last_accessed = last_accessed or datetime.now()
        self.emotional_valence = emotional_valence
        self.story_relevance = story_relevance
        self.cluster_id = cluster_id
        self.cluster_representative = cluster_representative
        self.immutable = immutable
        self.importance = importance

    def to_dict(self) -> dict:
        return {
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat(),
            "emotional_valence": self.emotional_valence,
            "story_relevance": self.story_relevance,
            "cluster_id": self.cluster_id,
            "cluster_representative": self.cluster_representative,
            "immutable": self.immutable,
            "importance": self.importance,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryMetadata":
        return cls(
            access_count=d.get("access_count", 0),
            last_accessed=datetime.fromisoformat(d["last_accessed"]) if "last_accessed" in d else datetime.now(),
            emotional_valence=d.get("emotional_valence", 0.0),
            story_relevance=d.get("story_relevance", 0.5),
            cluster_id=d.get("cluster_id"),
            cluster_representative=d.get("cluster_representative", False),
            immutable=d.get("immutable", False),
            importance=d.get("importance", 0.5),
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Dictionary-like access for backward compatibility."""
        return getattr(self, key, default)

class WorldMemoryEntry:
    """Single memory entry in the unified world memory with cognitive fields."""

    __slots__ = (
        'id', 'content', 'timestamp', 'source_type', 'source_id',
        'importance', 'tags', 'node_uid', 'version', 'parent_id',
        'embedding', 'metadata', 'memory_type', 'entity_uid', 'linked_entity_uids',
        'supersedes', 'superseded_by', 'pain_keywords', 'salience', 'decayed_salience',
        'needs_clustering'
    )

    def __init__(
        self,
        id: str,
        content: str,
        timestamp: datetime,
        source_type: str,
        source_id: str,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        node_uid: Optional[str] = None,
        version: int = 1,
        parent_id: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[MemoryMetadata] = None,
        # Cognitive fields
        memory_type: str = "episodic",  # 'episodic', 'semantic', 'entity', 'procedural', 'archival'
        entity_uid: Optional[str] = None,
        linked_entity_uids: Optional[List[str]] = None,
        supersedes: Optional[List[str]] = None,
        superseded_by: Optional[List[str]] = None,
        pain_keywords: Optional[List[str]] = None,
        salience: float = 0.5,
    ):
        self.id = id
        self.content = content
        self.timestamp = timestamp
        self.source_type = source_type
        self.source_id = source_id
        self.importance = importance
        self.tags = tags or []
        self.node_uid = node_uid
        self.version = version
        self.parent_id = parent_id
        self.embedding = embedding
        self.metadata = metadata or MemoryMetadata(importance=importance)

        # Cognitive fields
        self.memory_type = memory_type
        self.entity_uid = entity_uid
        self.linked_entity_uids = linked_entity_uids or []
        self.supersedes = supersedes or []
        self.superseded_by = superseded_by or []
        self.pain_keywords = pain_keywords or []
        self.salience = salience
        self.decayed_salience = salience

        self.needs_clustering = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "source_type": self.source_type,
            "source_id": self.source_id,
            "importance": self.importance,
            "tags": self.tags,
            "node_uid": self.node_uid,
            "version": self.version,
            "parent_id": self.parent_id,
            "embedding": self.embedding,
            "metadata": self.metadata.to_dict() if self.metadata else {},
            # Cognitive fields
            "memory_type": self.memory_type,
            "entity_uid": self.entity_uid,
            "linked_entity_uids": self.linked_entity_uids,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "pain_keywords": self.pain_keywords,
            "salience": self.salience,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorldMemoryEntry":
        entry = cls(
            id=d["id"],
            content=d["content"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            source_type=d["source_type"],
            source_id=d["source_id"],
            importance=d.get("importance", 0.5),
            tags=d.get("tags", []),
            node_uid=d.get("node_uid"),
            version=d.get("version", 1),
            parent_id=d.get("parent_id"),
            embedding=d.get("embedding"),
            memory_type=d.get("memory_type", "episodic"),
            entity_uid=d.get("entity_uid"),
            linked_entity_uids=d.get("linked_entity_uids", []),
            supersedes=d.get("supersedes", []),
            superseded_by=d.get("superseded_by", []),
            pain_keywords=d.get("pain_keywords", []),
            salience=d.get("salience", 0.5),
        )
        if "metadata" in d and d["metadata"]:
            entry.metadata = MemoryMetadata.from_dict(d["metadata"])
        return entry

class SessionDeltaTracker:
    """Tracks session-level changes for delta-aware context retrieval."""

    def __init__(self):
        self.last_seen_timestamp: Dict[str, datetime] = {}
        self.last_retrieved_ids: Dict[str, Set[str]] = {}

    def update(
        self,
        session_id: str,
        retrieved_ids: Set[str],
        current_time: datetime
    ):
        self.last_seen_timestamp[session_id] = current_time
        self.last_retrieved_ids[session_id] = retrieved_ids

    def get_last_seen(self, session_id: str) -> Optional[datetime]:
        return self.last_seen_timestamp.get(session_id)

    def get_delta(
        self,
        session_id: str,
        current_ids: Set[str]
    ) -> Tuple[Set[str], Set[str], Set[str]]:
        """Return (new_ids, updated_ids, removed_ids)."""
        last_ids = self.last_retrieved_ids.get(session_id, set())

        new_ids = current_ids - last_ids
        removed_ids = last_ids - current_ids
        # Updated = intersection (simplified - could track actual updates)
        updated_ids = set()

        return new_ids, updated_ids, removed_ids

class SpeculativeCache:
    """Cache for pre-assembled context based on predicted queries."""

    def __init__(self, maxsize: int = 100, ttl_seconds: int = 300):
        self.cache: OrderedDict = OrderedDict()
        self.maxsize = maxsize
        self.ttl = ttl_seconds

    async def get(self, key: str) -> Optional[List[dict]]:
        if key in self.cache:
            entry, timestamp = self.cache[key]
            if (datetime.now() - timestamp).total_seconds() < self.ttl:
                self.cache.move_to_end(key)
                return entry
            else:
                del self.cache[key]
        return None

    async def set(self, key: str, value: List[dict]):
        if len(self.cache) >= self.maxsize:
            self.cache.popitem(last=False)
        self.cache[key] = (value, datetime.now())

    def invalidate(self, key: str):
        if key in self.cache:
            del self.cache[key]

class WorldMemory:
    """
    Revolutionary graph-based self-optimizing memory system.

    Features:
    - Incremental FAISS indexing
    - Batch embedding generation
    - Write-behind persistence
    - Time-based partitioning
    - Deterministic scoring
    - Automated memory lifecycle management
    - Entity extraction & resolution
    - Contradiction detection
    - Pain signal tracking
    - Multi-pass retrieval
    - Delta-aware context
    - Salience decay & access boost
    - Attention-optimized ordering (U-curve)
    - Speculative cache
    """

    def __init__(
        self,
        storage_path: Path,
        llm: LLMClient,
        config: MemoryConfig = None,
    ):
        self.config = config or DEFAULT_CONFIG
        self.storage_path = storage_path
        self.llm = llm

        # Disable FAISS due to dimension mismatch issues - use linear search only
        self._faiss_disabled = True

        # Initialize components
        self.partition_mgr = MemoryPartitionManager(
            storage_path,
            self.config.retention_months,
            self.config.active_partitions_count
        )

        self.embedding_queue = EmbeddingQueue(
            llm,
            self.config.batch_embed_size,
            self.config.flush_interval_seconds,
            self.config.embedding_dim
        )

        self.write_buffer = WriteBehindBuffer(
            self.config.flush_interval_seconds,
            self.config.write_buffer_max_size
        )

        self.scoring = MemoryScoringEngine(
            self.config.scoring_weights,
            self.config.half_life_days
        )

        self.cluster = ClusterEngine(
            self.config.cluster_similarity_threshold,
            self.config.cluster_min_size,
            self.config.merge_cluster_min_size,
            self.config.enable_llm_merge
        )

        self.optimizer = MemoryOptimizer(
            self,
            self.config.optimizer_interval_hours,
            self.scoring,
            self.cluster,
            self.config.min_keep_score,
            self.config.min_keep_days
        )

        # Active memory storage
        self.active_entries: Dict[str, WorldMemoryEntry] = {}

        # FAISS index
        self.faiss_index: Optional[IncrementalFAISSIndex] = None
        self._id_to_faiss_id: Dict[str, int] = {}
        self._faiss_id_to_id: Dict[int, str] = {}

        # Session tracking
        self.session_delta = SessionDeltaTracker()
        self.speculative_cache = SpeculativeCache()

        # FAISS lock for thread safety
        self._faiss_lock = asyncio.Lock()

        # Active entries lock for thread safety
        self._active_lock = asyncio.Lock()

        # Inverted indexes for fast filtering
        self._source_type_to_ids: Dict[str, Set[int]] = defaultdict(set)
        self._source_id_to_ids: Dict[str, Set[int]] = defaultdict(set)
        self._month_to_ids: Dict[str, Set[int]] = defaultdict(set)

        # FAISS ID counter (instance-level)
        self._next_faiss_id = 0

        # Track new entries for rebuild threshold
        self._new_entries_since_consolidation = 0

        # Ensure directories exist
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Lazy loading - entries loaded on first access
        self._entries_loaded = False

        # Lock for _ensure_loaded to prevent race condition
        self._load_lock = asyncio.Lock()

        # Broadcast callback for WebSocket memory events
        self._broadcast_callback = None

        logger.info("WorldMemory initialized (lazy loading enabled)")

    def set_broadcast_callback(self, callback):
        """Set a callback function to be called when new memories are added."""
        self._broadcast_callback = callback

    async def _lock_with_timeout(self, lock: asyncio.Lock, timeout: float = 5.0):
        """Acquire a lock with timeout to prevent deadlocks."""
        try:
            return await asyncio.wait_for(lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Lock acquisition timed out after {timeout}s")
            return False

    async def _ensure_loaded(self):
        """Ensure entries are loaded (async version) with race condition fix."""
        if self._entries_loaded:
            return
        async with self._load_lock:
            # Double-check after acquiring lock
            if self._entries_loaded:
                return
            await self._load_active_entries_async()
            self._entries_loaded = True

    async def _load_active_entries_async(self):
        """Load recent partitions into active memory (async version)."""
        if self._entries_loaded:
            return

        try:
            entries_dict = await self.partition_mgr.get_active_entries()
            for e_dict in entries_dict:
                entry = WorldMemoryEntry.from_dict(e_dict)
                self.active_entries[entry.id] = entry
                if entry.embedding is not None:
                    fid = self._next_faiss_id
                    self._next_faiss_id = fid + 1
                    self._id_to_faiss_id[entry.id] = fid
                    self._faiss_id_to_id[fid] = entry.id

            # Initialize FAISS index after loading
            if HAS_FAISS and self.active_entries:
                self._init_faiss_index()

            self._entries_loaded = True
            logger.info(f"Loaded {len(self.active_entries)} active entries from partitions")
        except Exception as e:
            logger.warning(f"Failed to load active entries: {e}")

    def _init_faiss_index(self):
        """Initialize FAISS index with existing entries."""
        self.faiss_index = IncrementalFAISSIndex(self.config.embedding_dim)
        # Reset next FAISS ID to avoid collisions
        self._next_faiss_id = max(self._id_to_faiss_id.values(), default=0) + 1

        vectors = []
        ids = []
        for eid, entry in self.active_entries.items():
            if entry.embedding is not None:
                fid = self._id_to_faiss_id.get(eid)
                if fid is not None:
                    vectors.append(np.array(entry.embedding))
                    ids.append(fid)

        if vectors:
            self.faiss_index.add(vectors, ids)


    async def start(self, migrate: bool = True):
        """Start all background services.

        Args:
            migrate: If True, attempt to migrate old memory data
        """
        # Load entries if not already loaded
        if not self._entries_loaded:
            await self._load_active_entries_async()

        # Try to migrate old data if no new data exists
        if migrate and len(self.active_entries) == 0:
            await self._migrate_old_memory()

        await self.embedding_queue.start()
        await self.write_buffer.start(self._flush_callback)
        await self.optimizer.start()
        logger.info("WorldMemory started")

    async def _migrate_old_memory(self):
        """Migrate memories from the old WorldMemory format."""
        old_memories_path = self.storage_path.parent / "world_memory" / "memories.json"
        if not old_memories_path.exists():
            # Try alternative location
            old_memories_path = self.storage_path.parent.parent / "world_memory" / "memories.json"

        if not old_memories_path.exists():
            logger.info("No old memory data found to migrate")
            return

        try:
            import json
            with open(old_memories_path, 'r') as f:
                data = json.load(f)

            entries = data.get('entries', [])
            if not entries:
                entries = data.get('memories', [])

            if not entries:
                logger.info("Old memory file is empty")
                return

            logger.info(f"Migrating {len(entries)} memories from old format...")


            for entry_data in entries:
                try:
                    # Convert old format to new
                    new_entry = WorldMemoryEntry(
                        id=entry_data.get('id', str(uuid4())),
                        content=entry_data.get('content', ''),
                        timestamp=datetime.fromisoformat(entry_data.get('timestamp', datetime.now().isoformat())),
                        source_type=entry_data.get('source_type', 'migrated'),
                        source_id=entry_data.get('source_id', 'migration'),
                        importance=entry_data.get('importance', 0.5),
                        tags=entry_data.get('tags', []),
                        node_uid=entry_data.get('node_uid'),
                        version=entry_data.get('version', 1),
                        parent_id=entry_data.get('parent_id'),
                        embedding=entry_data.get('embedding'),
                    )

                    # Handle old metadata format
                    old_metadata = entry_data.get('metadata', {})
                    if old_metadata:
                        new_entry.metadata = MemoryMetadata(
                            access_count=old_metadata.get('access_count', 0),
                            emotional_valence=old_metadata.get('emotional_valence', 0.0),
                            story_relevance=old_metadata.get('story_relevance', 0.5),
                            immutable=old_metadata.get('immutable', False),
                        )

                    # Add to new system
                    await self.partition_mgr.save_entry(new_entry.to_dict())
                    self.active_entries[new_entry.id] = new_entry

                    # Add to index if has embedding
                    if new_entry.embedding:
                        await self._add_to_index(new_entry)

                except Exception as e:
                    logger.warning(f"Failed to migrate entry: {e}")
                    continue

            logger.info(f"Migration complete: {len(self.active_entries)} memories migrated")

        except Exception as e:
            logger.warning(f"Migration failed: {e}")

    async def stop(self):
        """Stop all background services."""
        await self.optimizer.stop()
        await self.write_buffer.stop()
        await self.embedding_queue.stop()
        logger.info("WorldMemory stopped")

    # ==================== Public API ====================

    async def add_memory(self, entry: WorldMemoryEntry) -> str:
        """Add a memory entry to the system."""
        # Generate embedding FIRST (before saving)
        if entry.embedding is None:
            entry.embedding = await self.embedding_queue.embed(entry.content)

        # Mark for clustering
        entry.needs_clustering = True

        # Add to FAISS index
        await self._add_to_index(entry)

        # Store in partition (with embedding now included)
        await self.partition_mgr.save_entry(entry.to_dict())
        # Use timeout to prevent potential deadlock
        acquired = await self._lock_with_timeout(self._active_lock, timeout=5.0)
        try:
            self.active_entries[entry.id] = entry
        finally:
            if acquired:
                self._active_lock.release()
            logger.warning("Failed to acquire _active_lock in add_memory, entry may not be in active_entries")

        # Write buffer for metadata updates
        await self.write_buffer.append(entry.to_dict())

        # Broadcast to WebSocket clients if callback is set
        if self._broadcast_callback:
            try:
                await self._broadcast_callback(entry)
            except Exception as e:
                logger.warning(f"Broadcast callback failed: {e}")

        return entry.id

    # ==================== Legacy API Compatibility ====================

    async def add_event(
        self,
        event_description: str,
        group: str = "narrative",
        importance: float = 0.4,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Legacy API: Add a timeline event (for compatibility with old code)."""
        entry = WorldMemoryEntry(
            id=f"event_{datetime.now().timestamp()}",
            content=event_description,
            timestamp=datetime.now(),
            source_type="event",
            source_id=group,
            importance=importance,
            metadata=MemoryMetadata(
                story_relevance=0.6,
                importance=importance,
            ) if metadata is None else MemoryMetadata(
                access_count=metadata.get("access_count", 0),
                emotional_valence=metadata.get("emotional_valence", 0.0),
                story_relevance=metadata.get("story_relevance", 0.6),
                immutable=metadata.get("immutable", False),
                importance=importance,
            ),
        )
        return await self.add_memory(entry)

    async def add_npc_memory(
        self,
        npc_name: str,
        content: str,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Legacy API: Add NPC memory."""
        entry = WorldMemoryEntry(
            id=f"npc_{datetime.now().timestamp()}",
            content=content,
            timestamp=datetime.now(),
            source_type="npc",
            source_id=npc_name,
            importance=importance,
            tags=tags or [],
            metadata=MemoryMetadata(
                access_count=metadata.get("access_count", 0) if metadata else 0,
                emotional_valence=metadata.get("emotion", 0.0) if metadata else 0.0,
                story_relevance=0.5,
                importance=importance,
            ),
        )
        return await self.add_memory(entry)

    async def add_entity_change(
        self,
        entity_uid: str,
        change: str,
        entity_name: Optional[str] = None,
        importance: float = 0.3,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Legacy API: Add entity change memory."""
        entry = WorldMemoryEntry(
            id=f"entity_{datetime.now().timestamp()}",
            content=change,
            timestamp=datetime.now(),
            source_type="entity_change",
            source_id=entity_uid,
            importance=importance,
            entity_uid=entity_uid,
            tags=[entity_name] if entity_name else [],
            metadata=MemoryMetadata(
                story_relevance=metadata.get("story_relevance", 0.6) if metadata else 0.6,
                importance=importance,
            ) if metadata is None else MemoryMetadata(
                access_count=metadata.get("access_count", 0),
                emotional_valence=metadata.get("emotional_valence", 0.0),
                story_relevance=metadata.get("story_relevance", 0.6),
                immutable=metadata.get("immutable", False),
                importance=importance,
            ),
        )
        return await self.add_memory(entry)

    async def add_location_visit(
        self,
        location_uid: str,
        location_name: str,
        visitor_name: str,
        importance: float = 0.2,
    ) -> str:
        """Legacy API: Record location visit."""
        return await self.add_entity_change(
            entity_uid=location_uid,
            change=f"{visitor_name} visited {location_name}",
            entity_name=location_name,
            importance=importance,
            metadata={"visitor": visitor_name, "visit_type": "arrival"},
        )

    async def add_item_interaction(
        self,
        item_uid: str,
        item_name: str,
        character_name: str,
        action: str,
        importance: float = 0.3,
    ) -> str:
        """Legacy API: Record item interaction."""
        return await self.add_entity_change(
            entity_uid=item_uid,
            change=f"{character_name} {action} {item_name}",
            entity_name=item_name,
            importance=importance,
            metadata={"character": character_name, "action": action},
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        entity_filter: Optional[Set[str]] = None,
        source_type_filter: Optional[Set[str]] = None,
        time_window: Optional[timedelta] = None,
        min_importance: float = 0.0,
        session_id: Optional[str] = None,
        last_seen: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Multi-pass semantic retrieval with optional filters.

        Pass 1: Instant recall (tag/ID exact match)
        Pass 2: Active search (vector similarity)
        Pass 3: Deep dig (graph expansion)
        """
        results = []
        seen_ids = set()

        # Pass 1: Tag/ID exact match
        tag_results = await self._tag_search(query, top_k)
        for score, entry in tag_results:
            if entry.id not in seen_ids:
                results.append(self._entry_to_result(entry, score))
                seen_ids.add(entry.id)

        # Pass 2: Vector similarity search
        query_emb = await self.embedding_queue.embed(query)
        # Ensure it's a 2D array for FAISS (n_samples, n_features)
        query_np = np.array(query_emb).astype('float32')
        if query_np.ndim == 1:
            query_np = query_np.reshape(1, -1)

        # Determine valid FAISS IDs from filters
        valid_faiss_ids = self._build_valid_mask(
            entity_filter, source_type_filter, time_window, min_importance
        )

        # Skip FAISS if dimension doesn't match - use linear search instead
        query_dim = query_np.shape[1] if query_np.ndim > 1 else len(query_emb)
        expected_dim = getattr(self.faiss_index, 'dimension', 0)

        if self.faiss_index and self.faiss_index.total_entries() > 0 and query_dim == expected_dim:
            try:
                vector_results = await self._vector_retrieve(
                    query_np, top_k * 2, valid_faiss_ids
                )
                for score, entry in vector_results:
                    if entry.id not in seen_ids:
                        results.append(self._entry_to_result(entry, score))
                        seen_ids.add(entry.id)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"FAISS retrieval failed: {e}. Using linear search.")
                linear_results = await self._linear_retrieve(
                    query_emb, top_k * 2, valid_faiss_ids
                )
        else:
            # Fallback to linear search (dimension mismatch or no FAISS)
            if query_dim != expected_dim and self.faiss_index:
                import logging
                logging.getLogger(__name__).warning(
                    f"Skipping FAISS: query dimension {query_dim} != index dimension {expected_dim}"
                )
            linear_results = await self._linear_retrieve(
                query_emb, top_k * 2, valid_faiss_ids
            )
            for score, entry in linear_results:
                if entry.id not in seen_ids:
                    results.append(self._entry_to_result(entry, score))
                    seen_ids.add(entry.id)

        # Pass 3: Graph expansion for entries with linked entities
        if results:
            expanded = await self._graph_expansion(results[:5])
            for entry, score in expanded:
                if entry.id not in seen_ids:
                    results.append(self._entry_to_result(entry, score))
                    seen_ids.add(entry.id)

        # Apply delta filtering if session_id provided
        if session_id and last_seen:
            results = self._apply_delta_filter(results, last_seen)

        # Sort by relevance and apply U-curve ordering
        results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        results = self._order_by_attention_curve(results)

        # Update access counts and session tracking
        if session_id:
            await self._update_session_tracking(session_id, results, top_k)

        return results[:top_k]

    async def update_access(self, entry_id: str):
        """Increment access count and update salience."""
        entry = self.active_entries.get(entry_id)
        if not entry:
            return

        entry.metadata.access_count += 1
        entry.metadata.last_accessed = datetime.now()

        # Recalculate decayed salience
        days = (datetime.now() - entry.timestamp).days
        decay = 2 ** (-days / self.config.half_life_days)
        access_boost = math.log1p(entry.metadata.access_count) * 0.1
        entry.decayed_salience = min(
            1.0,
            entry.salience * decay + access_boost
        )

        await self.write_buffer.append(entry.to_dict())

    async def get_stats(self) -> Dict:
        """Get comprehensive memory statistics."""
        faiss_entries = 0
        faiss_fragmentation = 0.0
        if self.faiss_index:
            faiss_entries = self.faiss_index.total_entries()
            faiss_fragmentation = self.faiss_index.fragmentation_ratio()

        return {
            "total_active_entries": len(self.active_entries),
            "faiss_entries": faiss_entries,
            "faiss_fragmentation": faiss_fragmentation,
            "embedding_queue_size": self.embedding_queue.get_queue_size(),
            "write_buffer_size": self.write_buffer.get_buffer_size(),
            "optimizer_stats": self.optimizer.get_stats(),
        }

    async def get_last_seen(self, session_id: str) -> Optional[datetime]:
        """Get the last seen timestamp for a session."""
        return self.session_delta.get_last_seen(session_id)

    def get_recent_global_facts(self, limit: int = 5) -> List[Dict]:
        """Get recent global facts for world knowledge retrieval.

        Returns a list of recent memory entries as facts.
        """
        facts = []
        # Get most recent entries from active_entries
        sorted_entries = sorted(
            self.active_entries.values(),
            key=lambda e: e.timestamp if hasattr(e, 'timestamp') else datetime.min,
            reverse=True
        )
        for entry in sorted_entries[:limit]:
            facts.append({
                "fact": entry.content[:200] if entry.content else "",
                "importance": getattr(entry, 'importance', 0.5),
                "source_type": getattr(entry, 'source_type', 'unknown'),
                "timestamp": entry.timestamp.isoformat() if hasattr(entry, 'timestamp') else None
            })
        return facts

    # ==================== Internal Methods ====================

    async def _add_to_index(self, entry: WorldMemoryEntry):
        """Add entry to FAISS index with thread safety."""
        if entry.embedding is None:
            return

        async with self._faiss_lock:
            if self.faiss_index is None:
                if HAS_FAISS:
                    self.faiss_index = IncrementalFAISSIndex(self.config.embedding_dim)
                else:
                    return

            fid = self._next_faiss_id
            self._next_faiss_id += 1
            self._id_to_faiss_id[entry.id] = fid
            self._faiss_id_to_id[fid] = entry.id

            # Update inverted indexes
            self._source_type_to_ids[entry.source_type].add(fid)
            self._source_id_to_ids[entry.source_id].add(fid)
            month = entry.timestamp.strftime("%Y-%m")
            self._month_to_ids[month].add(fid)

            self.faiss_index.add([np.array(entry.embedding)], [fid])

            # Track new entries and check if rebuild is needed
            self._new_entries_since_consolidation += 1
            if self._new_entries_since_consolidation >= FAISS_REBUILD_ENTRY_THRESHOLD:
                # Check fragmentation before rebuilding
                if self.faiss_index.fragmentation_ratio() > FAISS_REBUILD_FRAGMENTATION_THRESHOLD:
                    asyncio.create_task(self._async_rebuild_index())
                self._new_entries_since_consolidation = 0

    async def _delete_entry(self, entry_id: str):
        """Internal: remove entry from active memory and index."""
        entry = self.active_entries.pop(entry_id, None)
        if entry is None:
            return

        fid = self._id_to_faiss_id.pop(entry_id, None)
        if fid is not None:
            # Clean inverted indexes
            self._source_type_to_ids[entry.source_type].discard(fid)
            self._source_id_to_ids[entry.source_id].discard(fid)
            month = entry.timestamp.strftime("%Y-%m")
            self._month_to_ids[month].discard(fid)

            if self.faiss_index:
                self.faiss_index.delete([fid])
            self._faiss_id_to_id.pop(fid, None)

    async def _tag_search(
        self,
        query: str,
        top_k: int
    ) -> List[Tuple[float, WorldMemoryEntry]]:
        """Pass 1: Fast tag/ID exact match."""
        results = []

        # Check for tag search (#tag)
        if query.startswith("#"):
            tag = query[1:].lower()
            for entry in self.active_entries.values():
                if tag in [t.lower() for t in entry.tags]:
                    results.append((1.0, entry))
                    if len(results) >= top_k:
                        break
            return results

        # Check for ID exact match
        if query in self.active_entries:
            entry = self.active_entries[query]
            results.append((1.0, entry))

        return results

    async def _vector_retrieve(
        self,
        query_np: np.ndarray,
        k: int,
        valid_mask: Optional[Set[int]]
    ) -> List[Tuple[float, WorldMemoryEntry]]:
        """Pass 2: Vector similarity search."""
        if not self.faiss_index:
            return []

        # Try FAISS search with error handling for dimension mismatches
        try:
            # Normalize query vector for cosine similarity
            try:
                faiss.normalize_L2(query_np)
            except AssertionError as e:
                import logging
                logging.getLogger(__name__).warning(f"FAISS normalize_L2 dimension error: {e}. Using linear search.")
                return await self._linear_retrieve(query_np.flatten(), k, valid_mask)
            scores, ids = self.faiss_index.search(query_np, k, valid_mask)
        except (AssertionError, Exception) as e:
            # FAISS dimension mismatch - fall back to linear search
            import logging
            logging.getLogger(__name__).warning(f"FAISS search failed: {e}. Using linear search.")
            return await self._linear_retrieve(query_np.flatten(), k, valid_mask)
        results = []

        for score, fid in zip(scores, ids):
            if fid == -1:
                continue
            eid = self._faiss_id_to_id.get(int(fid))
            if eid and eid in self.active_entries:
                entry = self.active_entries[eid]
                # Apply recency and importance weighting
                days = (datetime.now() - entry.timestamp).days
                recency = math.exp(-days / self.config.half_life_days)
                final_score = float(score) * (
                    0.6 + 0.2 * entry.importance + 0.2 * recency
                )
                results.append((final_score, entry))

        return results

    def _compute_similarities(
        self,
        embeddings: np.ndarray,
        query_np: np.ndarray,
        id_list: List[str]
    ) -> List[Tuple[float, WorldMemoryEntry]]:
        """Compute cosine similarities and apply recency/importance weighting."""
        norm_q = np.linalg.norm(query_np)
        if norm_q == 0:
            return []

        norms = np.linalg.norm(embeddings, axis=1)
        sims = np.dot(embeddings, query_np) / (norms * norm_q + 1e-8)

        scores = []
        for i, eid in enumerate(id_list):
            entry = self.active_entries[eid]
            days = (datetime.now() - entry.timestamp).days
            recency = math.exp(-days / self.config.half_life_days)
            final_score = sims[i] * (0.6 + 0.2 * entry.importance + 0.2 * recency)
            scores.append((final_score, entry))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores

    async def _linear_retrieve(
        self,
        query_emb: List[float],
        top_k: int,
        valid_mask: Optional[Set[int]]
    ) -> List[Tuple[float, WorldMemoryEntry]]:
        """Fallback linear retrieval when FAISS unavailable. (NumPy vectorised)"""
        # Build list of candidate embeddings and ids
        emb_list = []
        id_list = []
        for eid, entry in self.active_entries.items():
            if entry.embedding is None:
                continue
            if valid_mask:
                fid = self._id_to_faiss_id.get(eid)
                if fid not in valid_mask:
                    continue
            emb_list.append(entry.embedding)
            id_list.append(eid)

        if not emb_list:
            return []

        # Filter embeddings to ensure all have the same dimension as query
        expected_dim = len(query_emb)
        valid_emb_list = []
        valid_id_list = []
        for emb, eid in zip(emb_list, id_list):
            if emb is not None and len(emb) == expected_dim:
                valid_emb_list.append(emb)
                valid_id_list.append(eid)

        if not valid_emb_list:
            return []

        embeddings = np.array(valid_emb_list)
        query_np = np.array(query_emb)
        id_list = valid_id_list

        # Offload CPU-bound NumPy operations to thread
        scores = await asyncio.to_thread(
            self._compute_similarities, embeddings, query_np, id_list
        )

        return scores[:top_k]

    async def _graph_expansion(
        self,
        results: List[Dict]
    ) -> List[Tuple[float, WorldMemoryEntry]]:
        """Pass 3: Expand by following entity links."""
        expanded = []
        seen_entity_uids = set()

        for result in results:
            entry = self.active_entries.get(result.get("id"))
            if not entry:
                continue

            # Get related entity UIDs
            entity_uids = []
            if entry.entity_uid:
                entity_uids.append(entry.entity_uid)
            entity_uids.extend(entry.linked_entity_uids)

            for entity_uid in entity_uids:
                if entity_uid in seen_entity_uids:
                    continue
                seen_entity_uids.add(entity_uid)

                # Find all memories linked to this entity
                for other_entry in self.active_entries.values():
                    if other_entry.id == entry.id:
                        continue
                    if other_entry.entity_uid == entity_uid:
                        # Score based on relationship strength
                        score = result.get("relevance", 0) * 0.8
                        expanded.append((score, other_entry))

        return expanded

    def _build_valid_mask(
        self,
        entity_filter: Optional[Set[str]],
        source_type_filter: Optional[Set[str]],
        time_window: Optional[timedelta],
        min_importance: float
    ) -> Optional[Set[int]]:
        """Build a mask of valid FAISS IDs based on filters using inverted indexes (O(1) per filter)."""
        if not any([entity_filter, source_type_filter, time_window, min_importance > 0]):
            return None

        candidate_sets = []

        if source_type_filter:
            ids = set()
            for st in source_type_filter:
                ids.update(self._source_type_to_ids.get(st, set()))
            candidate_sets.append(ids)

        if entity_filter:
            ids = set()
            for eid in entity_filter:
                ids.update(self._source_id_to_ids.get(eid, set()))
            candidate_sets.append(ids)

        if time_window:
            cutoff = datetime.now() - time_window
            months = set()
            current = datetime.now()
            while current >= cutoff:
                months.add(current.strftime("%Y-%m"))
                current -= timedelta(days=30)
            ids = set()
            for m in months:
                ids.update(self._month_to_ids.get(m, set()))
            candidate_sets.append(ids)

        if candidate_sets:
            mask = set.intersection(*candidate_sets) if len(candidate_sets) > 1 else candidate_sets[0]
        else:
            mask = set(self._id_to_faiss_id.values())

        # Apply importance filter (post-filter, but mask is smaller now)
        if min_importance > 0:
            final_mask = set()
            for fid in mask:
                eid = self._faiss_id_to_id.get(fid)
                if eid and self.active_entries[eid].importance >= min_importance:
                    final_mask.add(fid)
            return final_mask

        return mask if mask else None

    def _entry_to_result(
        self,
        entry: WorldMemoryEntry,
        score: float
    ) -> Dict[str, Any]:
        """Convert entry to retrieval result dict."""
        return {
            "id": entry.id,
            "content": entry.content,
            "source": entry.source_id,
            "source_type": entry.source_type,
            "timestamp": entry.timestamp.isoformat(),
            "relevance": score,
            "importance": entry.importance,
            "tags": entry.tags,
            "memory_type": entry.memory_type,
        }

    def _apply_delta_filter(
        self,
        results: List[Dict],
        last_seen: datetime
    ) -> List[Dict]:
        """Filter results to only show changes since last_seen."""
        filtered = []
        for r in results:
            ts = datetime.fromisoformat(r["timestamp"])
            if ts > last_seen:
                filtered.append(r)
        return filtered

    async def _update_session_tracking(
        self,
        session_id: str,
        results: List[Dict],
        top_k: int
    ):
        """Update session tracking for delta-aware retrieval."""
        retrieved_ids = {r["id"] for r in results[:top_k]}
        self.session_delta.update(session_id, retrieved_ids, datetime.now())

        # Update access counts
        for r in results[:top_k]:
            await self.update_access(r["id"])

    def _order_by_attention_curve(self, results: List[dict]) -> List[dict]:
        """Arrange results in U-curve order for attention optimization."""
        if len(results) <= 2:
            return results

        # Sort by relevance (high to low)
        sorted_res = sorted(
            results,
            key=lambda x: x.get("relevance", 0),
            reverse=True
        )

        # Interleave: highest at start, second highest at end, etc.
        ordered = []
        left, right = 0, len(sorted_res) - 1
        take_left = True

        while left <= right:
            if take_left:
                ordered.append(sorted_res[left])
                left += 1
            else:
                ordered.append(sorted_res[right])
                right -= 1
            take_left = not take_left

        return ordered

    async def _flush_callback(self, batch: List[dict]):
        """Callback for write-behind buffer to persist entries."""
        for entry_dict in batch:
            await self.partition_mgr.save_entry(entry_dict)
