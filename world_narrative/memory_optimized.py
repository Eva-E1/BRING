"""
Optimized memory system for NPCs – vector embeddings, graph indexing, and background maintenance.
Replaces the original NPCManager with a scalable, NPC‑centric long‑term memory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

import numpy as np

# For vector similarity
try:
    from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    sklearn_cosine = None

# Helper to handle both 1D and 2D arrays for sklearn
def cosine_similarity(a, b):
    """Compute cosine similarity, handling both 1D and 2D arrays."""
    if HAS_SKLEARN and sklearn_cosine:
        # Ensure 2D: (1, n_features) for single vectors
        a_arr = np.array(a)
        b_arr = np.array(b)
        if a_arr.ndim == 1:
            a_arr = a_arr.reshape(1, -1)
        if b_arr.ndim == 1:
            b_arr = b_arr.reshape(1, -1)
        return sklearn_cosine(a_arr, b_arr)[0][0]
    # Fallback: simple dot product
    a_flat = np.array(a).flatten()
    b_flat = np.array(b).flatten()
    dot = sum(x*y for x, y in zip(a_flat, b_flat))
    norm_a = math.sqrt(sum(x*x for x in a_flat))
    norm_b = math.sqrt(sum(y*y for y in b_flat))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

from world_builder.graph_manager import GraphManager
from world_builder.llm import LLMClient
from world_narrative.chronicler import Chronicler
from world_core.llm_queue import GlobalLLMQueue
from world_director.models import TaskPriority

logger = logging.getLogger(__name__)


# ==================================================================
# Memory Data Structures
# ==================================================================

@dataclass
class EpisodicMemory:
    """A single memory entry for an NPC."""
    id: str
    timestamp: datetime
    description: str
    importance: float          # 0.0 - 1.0 (how significant)
    emotion: str               # "joy", "fear", "anger", "surprise", "sadness", "neutral"
    involved_entities: List[str] = field(default_factory=list)
    location: str = ""
    embedding: Optional[List[float]] = None   # lazy loaded
    consolidated: bool = False  # whether it has been merged into semantic memory


@dataclass
class NPCProfile:
    """Full NPC profile with layered memory."""
    name: str
    uid: str                     # f"{entity_type}:{name}"
    short_term: List[EpisodicMemory] = field(default_factory=list)   # last 10-20 events
    long_term_episodic: List[EpisodicMemory] = field(default_factory=list)  # consolidated
    # Runtime state (kept for fast access)
    location: str = "unknown"
    health: int = 100
    mood: str = "neutral"
    goals: List[str] = field(default_factory=list)
    inventory: Set[str] = field(default_factory=set)
    tags: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # Skills for probability system (0.0 to 1.0)
    skills: Dict[str, float] = field(default_factory=lambda: {
        "strength": 0.5, "dexterity": 0.5, "charisma": 0.5,
        "intelligence": 0.5, "wisdom": 0.5, "luck": 0.5,
        "combat_skill": 0.5, "persuasion": 0.5, "stealth": 0.5,
    })


# ==================================================================
# Memory Optimizer – Background consolidation and pruning
# ==================================================================

class MemoryOptimizer:
    """Runs in background to prune and promote memories."""

    def __init__(
        self,
        store: "OptimizedMemoryStore",
        llm_queue: GlobalLLMQueue,
        run_interval_seconds: int = 300,
        short_term_limit: int = 20,
        max_long_term: int = 500,
        importance_threshold: float = 0.4,
        max_embedding_cache_size: int = 1000,
    ):
        self.store = store
        self.llm_queue = llm_queue
        self.run_interval = run_interval_seconds
        self.short_term_limit = short_term_limit
        self.max_long_term = max_long_term
        self.importance_threshold = importance_threshold
        self.max_embedding_cache_size = max_embedding_cache_size
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._background_loop())
        logger.info("MemoryOptimizer started")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MemoryOptimizer stopped")

    async def _background_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.run_interval)
                await self._run_optimization()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"MemoryOptimizer error: {e}")

    async def _run_optimization(self):
        """Consolidate, prune, and deduplicate memories for all NPCs."""
        for npc_name, profile in self.store._npcs.items():
            # 1. Move important short‑term memories to long‑term
            for mem in profile.short_term[:]:
                if mem.importance >= self.importance_threshold:
                    profile.short_term.remove(mem)
                    # Check if already exists in long‑term
                    exists = False
                    for existing in profile.long_term_episodic:
                        if existing.description == mem.description:
                            exists = True
                            break
                    if not exists:
                        profile.long_term_episodic.append(mem)
                        # Update embedding for long‑term if needed
                        if mem.embedding is not None:
                            await self.store._ensure_embedding(mem, npc_name)

            # 2. Prune short‑term to limit
            if len(profile.short_term) > self.short_term_limit:
                # Sort by importance, keep most important
                profile.short_term.sort(key=lambda m: m.importance, reverse=True)
                profile.short_term = profile.short_term[:self.short_term_limit]

            # 3. Prune long‑term episodic
            if len(profile.long_term_episodic) > self.max_long_term:
                # Sort by importance and recency
                profile.long_term_episodic.sort(
                    key=lambda m: (m.importance, m.timestamp.timestamp()),
                    reverse=True
                )
                profile.long_term_episodic = profile.long_term_episodic[:self.max_long_term]

        self.store._save()


# ==================================================================
# Optimized Memory Store
# ==================================================================

class OptimizedMemoryStore:
    """
    High‑performance memory store with:
    - NPC‑centric long‑term episodic + semantic memory
    - Embedding caching (per memory entry)
    - Automatic consolidation via background optimizer
    - Fast similarity search for narrative retrieval
    """

    def __init__(self, state_path: Path, gm: GraphManager, llm_queue: GlobalLLMQueue, llm: LLMClient = None,
                 max_embedding_cache_size: int = 1000, world_memory=None):
        self.state_path = state_path
        self.gm = gm
        self.llm = llm  # Keep raw LLM for embeddings (not handled by queue)
        self.llm_queue = llm_queue  # Queue for text generation
        self.max_embedding_cache_size = max_embedding_cache_size
        self._npcs: Dict[str, NPCProfile] = {}
        self._embedding_cache_dir = state_path / "embeddings"
        self._embedding_cache_dir.mkdir(parents=True, exist_ok=True)
        self._load()
        self.optimizer = MemoryOptimizer(self, llm_queue, max_embedding_cache_size=max_embedding_cache_size)
        self._embedding_lock = asyncio.Lock()
        self._npcs_lock = asyncio.Lock()  # Lock for thread-safe NPC dict access
        self.world_memory = world_memory  # Optional unified world memory layer

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        """Load NPC profiles from disk."""
        profiles_path = self.state_path / "npc_profiles.json"
        if profiles_path.exists():
            try:
                data = json.loads(profiles_path.read_text(encoding="utf-8"))
                for name, d in data.items():
                    # Reconstruct short‑term memories
                    short_term = []
                    for m in d.get("short_term", []):
                        short_term.append(EpisodicMemory(
                            id=m["id"],
                            timestamp=datetime.fromisoformat(m["timestamp"]),
                            description=m["description"],
                            importance=m["importance"],
                            emotion=m["emotion"],
                            involved_entities=m.get("involved_entities", []),
                            location=m.get("location", ""),
                            consolidated=m.get("consolidated", False),
                        ))
                    # Reconstruct long‑term episodic
                    long_term = []
                    for m in d.get("long_term_episodic", []):
                        long_term.append(EpisodicMemory(
                            id=m["id"],
                            timestamp=datetime.fromisoformat(m["timestamp"]),
                            description=m["description"],
                            importance=m["importance"],
                            emotion=m["emotion"],
                            involved_entities=m.get("involved_entities", []),
                            location=m.get("location", ""),
                            consolidated=m.get("consolidated", False),
                        ))
                    # Build profile
                    profile = NPCProfile(
                        name=name,
                        uid=d["uid"],
                        short_term=short_term,
                        long_term_episodic=long_term,
                        location=d.get("location", "unknown"),
                        health=d.get("health", 100),
                        mood=d.get("mood", "neutral"),
                        goals=d.get("goals", []),
                        inventory=set(d.get("inventory", [])),
                        tags=d.get("tags", {}),
                        updated_at=d.get("updated_at", datetime.now().isoformat()),
                    )
                    self._npcs[name] = profile
            except Exception as e:
                logger.warning(f"Failed to load memory store: {e}")

    def _save(self):
        """Save all NPC profiles to disk (atomic)."""
        data = {}
        for name, p in self._npcs.items():
            data[name] = {
                "uid": p.uid,
                "short_term": [
                    {
                        "id": m.id,
                        "timestamp": m.timestamp.isoformat(),
                        "description": m.description,
                        "importance": m.importance,
                        "emotion": m.emotion,
                        "involved_entities": m.involved_entities,
                        "location": m.location,
                        "consolidated": m.consolidated,
                    }
                    for m in p.short_term
                ],
                "long_term_episodic": [
                    {
                        "id": m.id,
                        "timestamp": m.timestamp.isoformat(),
                        "description": m.description,
                        "importance": m.importance,
                        "emotion": m.emotion,
                        "involved_entities": m.involved_entities,
                        "location": m.location,
                        "consolidated": m.consolidated,
                    }
                    for m in p.long_term_episodic
                ],
                "location": p.location,
                "health": p.health,
                "mood": p.mood,
                "goals": p.goals,
                "inventory": list(p.inventory),
                "tags": p.tags,
                "updated_at": p.updated_at,
            }

        # Atomic write
        profiles_path = self.state_path / "npc_profiles.json"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=profiles_path.parent, delete=False) as tf:
            json.dump(data, tf, indent=2)
            os.replace(tf.name, profiles_path)

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    async def _embed_text(self, obj: Any, npc_name: str, memory_type: str) -> List[float]:
        """Generate embedding for a memory item and cache it."""
        async with self._embedding_lock:
            # Determine cache key
            if hasattr(obj, "id"):
                cache_key = f"{npc_name}_{memory_type}_{obj.id}"
            else:
                cache_key = f"{npc_name}_{memory_type}_{hash(str(obj))}"
            cache_path = self._embedding_cache_dir / f"{cache_key}.npy"

            if cache_path.exists():
                try:
                    return np.load(cache_path).tolist()
                except Exception:
                    pass

            # Generate text to embed
            if isinstance(obj, EpisodicMemory):
                text = f"{obj.description} [Importance: {obj.importance}, Emotion: {obj.emotion}]"
            else:
                text = str(obj)

            # Use LLM embedding API (reuse existing gateway)
            try:
                embedding = await self.llm.embedding(text)
                if isinstance(embedding, list):
                    np.save(cache_path, np.array(embedding))
                    # Clean up old cache files if exceeding max size
                    await self._cleanup_embedding_cache()
                    return embedding
            except Exception as e:
                logger.warning(f"Embedding failed for {npc_name}: {e}")
                return [0.0] * 384  # fallback zero vector (1D)

    async def _cleanup_embedding_cache(self):
        """Remove old cache files if exceeding max_embedding_cache_size."""
        if not hasattr(self, '_embedding_cache_dir') or self._embedding_cache_dir is None:
            return
        try:
            cache_files = list(self._embedding_cache_dir.glob("*.npy"))
            if len(cache_files) > self.max_embedding_cache_size:
                # Sort by modification time, delete oldest
                cache_files.sort(key=lambda f: f.stat().st_mtime)
                for f in cache_files[:len(cache_files) - self.max_embedding_cache_size]:
                    f.unlink()
        except Exception as e:
            logger.warning(f"Cache cleanup failed: {e}")

    async def _ensure_embedding(self, mem: EpisodicMemory, npc_name: str):
        if mem.embedding is None:
            mem.embedding = await self._embed_text(mem, npc_name, "episodic")

    # ------------------------------------------------------------------
    # NPC Management (core API)
    # ------------------------------------------------------------------

    async def register(self, name: str, uid: str, location: str = "unknown") -> NPCProfile:
        """Register a new NPC or return existing."""
        async with self._npcs_lock:
            if name not in self._npcs:
                # Initialize with default skills (will be overridden by L2 data if available)
                default_skills = {
                    "strength": 0.5, "dexterity": 0.5, "charisma": 0.5,
                    "intelligence": 0.5, "wisdom": 0.5, "luck": 0.5,
                    "combat_skill": 0.5, "persuasion": 0.5, "stealth": 0.5,
                }
                self._npcs[name] = NPCProfile(
                    name=name,
                    uid=uid,
                    location=location,
                    skills=default_skills,
                )
                self._save()
            return self._npcs[name]

    async def add_memory(
        self,
        name: str,
        description: str,
        emotion: str = "neutral",
        importance: float = 0.5,
        involved_entities: Optional[List[str]] = None,
        location: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Add a new episodic memory for an NPC.
        Returns memory ID.
        """
        profile = self._npcs.get(name)
        if not profile:
            raise ValueError(f"NPC '{name}' not found")

        mem_id = f"{name}_mem_{len(profile.short_term) + len(profile.long_term_episodic)}_{datetime.now().timestamp()}"
        memory = EpisodicMemory(
            id=mem_id,
            timestamp=datetime.now(),
            description=description,
            importance=importance,
            emotion=emotion,
            involved_entities=involved_entities or [],
            location=location or profile.location,
        )
        profile.short_term.append(memory)
        self._save()

        # Sync to unified world memory if available
        if self.world_memory is not None:
            await self.world_memory.add_npc_memory(
                npc_name=name,
                content=description,
                importance=importance,
                metadata={"emotion": emotion, "location": location or profile.location}
            )

        return mem_id

    async def get_memories(
        self,
        name: str,
        memory_type: str = "all",
        limit: int = 20,
        min_importance: float = 0.0,
        emotion_filter: Optional[str] = None,
    ) -> List[EpisodicMemory]:
        """
        Retrieve memories for an NPC.
        memory_type: "short", "long", "semantic", "all"
        """
        profile = self._npcs.get(name)
        if not profile:
            return []

        results = []
        if memory_type in ("short", "all"):
            results.extend(profile.short_term)
        if memory_type in ("long", "all"):
            results.extend(profile.long_term_episodic)

        # Filter
        if emotion_filter:
            results = [m for m in results if m.emotion == emotion_filter]
        if min_importance > 0:
            results = [m for m in results if m.importance >= min_importance]

        # Sort by timestamp descending, then importance
        results.sort(key=lambda m: (m.timestamp.timestamp(), m.importance), reverse=True)
        return results[:limit]



    async def get_relevant_memories(
        self,
        name: str,
        context: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories most relevant to a given context string.
        Used by Director / StoryEngine for character‑aware narration.
        """
        # Embed context
        context_emb = await self._embed_text(context, name, "context")

        profile = self._npcs.get(name)
        if not profile:
            return []

        # Collect all memories with embeddings
        candidates = []
        for mem in profile.short_term + profile.long_term_episodic:
            if mem.embedding is None:
                await self._ensure_embedding(mem, name)
            if mem.embedding:
                sim = cosine_similarity(context_emb, mem.embedding)
                candidates.append(("episodic", mem, sim))

        candidates.sort(key=lambda x: x[2], reverse=True)

        results = []
        for mem_type, obj, score in candidates[:top_k]:
            if mem_type == "episodic":
                results.append({
                    "type": "episodic",
                    "description": obj.description,
                    "timestamp": obj.timestamp.isoformat(),
                    "importance": obj.importance,
                    "emotion": obj.emotion,
                    "relevance": score,
                })
            else:
                results.append({
                    "type": "semantic",
                    "fact": obj.fact,
                    "confidence": obj.confidence,
                    "relevance": score,
                })
        return results

    # ------------------------------------------------------------------
    # Runtime state (compatible with old NPCManager)
    # ------------------------------------------------------------------

    async def move(self, name: str, location: str, story_time: datetime) -> None:
        async with self._npcs_lock:
            profile = self._npcs.get(name)
            if profile:
                profile.location = location
                profile.updated_at = story_time.isoformat()
                self._save()
                # Add memory of movement if significant
                if profile.location != location:
                    await self.add_memory(
                        name,
                        f"Moved to {location}",
                        emotion="neutral",
                        importance=0.3,
                        location=location,
                    )

    async def adjust_health(self, name: str, delta: int) -> int:
        async with self._npcs_lock:
            profile = self._npcs.get(name)
            if profile:
                profile.health = max(0, min(100, profile.health + delta))
                self._save()
                # Add memory if significant health change
                if abs(delta) >= 15:
                    emotion = "fear" if delta < 0 else "joy"
                    await self.add_memory(
                        name,
                        f"Health changed by {delta}",
                        emotion=emotion,
                        importance=0.4,
                    )
            return profile.health if profile else 100

    async def set_mood(self, name: str, mood: str) -> None:
        async with self._npcs_lock:
            profile = self._npcs.get(name)
            if profile:
                old_mood = profile.mood
                profile.mood = mood
                profile.updated_at = datetime.now().isoformat()
                self._save()
                if old_mood != mood:
                    await self.add_memory(
                        name,
                        f"Mood changed from {old_mood} to {mood}",
                        emotion=mood,
                        importance=0.2,
                    )

    async def add_goal(self, name: str, goal: str) -> None:
        profile = self._npcs.get(name)
        if profile and goal not in profile.goals:
            profile.goals.append(goal)
            self._save()
            await self.add_memory(
                name,
                f"Gained new goal: {goal}",
                emotion="determined",
                importance=0.5,
            )

    async def add_item(self, name: str, item_name: str) -> None:
        profile = self._npcs.get(name)
        if profile:
            profile.inventory.add(item_name)
            self._save()
            await self.add_memory(
                name,
                f"Acquired {item_name}",
                emotion="joy" if item_name else "neutral",
                importance=0.3,
            )

    async def remove_item(self, name: str, item_name: str) -> None:
        profile = self._npcs.get(name)
        if profile:
            profile.inventory.discard(item_name)
            self._save()
            await self.add_memory(
                name,
                f"Lost {item_name}",
                emotion="sadness",
                importance=0.3,
            )

    def get(self, name: str) -> Optional[NPCProfile]:
        return self._npcs.get(name)

    def list_all(self) -> Dict[str, NPCProfile]:
        return self._npcs.copy()

    async def start_optimizer(self):
        await self.optimizer.start()

    async def stop_optimizer(self):
        await self.optimizer.stop()
