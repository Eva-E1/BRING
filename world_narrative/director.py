# world_narrative/director.py
"""
BRING v2 — Unified background narrative director.
Eliminates the split between world_narrative/director and world_director.
Uses EventBus for decoupled communication.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from world_core.utils import atomic_write_json
from world_core.event_bus import EventBus, EventTopic, Event, get_event_bus

from world_builder.graph_manager import GraphManager
from world_narrative.story_engine import StoryEngine
from world_narrative.chronicler import Chronicler
from world_narrative.world_clock import WorldClock
from world_narrative.memory_optimized import OptimizedMemoryStore
from world_narrative.quest_manager import QuestManager
from world_narrative.villain_manager import VillainManager
from world_narrative.story_planner import StoryPlanner

logger = logging.getLogger(__name__)


@dataclass
class DirectorConfig:
    tick_interval_minutes: int = 30
    chance_event_probability: float = 0.3
    major_beat_cooldown_hours: int = 6
    wake_interval_seconds: int = 60
    max_concurrent_beats: int = 5
    use_enhanced: bool = True


class Director:
    """
    Unified background narrative orchestrator.
    v2: Uses EventBus for decoupled communication, unified with world_director features.
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
        event_bus: Optional[EventBus] = None,
        # Extra dependencies from NarrativeContext
        graph_store: Optional[Any] = None,
        quest_mgr: Optional[QuestManager] = None,
        builder: Optional[Any] = None,
        llm: Optional[Any] = None,
    ):
        self.gm = gm
        self.story_engine = story_engine
        self.chronicler = chronicler
        self.clock = clock
        self.npc_mgr = npc_mgr
        self.config = config or DirectorConfig()
        self.state_dir = state_dir
        self._bus = event_bus or get_event_bus()

        # Store injected dependencies
        self.graph_store = graph_store
        self.quest_mgr = quest_mgr
        self.builder = builder
        self.llm = llm

        self.villain_mgr = VillainManager(gm, chronicler, state_dir / "villains.json")
        self.story_planner = StoryPlanner(gm, chronicler, state_dir / "story_plan.json")

        self._running = False
        self._background_task: Optional[asyncio.Task] = None
        self._last_major_beat_time: Optional[datetime] = None

        # Subscribe to events
        self._bus.subscribe(EventTopic.ENTITY_ADDED, self._on_entity_added)
        self._bus.subscribe(EventTopic.RELATIONSHIP_ADDED, self._on_relationship_added)

        self._load()

    async def _on_entity_added(self, event: Event):
        logger.debug(f"Director noticed new entity: {event.payload}")

    async def _on_relationship_added(self, event: Event):
        logger.debug(f"Director noticed new relationships: {event.payload}")

    def _load(self):
        data_path = self.state_dir / "director_state.json"
        if data_path.exists():
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
                self._last_major_beat_time = datetime.fromisoformat(data["last_major_beat"])
            except (json.JSONDecodeError, KeyError, TypeError):
                self._last_major_beat_time = None

    def _save(self):
        data = {
            "last_major_beat": (
                self._last_major_beat_time.isoformat()
                if self._last_major_beat_time
                else None
            ),
        }
        atomic_write_json(self.state_dir / "director_state.json", data)

    async def start(self):
        if self._running:
            return
        self._running = True
        self._background_task = asyncio.create_task(self._background_loop())
        logger.info("Director started")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
        logger.info("Director stopped")

    async def force_chance_event(self) -> Dict[str, Any]:
        return await self._generate_chance_event(self.clock.current_time)

    async def force_beat(self) -> Dict[str, Any]:
        return await self._generate_major_beat(self.clock.current_time)

    async def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "last_major_beat": (
                self._last_major_beat_time.isoformat()
                if self._last_major_beat_time
                else None
            ),
            "villain_status": await self.villain_mgr.get_status(),
            "story_plan": await self.story_planner.get_plan_summary(),
        }

    async def _background_loop(self):
        while self._running:
            try:
                await self.clock.tick(self.config.tick_interval_minutes)
                current_time = self.clock.current_time

                if hasattr(self.story_engine, "social_sim"):
                    await self.story_engine.social_sim.simulate_turn(current_time)

                villain_events = await self.villain_mgr.tick(current_time)
                for ev in villain_events:
                    await self._apply_villain_event(ev, current_time)

                if random.random() < self.config.chance_event_probability:
                    await self._generate_chance_event(current_time)

                await self._maybe_generate_major_beat(current_time)
                await self._process_scheduled_beats(current_time)

                self._save()
                await asyncio.sleep(self.config.wake_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Director loop error: {e}")
                await asyncio.sleep(5)

    async def _generate_chance_event(self, current_time: datetime) -> Dict[str, Any]:
        categories = [
            "accident", "discovery", "misunderstanding", "weather_event",
            "luck", "misfortune", "random_encounter", "rumor",
        ]
        category = random.choice(categories)
        npcs = list(self.npc_mgr.list_all().keys())
        involved = random.sample(npcs, min(2, len(npcs))) if npcs else []
        event = await self.story_engine.generate_event(
            current_time, involved, category=category, severity=random.uniform(0.2, 0.7)
        )
        await self.story_engine.apply_effects(
            event.get("effects", []), current_time, event.get("involved_entities", [])
        )
        await self.chronicler.log_event(
            f"[Director] Chance: {event['title']}", current_time, group="director"
        )
        await self._bus.publish_simple(
            EventTopic.STORY_EVENT,
            {"title": event["title"], "category": category},
            source="director",
        )
        return event

    async def _maybe_generate_major_beat(self, current_time: datetime):
        if self._last_major_beat_time:
            cooldown = timedelta(hours=self.config.major_beat_cooldown_hours)
            if current_time - self._last_major_beat_time < cooldown:
                return
        if await self.story_planner.should_generate_beat(current_time):
            await self._generate_major_beat(current_time)

    async def _generate_major_beat(self, current_time: datetime) -> Dict[str, Any]:
        logger.info("Generating major story beat")
        beat = await self.story_planner.generate_next_beat(current_time)
        if beat:
            event = await self.story_engine.generate_event(
                current_time,
                beat.get("involved_entities", []),
                category=beat.get("category", "story_beat"),
                severity=0.8,
            )
            await self.story_engine.apply_effects(
                event.get("effects", []), current_time, event.get("involved_entities", [])
            )
            await self.chronicler.log_event(
                f"[Director] Major beat: {event['title']}", current_time, group="director"
            )
            self._last_major_beat_time = current_time
            self._save()
            await self.story_planner.record_beat_completed(beat["id"], current_time)

            await self._bus.publish_simple(
                EventTopic.STORY_BEAT,
                {"title": event["title"], "beat_id": beat["id"]},
                source="director",
            )
            return event
        return {}

    async def _process_scheduled_beats(self, current_time: datetime):
        pending = await self.story_planner.get_pending_beats(current_time)
        for beat in pending:
            event = await self.story_engine.generate_event(
                current_time,
                beat.get("involved_entities", []),
                category=beat.get("category", "scheduled"),
                severity=0.6,
            )
            await self.story_engine.apply_effects(
                event.get("effects", []), current_time, event.get("involved_entities", [])
            )
            await self.chronicler.log_event(
                f"[Director] Scheduled: {event['title']}", current_time, group="director"
            )

    async def _apply_villain_event(self, ev: dict, current_time: datetime):
        await self.story_engine.apply_effects(
            ev.get("effects", []), current_time, ev.get("involved_entities", [])
        )
        await self._bus.publish_simple(
            EventTopic.VILLAIN_PROGRESS,
            {"event": ev.get("title", "Unknown")},
            source="director",
        )
