"""Background narrative director – orchestrates deep story, chance events, villains, and NPC interactions.

This is a unified Director that combines:
- Original Director functionality (villains, story planner, NPC simulator)
- Enhanced features from world_director (multi-agent queue, graph expansion, world evolution, story arcs)
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_narrative.story_engine import StoryEngine
from world_narrative.chronicler import Chronicler
from world_narrative.world_clock import WorldClock
from world_narrative.memory_optimized import OptimizedMemoryStore
from world_narrative.quest_manager import QuestManager
from world_narrative.villain_manager import VillainManager
from world_narrative.story_planner import StoryPlanner
from world_narrative.npc_simulator import NPCSimulator
from world_explorer.store import GraphStore

# Import from world_director
from world_director.agent_coordinator import AgentCoordinator
from world_director.story_arc_manager import StoryArcManager
from world_director.world_evolver import WorldEvolver
from world_director.models import DirectorTask, TaskPriority

logger = logging.getLogger(__name__)


@dataclass
class DirectorConfig:
    """Configuration for the director's behaviour."""
    # How often to run the main tick (in story minutes)
    tick_interval_minutes: int = 30
    # Probability of a chance event per tick (0-1)
    chance_event_probability: float = 0.3
    # Minimum time between major story beats (in hours)
    major_beat_cooldown_hours: int = 6
    # Schedule check interval (in real seconds) for background loop
    wake_interval_seconds: int = 60
    # Maximum number of concurrent scheduled story beats
    max_concurrent_beats: int = 5
    # Enable enhanced features (multi-agent queue, world evolution)
    use_enhanced: bool = True


