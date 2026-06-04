"""Dependency injection container for narrative services."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from world_builder.llm import LLMClient
from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_builder.config import get_entity_store_path, get_world_frame_path
from world_explorer.config import DEFAULT_DB_PATH
from world_explorer.store import GraphStore
from world_explorer.branch_manager import BranchManager

from .memory_optimized import OptimizedMemoryStore, NPCProfile
from .chronicler import Chronicler
from .validation import WorldValidator
from .story_engine import StoryEngine
from .director import Director, DirectorConfig
from .user_agent import UserAgent
from .quest_manager import QuestManager
from .social_sim import SocialSimulator
from .world_clock import WorldClock
from world_engine.roleplay_engine import RoleplayEngine
from .birth import BirthScenario
from world_core.llm_queue import GlobalLLMQueue
from world_core.probability.engine import ProbabilityEngine
from world_core.probability.resolver import ProbabilityContextResolver
from world_core.probability.profiles import get_profile
from world_core.romance import RomanceEngine

# New memory system imports
from world_core.memory import (
    WorldMemory,
    MemoryConfig,
    DEFAULT_CONFIG,
    EntityExtractor,
    ContradictionDetector,
    PainSignalManager,
    CognitivePipeline,
)

logger = logging.getLogger(__name__)


class NarrativeContext:
    """Centralised container for all narrative services. Boots once."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, memory_config: MemoryConfig = None):
        self.db_path = db_path
        self._booted = False
        self._services_started = False
        self._memory_config = memory_config or DEFAULT_CONFIG

        # Shared dependencies
        self.llm = LLMClient()
        self.llm_queue = GlobalLLMQueue(self.llm, max_concurrent=3)
        self.gm = GraphManager(entity_store_path=get_entity_store_path(db_path))
        self.world_frame = self._load_world_frame()
        self.graph_store = GraphStore(db_path)
        # Note: boot() is called separately in async contexts (e.g. API startup).
        # Do NOT call boot_sync() here - it causes issues when the event loop is already running.

        # ============================================================
        # NEW: Revolutionary Graph-Based Self-Optimizing Memory System
        # ============================================================
        self.world_memory = WorldMemory(
            storage_path=db_path / "world_memory",
            llm=self.llm,
            config=self._memory_config,
        )

        # Cognitive components for advanced memory processing
        self.entity_extractor = EntityExtractor(self.llm, self.world_memory)
        self.pain_signal_manager = PainSignalManager(self.world_memory)
        self.contradiction_detector = ContradictionDetector(
            self.world_memory,
            self.llm,
            similarity_threshold=self._memory_config.cluster_similarity_threshold
        )
        self.cognitive_pipeline = CognitivePipeline(
            self.world_memory,
            self.llm,
            self.entity_extractor,
            self.pain_signal_manager,
            self.contradiction_detector,
        )
        # ============================================================

        self.chronicler = Chronicler(
            db_path / "timeline.jsonl",
            world_memory=self.world_memory,
        )
        self.validator = WorldValidator(self.gm, self.world_frame)
        self.quest_mgr = QuestManager(db_path / "quests.json")
        self.social_sim = SocialSimulator(self)
        self.clock = WorldClock(db_path / "world_clock.json")

        # NPC Manager - runtime state for NPCs (separate from long-term memory)
        self.npc_mgr = OptimizedMemoryStore(
            db_path / "memory_store",
            self.gm,
            self.llm_queue,
            self.llm,
            max_embedding_cache_size=1000,
            world_memory=self.world_memory,
        )

        # Probability system - global engine and resolver
        self.prob_resolver = ProbabilityContextResolver(
            self.gm, self.npc_mgr, self.world_memory, self.world_frame
        )
        self.prob_engine = ProbabilityEngine(global_luck=0.5)
        self.prob_engine.set_context_resolver(self.prob_resolver)
        self.prob_engine.set_npc_manager(self.npc_mgr)
        self.prob_engine.set_world_memory(self.world_memory)
        # Load saved modifiers
        mod_path = db_path / "probability_modifiers.json"
        self.prob_engine.load_modifiers(mod_path)

        # Connect probability engine with world clock for global luck
        self.prob_engine.set_world_clock(self.clock)

        # Connect probability system with quest manager
        def prob_check(profile: str, actor: str, target: Optional[str] = None) -> bool:
            """Callback for checking probability-based quest objectives."""
            import asyncio
            try:
                profile_obj = get_profile(profile)
                if not profile_obj:
                    return False
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, create a task
                    return False  # Would need async handling
                context = loop.run_until_complete(
                    self.prob_resolver.build_context(actor, target, profile, None)
                )
                probability = self.prob_engine.get_success_chance(profile_obj, context, actor)
                # Consider complete if > 60% base chance (not considering luck)
                return probability > 0.6
            except Exception:
                return False

        self.quest_mgr.prob_check_callback = prob_check

        # Core engines - pass graph_store for intelligence integration
        self.story_engine = StoryEngine(
            self.llm_queue, self.gm, self.npc_mgr, self.chronicler, self.validator,
            self.world_frame["world_name"], self.world_frame.get("world_rules", []),
            self.quest_mgr, self.social_sim, self.clock,
            graph_store=self.graph_store,
            world_memory=self.world_memory,
            prob_engine=self.prob_engine,
            prob_resolver=self.prob_resolver,
        )

        # WorldBuilder for entity creation (needed by Director)
        self.builder = WorldBuilder(self.llm, self.gm, world_frame=self.world_frame)

        # Create the unified Director with enhanced features
        self.director = Director(
            gm=self.gm,
            story_engine=self.story_engine,
            chronicler=self.chronicler,
            clock=self.clock,
            npc_mgr=self.npc_mgr,
            state_dir=db_path / "director_state",
            config=DirectorConfig(use_enhanced=True),
            graph_store=self.graph_store,
            quest_mgr=self.quest_mgr,
            builder=self.builder,
            llm=self.llm,
        )

        # Birth scenario helper (unified character creation)
        self.birth_scenario = BirthScenario

        self.user_agent = UserAgent(
            self.llm, self.gm, self.npc_mgr, self.chronicler, self.director,
            self.story_engine, self.validator, self.quest_mgr, db_path / "sessions"
        )

        # Inject story_engine into clock for callback support
        self.clock.story_engine = self.story_engine

        # Romance Engine - deterministic romantic relationship system
        self.romance_engine = RomanceEngine(
            prob_engine=self.prob_engine,
            world_memory=self.world_memory,
            gm=self.gm,
            npc_mgr=self.npc_mgr,
            director=self.director,
            data_dir=db_path / "romance",
        )

        # Session History Manager - persistent conversation storage
        from world_core.history_manager import HistoryManager
        self.history_mgr = HistoryManager(db_path)

        # Auto-register all characters from world frame into memory store
        self._register_existing_characters()

        self._booted = True

    def _load_world_frame(self) -> dict:
        path = get_world_frame_path(self.db_path)
        if not path.exists():
            raise FileNotFoundError(f"World frame not found at {path}. Run `world_builder build` first.")
        return json.loads(path.read_text())

    def _register_existing_characters(self) -> None:
        """Auto-register all characters from the world frame into the memory store."""
        characters = self.world_frame.get("characters", [])
        registered_count = 0

        for ch in characters:
            name = ch.get("name")
            if not name:
                continue

            # Use L2 current_location if available, otherwise fallback to L1 or default
            loc = ch.get("current_location")
            if not loc and isinstance(ch, dict):
                l2 = ch.get("profile", {}).get("l2", {})
                loc = l2.get("current_location", l2.get("location"))

            loc = loc or "unknown"

            # Only register if not already in runtime state (synchronous check)
            if name not in self.npc_mgr._npcs:
                uid = f"Character:{name}"
                # Directly create the profile synchronously (bypasses async register)
                self.npc_mgr._npcs[name] = NPCProfile(
                    name=name,
                    uid=uid,
                    location=loc,
                )
                registered_count += 1
                logger.debug(f"Registered character from world frame: {name} at {loc}")

        if registered_count > 0:
            self.npc_mgr._save()
            logger.info(f"Auto-registered {registered_count} characters from world frame")

    def ensure_booted(self):
        if not self._booted:
            raise RuntimeError("NarrativeContext not properly initialised.")

    async def start_background_services(self) -> None:
        """Start all background services (LLM queue, director, memory optimizer, and new memory system)."""
        if self._services_started:
            return
        await self.llm_queue.start()
        await self.director.start()
        await self.npc_mgr.start_optimizer()

        # NEW: Start the new memory system components
        await self.world_memory.start()

        self._services_started = True
        logger.info("All background services started")

    async def stop_background_services(self) -> None:
        """Stop all background services."""
        if not self._services_started:
            return
        await self.llm_queue.stop()
        await self.director.stop()
        await self.npc_mgr.stop_optimizer()

        # NEW: Stop the new memory system components
        await self.world_memory.stop()

        self._services_started = False
        logger.info("All background services stopped")

    async def start_director(self) -> None:
        """Start the background director task."""
        await self.director.start()

    async def stop_director(self) -> None:
        """Stop the background director task."""
        await self.director.stop()

    async def start_memory_optimizer(self) -> None:
        """Start the memory optimizer background task."""
        await self.npc_mgr.start_optimizer()
        # Also start the new memory system optimizer
        await self.world_memory.optimizer.start()

    async def stop_memory_optimizer(self) -> None:
        """Stop the memory optimizer background task."""
        await self.npc_mgr.stop_optimizer()
        # Also stop the new memory system optimizer
        await self.world_memory.optimizer.stop()

    async def get_memory_stats(self) -> dict:
        """Get comprehensive memory system statistics."""
        stats = await self.world_memory.get_stats()
        stats["cognitive_pipeline"] = self.cognitive_pipeline.get_statistics()
        stats["contradiction_detector"] = self.contradiction_detector.get_statistics()
        stats["pain_signals"] = self.pain_signal_manager.get_statistics()
        return stats

    async def trigger_memory_optimization(self) -> None:
        """Manually trigger memory optimization."""
        await self.world_memory.optimizer.run_manual()

    def create_roleplay_engine(
        self,
        character: str = None,
        location: str = None,
    ) -> RoleplayEngine:
        """Create a new RoleplayEngine instance for third-person roleplay."""
        engine = RoleplayEngine(
            db_path=self.db_path,
            world_frame=self.world_frame,
            llm_queue=self.llm_queue,
            gm=self.gm,
            npc_mgr=self.npc_mgr,
            chronicler=self.chronicler,
            director=self.director,
            story_engine=self.story_engine,
            validator=self.validator,
            quest_mgr=self.quest_mgr,
            clock=self.clock,
            graph_store=self.graph_store,
            world_memory=self.world_memory,
            history_mgr=self.history_mgr,
        )
        # Determine starting location
        if not location:
            locs = self.gm.store.list_by_type("Location")
            location = locs[0].name if locs else "unknown"

        engine.set_session(
            character=character,
            location=location,
            story_time=datetime.now(),
            role="protagonist",
        )
        return engine

    async def process_turn_with_memory(
        self,
        user_message: str,
        assistant_response: str,
        turn_id: int,
        session_id: str = None,
    ) -> dict:
        """
        Process a conversation turn through the cognitive pipeline.

        This extracts facts, entities, checks for contradictions,
        and retrieves relevant context.
        """
        return await self.cognitive_pipeline.process_turn(
            user_message=user_message,
            assistant_response=assistant_response,
            turn_id=turn_id,
            session_id=session_id,
        )

    async def get_context_for_prompt(
        self,
        query: str,
        session_id: str = None,
        include_warnings: bool = True,
    ) -> dict:
        """Get context and warnings for a prompt without storing the conversation."""
        return await self.cognitive_pipeline.get_context_for_response(
            user_message=query,
            session_id=session_id,
            include_warnings=include_warnings,
        )

    async def record_pain_signal(
        self,
        description: str,
        keywords: list,
        source_id: str,
        importance: float = 0.8,
    ) -> str:
        """Record a pain signal for tracking failures."""
        return await self.pain_signal_manager.record_pain(
            description=description,
            keywords=keywords,
            source_id=source_id,
            importance=importance,
        )

    async def get_pain_warnings(self, context_text: str, top_k: int = 3) -> list:
        """Get pain signal warnings for the given context."""
        return await self.pain_signal_manager.get_warnings(context_text, top_k)

    async def shutdown(self) -> None:
        """Clean shutdown of narrative services."""
        logger.info("Shutting down NarrativeContext...")
        # Stop all background services
        await self.stop_background_services()
        # Save any pending state
        self.npc_mgr._save()
        self.clock._save()
        # Save probability modifiers
        mod_path = self.db_path / "probability_modifiers.json"
        self.prob_engine.save_modifiers(mod_path)
        logger.info("NarrativeContext shutdown complete.")
