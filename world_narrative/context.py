"""Dependency injection container for narrative services."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime

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
from world_director.newborn_scenario import NewbornScenario
from world_core.llm_queue import GlobalLLMQueue

logger = logging.getLogger(__name__)


class NarrativeContext:
    """Centralised container for all narrative services. Boots once."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._booted = False

        # Shared dependencies
        self.llm = LLMClient()
        self.llm_queue = GlobalLLMQueue(self.llm, max_concurrent=3)
        self.gm = GraphManager(entity_store_path=get_entity_store_path(db_path))
        self.world_frame = self._load_world_frame()
        self.graph_store = GraphStore(db_path)
        self.graph_store.boot()

        # Narrative components
        self.npc_mgr = OptimizedMemoryStore(
            db_path / "memory_store", self.gm, self.llm_queue, self.llm,
            max_embedding_cache_size=1000
        )
        self.chronicler = Chronicler(db_path / "timeline.jsonl")
        self.validator = WorldValidator(self.gm, self.world_frame)
        self.quest_mgr = QuestManager(db_path / "quests.json")
        self.social_sim = SocialSimulator(self)
        self.clock = WorldClock(db_path / "world_clock.json")

        # Core engines - pass graph_store for intelligence integration
        self.story_engine = StoryEngine(
            self.llm_queue, self.gm, self.npc_mgr, self.chronicler, self.validator,
            self.world_frame["world_name"], self.world_frame.get("world_rules", []),
            self.quest_mgr, self.social_sim, self.clock,
            graph_store=self.graph_store
        )

        # WorldBuilder for entity creation (needed by Director)
        self.builder = WorldBuilder(self.world_frame, self.gm)

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

        # Newborn scenario helper
        self.newborn_scenario = NewbornScenario

        self.user_agent = UserAgent(
            self.llm, self.gm, self.npc_mgr, self.chronicler, self.director,
            self.story_engine, self.validator, self.quest_mgr, db_path / "sessions"
        )

        # Inject story_engine into clock for callback support
        self.clock.story_engine = self.story_engine

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
        """Start all background services (LLM queue, director, and memory optimizer)."""
        await self.llm_queue.start()
        await self.director.start()
        await self.npc_mgr.start_optimizer()
        logger.info("All background services started")

    async def stop_background_services(self) -> None:
        """Stop all background services."""
        await self.llm_queue.stop()
        await self.director.stop()
        await self.npc_mgr.stop_optimizer()
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

    async def stop_memory_optimizer(self) -> None:
        """Stop the memory optimizer background task."""
        await self.npc_mgr.stop_optimizer()

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

    async def shutdown(self) -> None:
        """Clean shutdown of narrative services."""
        logger.info("Shutting down NarrativeContext...")
        # Stop all background services
        await self.stop_background_services()
        # Save any pending state
        self.npc_mgr._save()
        self.clock._save()
        logger.info("NarrativeContext shutdown complete.")