class Director:
    """
    Unified background narrative orchestrator.

    Combines:
    - Original Director: villains, story planner, NPC interactions
    - Enhanced features: multi-agent queue, graph expansion, world evolution, story arcs

    Runs as an async task, advancing story arcs, villains, and NPC interactions.
    """

    def __init__(
        self,
        gm: GraphManager,
        story_engine: StoryEngine,
        chronicler: Chronicler,
        clock: WorldClock,
        npc_mgr: OptimizedMemoryStore,
        state_dir: Path,
        config: Optional[DirectorConfig] = None,
        # Enhanced features parameters
        graph_store: Optional[GraphStore] = None,
        quest_mgr: Optional[QuestManager] = None,
        builder: Optional[WorldBuilder] = None,
        llm: Any = None,
    ):
        self.gm = gm
        self.story_engine = story_engine
        self.chronicler = chronicler
        self.clock = clock
        self.npc_mgr = npc_mgr
        self.config = config or DirectorConfig()
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Sub‑modules (original)
        self.villain_mgr = VillainManager(gm, chronicler, state_dir / "villains.json")
        self.story_planner = StoryPlanner(gm, chronicler, state_dir / "story_plan.json")
        self.npc_sim = NPCSimulator(gm, chronicler, npc_mgr, state_dir / "npc_memories.json")

        # Enhanced features
        self.use_enhanced = self.config.use_enhanced
        if self.use_enhanced:
            self.graph_store = graph_store
            self.quest_mgr = quest_mgr
            self.builder = builder
            self.llm = llm

            # Multi-agent task coordinator
            self.coordinator = AgentCoordinator(max_concurrent_tasks=3)

            # Story arc manager
            self.arc_manager = StoryArcManager(state_dir / "story_arcs.json")

            # World evolver
            if builder and llm:
                self.evolver = WorldEvolver(gm, builder, npc_mgr, chronicler, llm)
            else:
                self.evolver = None
                logger.warning("WorldEvolver not initialized: missing builder or llm")

            # Register task handlers
            self._register_handlers()
        else:
            self.coordinator = None
            self.arc_manager = None
            self.evolver = None

        # Runtime state
        self._running = False
        self._background_task: Optional[asyncio.Task] = None
        self._last_major_beat_time: Optional[datetime] = None

        # Load any existing state
        self._load()

    def _register_handlers(self):
        """Register task handlers for the coordinator."""
        if not self.use_enhanced:
            return
        self.coordinator.register_handler("expand_branch", self._handle_expand_branch)
        self.coordinator.register_handler("add_entity", self._handle_add_entity)
        self.coordinator.register_handler("edit_entity", self._handle_edit_entity)
        self.coordinator.register_handler("generate_event", self._handle_generate_event)
        self.coordinator.register_handler("advance_arc", self._handle_advance_arc)
        self.coordinator.register_handler("evolve_world", self._handle_evolve_world)

    def _load(self):
        data_path = self.state_dir / "director_state.json"
        if data_path.exists():
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
                self._last_major_beat_time = datetime.fromisoformat(data["last_major_beat"])
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Failed to load director state: {e}")
                self._last_major_beat_time = None

    def _save(self):
        data = {
            "last_major_beat": self._last_major_beat_time.isoformat() if self._last_major_beat_time else None,
        }
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "director_state.json").write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------
    # Public API – to be called by the main narrative system
    # ------------------------------------------------------------------

    async def start(self):
        """Start the background director task."""
        if self._running:
            return
        self._running = True

        # Start enhanced coordinator if enabled
        if self.use_enhanced and self.coordinator:
            await self.coordinator.start()

        self._background_task = asyncio.create_task(self._background_loop())
        logger.info("Director background task started")

    async def stop(self):
        """Stop the background director task."""
        if not self._running:
            return
        self._running = False

        # Stop background task
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None

        # Stop coordinator if running
        if self.use_enhanced and self.coordinator:
            await self.coordinator.stop()

        logger.info("Director background task stopped")

    async def force_chance_event(self) -> Dict[str, Any]:
        """Manually trigger a chance event (used for testing or CLI)."""
        return await self._generate_chance_event(self.clock.current_time)

    async def force_beat(self) -> Dict[str, Any]:
        """Force a major story beat to be generated immediately."""
        return await self._generate_major_beat(self.clock.current_time)

    async def get_status(self) -> Dict[str, Any]:
        """Return current director status for debugging."""
        return {
            "running": self._running,
            "last_major_beat": self._last_major_beat_time.isoformat() if self._last_major_beat_time else None,
            "villain_status": await self.villain_mgr.get_status(),
            "story_plan": await self.story_planner.get_plan_summary(),
        }

    # ------------------------------------------------------------------
    # Enhanced task handlers
    # ------------------------------------------------------------------

    async def _handle_expand_branch(self, task: DirectorTask):
        """Expand a branch of the graph (subgraph around a center node)."""
        center_uid = task.data.get("center_uid")
        depth = task.data.get("depth", 1)
        if not center_uid:
            logger.error("expand_branch task missing center_uid")
            return
        try:
            from world_intelligence.subgraph_expander import SubgraphExpander
            from world_explorer.builder_integration import BuilderInterface
            bi = BuilderInterface(self.gm)
            expander = SubgraphExpander(self.graph_store, bi)
            report = expander.expand(center_uid, depth=depth, complete_layers=True)
            await self.chronicler.log_event(
                f"Expanded subgraph around {center_uid}: {report.get('nodes_in_subgraph')} nodes",
                self.clock.current_time,
                group="director"
            )
        except ImportError as e:
            logger.warning(f"SubgraphExpander not available: {e}")

    async def _handle_add_entity(self, task: DirectorTask):
        """Add a new entity via world evolver."""
        if not self.evolver:
            return
        entity_type = task.data.get("entity_type")
        data = task.data.get("data", {})
        if entity_type == "npc":
            name = await self.evolver.add_random_npc(data.get("faction"))
        elif entity_type == "location":
            name = await self.evolver.add_random_location()
        elif entity_type == "item":
            name = await self.evolver.add_random_item(data.get("item_type", "artifact"))

    async def _handle_edit_entity(self, task: DirectorTask):
        """Edit an existing entity's L2 or L3 data."""
        uid = task.data.get("uid")
        layer = task.data.get("layer", "l2")
        new_data = task.data.get("data", {})
        if not uid:
            return
        success = self.gm.store.update_entity_level(uid, layer, new_data)
        if success:
            await self.chronicler.log_event(f"Updated {layer} for {uid}", self.clock.current_time, group="director")

    async def _handle_generate_event(self, task: DirectorTask):
        """Generate a story event."""
        category = task.data.get("category", "incident")
        severity = task.data.get("severity", 0.5)
        involved = task.data.get("involved_entities", [])
        event = await self.story_engine.generate_event(self.clock.current_time, involved, category, severity)
        await self.story_engine.apply_effects(event.get("effects", []), self.clock.current_time, involved)
        await self.chronicler.log_event(f"Director event: {event['title']} – {event['description']}", self.clock.current_time, group="director")

    async def _handle_advance_arc(self, task: DirectorTask):
        """Advance a story arc to its next phase."""
        if not self.arc_manager:
            return
        arc_id = task.data.get("arc_id")
        if arc_id:
            self.arc_manager.advance_phase(arc_id)
            await self.chronicler.log_event(f"Story arc {arc_id} advanced to next phase", self.clock.current_time, group="director")

    async def _handle_evolve_world(self, task: DirectorTask):
        """Periodic world evolution."""
        if self.evolver:
            await self.evolver.evolve_world(self.clock.current_time)

    # ------------------------------------------------------------------
    # Public enhanced methods
    # ------------------------------------------------------------------

    async def expand_branch(self, center_uid: str, depth: int = 1):
        """Public method to expand a subgraph."""
        if not self.use_enhanced or not self.coordinator:
            logger.warning("Enhanced features not enabled")
            return
        await self.coordinator.submit(DirectorTask(
            id=str(uuid4()),
            type="expand_branch",
            priority=TaskPriority.NORMAL,
            data={"center_uid": center_uid, "depth": depth},
            created_at=datetime.now(),
        ))

    async def add_entity(self, entity_type: str, **kwargs):
        """Add a new entity (npc, location, item)."""
        if not self.use_enhanced or not self.coordinator:
            logger.warning("Enhanced features not enabled")
            return
        await self.coordinator.submit(DirectorTask(
            id=str(uuid4()),
            type="add_entity",
            priority=TaskPriority.NORMAL,
            data={"entity_type": entity_type, "data": kwargs},
            created_at=datetime.now(),
        ))

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _background_loop(self):
        """Main loop – wakes periodically and processes story ticks."""
        while self._running:
            try:
                # Advance the world clock by the tick interval
                await self.clock.tick(self.config.tick_interval_minutes)
                current_time = self.clock.current_time

                # 1. Run NPC interaction simulation
                await self._process_npc_interactions(current_time)

                # 2. Advance villain agendas
                villain_events = await self.villain_mgr.tick(current_time)
                for ev in villain_events:
                    await self._apply_villain_event(ev, current_time)

                # 3. Chance event
                if random.random() < self.config.chance_event_probability:
                    await self._generate_chance_event(current_time)

                # 4. Check if a major story beat is due
                await self._maybe_generate_major_beat(current_time)

                # 5. Process any scheduled story beats from the planner
                await self._process_scheduled_beats(current_time)

                # 6. Enhanced: World evolution (every 30 story minutes)
                if self.use_enhanced and current_time.minute % 30 == 0 and self.coordinator:
                    await self.coordinator.submit(DirectorTask(
                        id=str(uuid4()),
                        type="evolve_world",
                        priority=TaskPriority.LOW,
                        data={},
                        created_at=datetime.now(),
                    ))

                # Save director state after each loop
                self._save()

                # Sleep real time
                await asyncio.sleep(self.config.wake_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Director background loop error: {e}")
                await asyncio.sleep(5)  # backoff

    # ------------------------------------------------------------------
    # Internal generators
    # ------------------------------------------------------------------

    async def _process_npc_interactions(self, current_time: datetime):
        """Run the NPC simulator to generate complex interactions."""
        events = await self.npc_sim.tick(current_time)
        for ev in events:
            await self._apply_npc_event(ev, current_time)

    async def _generate_chance_event(self, current_time: datetime) -> Dict[str, Any]:
        """Generate a random, unexpected event (accident, discovery, etc.)."""
        logger.debug("Generating chance event")
        categories = [
            "accident", "discovery", "misunderstanding", "weather_event",
            "luck", "misfortune", "random_encounter", "rumor"
        ]
        category = random.choice(categories)
        # Pick a random NPC as initiator (if any exist)
        npcs = list(self.npc_mgr.list_all().keys())
        involved = random.sample(npcs, min(2, len(npcs))) if npcs else []
        event = await self.story_engine.generate_event(
            current_time, involved, category=category, severity=random.uniform(0.2, 0.7)
        )
        await self.story_engine.apply_effects(
            event.get("effects", []),
            current_time,
            event.get("involved_entities", [])
        )
        await self.chronicler.log_event(
            f"[Director] Chance event: {event['title']} – {event['description']}",
            current_time,
            group="director"
        )
        return event

    async def _maybe_generate_major_beat(self, current_time: datetime):
        """Generate a major story beat if cooldown has passed and planner requests it."""
        if self._last_major_beat_time:
            cooldown = timedelta(hours=self.config.major_beat_cooldown_hours)
            if current_time - self._last_major_beat_time < cooldown:
                return
        # Ask the story planner if we need a beat
        if await self.story_planner.should_generate_beat(current_time):
            await self._generate_major_beat(current_time)

    async def _generate_major_beat(self, current_time: datetime) -> Dict[str, Any]:
        """Generate a major story beat (chapter transition, villain reveal, etc.)."""
        logger.info("Generating major story beat")
        beat = await self.story_planner.generate_next_beat(current_time)
        if beat:
            # Convert the beat into a story event
            event = await self.story_engine.generate_event(
                current_time,
                beat.get("involved_entities", []),
                category=beat.get("category", "story_beat"),
                severity=0.8,
            )
            await self.story_engine.apply_effects(
                event.get("effects", []),
                current_time,
                event.get("involved_entities", [])
            )
            await self.chronicler.log_event(
                f"[Director] Major beat: {event['title']} – {event['description']}",
                current_time,
                group="director"
            )
            self._last_major_beat_time = current_time
            self._save()
            # Schedule follow‑up beats via the planner
            await self.story_planner.record_beat_completed(beat["id"], current_time)
            return event
        return {}

    async def _process_scheduled_beats(self, current_time: datetime):
        """Execute any scheduled story beats that are due."""
        pending = await self.story_planner.get_pending_beats(current_time)
        for beat in pending:
            event = await self.story_engine.generate_event(
                current_time,
                beat.get("involved_entities", []),
                category=beat.get("category", "scheduled"),
                severity=0.6,
            )
            await self.story_engine.apply_effects(
                event.get("effects", []),
                current_time,
                event.get("involved_entities", [])
            )
            await self.chronicler.log_event(
                f"[Director] Scheduled beat: {event['title']} – {event['description']}",
                current_time,
                group="director"
            )
            await self.story_planner.mark_beat_done(beat["id"])

    async def _apply_villain_event(self, villain_event: dict, current_time: datetime):
        """Apply an event generated by the villain manager."""
        event = await self.story_engine.generate_event(
            current_time,
            villain_event.get("involved_entities", []),
            category="villain_move",
            severity=villain_event.get("severity", 0.7),
        )
        await self.story_engine.apply_effects(
            event.get("effects", []),
            current_time,
            event.get("involved_entities", [])
        )
        await self.chronicler.log_event(
            f"[Villain] {event['title']} – {event['description']}",
            current_time,
            group="villain"
        )

    async def _apply_npc_event(self, npc_event: dict, current_time: datetime):
        """Apply an event generated by the NPC simulator."""
        await self.story_engine.apply_effects(
            [npc_event],
            current_time,
            npc_event.get("involved_entities", [])
        )
        await self.chronicler.log_event(
            f"[NPC] {npc_event.get('description', 'Interaction')}",
            current_time,
            group="npc"
        )

    # ------------------------------------------------------------------
    # Legacy API - keep for backward compatibility
    # ------------------------------------------------------------------

    async def get_narrative_context(
        self,
        query: str,
        story_time: datetime,
    ) -> dict:
        """Get narrative context for a query (legacy compatibility)."""
        nodes = self.gm.store.search(query)
        current = [
            {"name": n.name, "type": n.entity_type, "summary": n.profile.l1.get("summary", "")}
            for n in nodes[:10]
        ]
        timeline = await self.chronicler.get_timeline(since=story_time, limit=20)
        return {
            "story_time": story_time.isoformat(),
            "current_state": current,
            "relevant_history": timeline,
        }

    async def advance_story(
        self,
        story_time: datetime,
        world_name: str,
        involved_entities: Optional[List[str]] = None,
    ) -> dict:
        """Advance the story by one tick (legacy compatibility)."""
        result = await self.story_engine.tick(story_time, involved_entities)
        # Schedule follow‑up events based on villain clocks
        for villain, progress in self.story_engine._villain_clocks.items():
            if progress >= 5 and progress % 5 == 0:
                await self.clock.schedule_event(
                    story_time + timedelta(hours=12),
                    "villain_event",
                    {"villain": villain, "progress": progress}
                )
        return result
