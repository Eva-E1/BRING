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
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    # Fallback: implement simple dot product
    def simple_cosine(a, b):
        dot = sum(x*y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x*x for x in a))
        norm_b = math.sqrt(sum(y*y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    cosine_similarity = simple_cosine

from world_builder.graph_manager import GraphManager
from world_builder.llm import LLMClient
from world_narrative.chronicler import Chronicler

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
class SemanticMemory:
    """Long‑term semantic knowledge extracted from episodes."""
    id: str
    fact: str
    source_episodes: List[str]   # IDs of episodes that contributed
    confidence: float            # 0.0 - 1.0
    embedding: Optional[List[float]] = None


@dataclass
class NPCProfile:
    """Full NPC profile with layered memory."""
    name: str
    uid: str                     # f"{entity_type}:{name}"
    short_term: List[EpisodicMemory] = field(default_factory=list)   # last 10-20 events
    long_term_episodic: List[EpisodicMemory] = field(default_factory=list)  # consolidated
    semantic: List[SemanticMemory] = field(default_factory=list)
    # Runtime state (kept for fast access)
    location: str = "unknown"
    health: int = 100
    mood: str = "neutral"
    goals: List[str] = field(default_factory=list)
    inventory: Set[str] = field(default_factory=set)
    tags: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ==================================================================
# Memory Optimizer – Background consolidation and pruning
# ==================================================================

class MemoryOptimizer:
    """Runs in background to consolidate, prune, and re‑embed memories."""

    def __init__(
        self,
        store: "OptimizedMemoryStore",
        llm: LLMClient,
        run_interval_seconds: int = 300,
        short_term_limit: int = 20,
        max_long_term: int = 500,
        importance_threshold: float = 0.4,
        similarity_threshold: float = 0.85,
        max_embedding_cache_size: int = 1000,
    ):
        self.store = store
        self.llm = llm
        self.run_interval = run_interval_seconds
        self.short_term_limit = short_term_limit
        self.max_long_term = max_long_term
        self.importance_threshold = importance_threshold
        self.similarity_threshold = similarity_threshold
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

            # 4. Consolidate episodic into semantic memory
            await self._consolidate_to_semantic(npc_name, profile)

            # 5. Deduplicate semantic memories
            await self._deduplicate_semantic(npc_name, profile)

        self.store._save()

    async def _consolidate_to_semantic(self, npc_name: str, profile: NPCProfile):
        """Extract semantic facts from episodic memories using LLM."""
        # Find episodes not yet consolidated
        unconsolidated = [m for m in profile.long_term_episodic if not m.consolidated]
        if not unconsolidated:
            return

        batch_size = 5
        for i in range(0, len(unconsolidated), batch_size):
            batch = unconsolidated[i:i+batch_size]
            episodes_text = "\n".join(
                f"- [{m.timestamp.isoformat()}] {m.description}"
                for m in batch
            )
            prompt = f"""
You are extracting semantic knowledge for the character "{npc_name}".
From the following episodic memories, extract **facts** that become part of their long‑term knowledge base.
Each fact should be a statement about the world, other characters, or themselves.
Return a JSON array of strings (each string is one fact).
Skip trivial or redundant facts.

Episodes:
{episodes_text}
"""
            try:
                result = await self.llm.generate_json(prompt, temperature=0.3)
                facts = result if isinstance(result, list) else []
                for fact in facts:
                    # Check if fact already exists in semantic memory
                    existing = any(s.fact == fact for s in profile.semantic)
                    if not existing:
                        semantic = SemanticMemory(
                            id=f"{npc_name}_sem_{len(profile.semantic)}_{datetime.now().timestamp()}",
                            fact=fact,
                            source_episodes=[m.id for m in batch],
                            confidence=0.7,
                        )
                        profile.semantic.append(semantic)
                        # Compute embedding for semantic fact
                        await self.store._embed_text(semantic, npc_name, "semantic")
                # Mark episodes as consolidated
                for m in batch:
                    m.consolidated = True
            except Exception as e:
                logger.warning(f"Semantic consolidation failed for {npc_name}: {e}")

    async def _deduplicate_semantic(self, npc_name: str, profile: NPCProfile):
        """Merge similar semantic memories using embedding similarity."""
        if len(profile.semantic) < 2:
            return

        # Ensure all semantic memories have embeddings
        for sem in profile.semantic:
            if sem.embedding is None:
                await self.store._embed_text(sem, npc_name, "semantic")

        to_remove = set()
        for i, s1 in enumerate(profile.semantic):
            if s1.id in to_remove:
                continue
            for j, s2 in enumerate(profile.semantic[i+1:], start=i+1):
                if s2.id in to_remove:
                    continue
                # Compute similarity
                if s1.embedding and s2.embedding:
                    sim = cosine_similarity(s1.embedding, s2.embedding)
                    if sim >= self.similarity_threshold:
                        # Merge s2 into s1
                        s1.source_episodes.extend(s2.source_episodes)
                        s1.confidence = max(s1.confidence, s2.confidence)
                        to_remove.add(s2.id)

        # Remove duplicates
        profile.semantic = [s for s in profile.semantic if s.id not in to_remove]


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

    def __init__(self, state_path: Path, gm: GraphManager, llm: LLMClient):
        self.state_path = state_path
        self.gm = gm
        self.llm = llm
        self._npcs: Dict[str, NPCProfile] = {}
        self._embedding_cache_dir = state_path / "embeddings"
        self._embedding_cache_dir.mkdir(parents=True, exist_ok=True)
        self._load()
        self.optimizer = MemoryOptimizer(self, llm)
        self._embedding_lock = asyncio.Lock()

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
                    # Reconstruct semantic
                    semantic = []
                    for s in d.get("semantic", []):
                        semantic.append(SemanticMemory(
                            id=s["id"],
                            fact=s["fact"],
                            source_episodes=s.get("source_episodes", []),
                            confidence=s.get("confidence", 0.7),
                        ))
                    # Build profile
                    profile = NPCProfile(
                        name=name,
                        uid=d["uid"],
                        short_term=short_term,
                        long_term_episodic=long_term,
                        semantic=semantic,
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
                "semantic": [
                    {
                        "id": s.id,
                        "fact": s.fact,
                        "source_episodes": s.source_episodes,
                        "confidence": s.confidence,
                    }
                    for s in p.semantic
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
            elif isinstance(obj, SemanticMemory):
                text = obj.fact
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
                return [0.0] * 384  # fallback zero vector

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
        if name not in self._npcs:
            self._npcs[name] = NPCProfile(name=name, uid=uid, location=location)
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

    async def search_semantic(
        self,
        name: str,
        query: str,
        top_k: int = 5,
        min_confidence: float = 0.5,
    ) -> List[Tuple[SemanticMemory, float]]:
        """
        Search semantic memory using embedding similarity.
        Returns list of (SemanticMemory, similarity_score).
        """
        profile = self._npcs.get(name)
        if not profile or not profile.semantic:
            return []

        # Embed the query
        query_emb = await self._embed_text(query, name, "query")

        # Get embeddings for all semantic memories
        scored = []
        for sem in profile.semantic:
            if sem.confidence < min_confidence:
                continue
            if sem.embedding is None:
                sem.embedding = await self._embed_text(sem, name, "semantic")
            if sem.embedding:
                sim = cosine_similarity(query_emb, sem.embedding)
                scored.append((sem, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def get_relevant_memories(
        self,
        name: str,
        context: str,
        top_k: int = 10,
        include_semantic: bool = True,
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

        if include_semantic:
            for sem in profile.semantic:
                if sem.embedding is None:
                    sem.embedding = await self._embed_text(sem, name, "semantic")
                if sem.embedding:
                    sim = cosine_similarity(context_emb, sem.embedding)
                    candidates.append(("semantic", sem, sim))

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
