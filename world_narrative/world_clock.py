"""World clock with scheduled event callbacks."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ScheduledEvent:
    """A scheduled event that fires at a specific time."""
    time: datetime
    callback: str  # registered callback name
    data: Dict[str, Any] = field(default_factory=dict)


class WorldClock:
    def __init__(self, state_path: Path, story_engine=None):
        self.state_path = state_path
        self.story_engine = story_engine  # Inject after creation for callback support
        self.current_time = datetime.now()
        self.scheduled_events: List[ScheduledEvent] = []
        self._callbacks: Dict[str, Callable] = {}  # Registry of callback functions
        self._load()

    def register_callback(self, name: str, callback: Callable) -> None:
        """Register a callback function for scheduled events."""
        self._callbacks[name] = callback
        logger.debug(f"Registered callback: {name}")

    def _get_callback(self, name: str) -> Optional[Callable]:
        """Get a registered callback by name."""
        return self._callbacks.get(name)

    def _load(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                self.current_time = datetime.fromisoformat(data["current_time"])
                self.scheduled_events = [
                    ScheduledEvent(
                        datetime.fromisoformat(e["time"]),
                        e["callback"],
                        e.get("data", {})
                    )
                    for e in data.get("scheduled", [])
                ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load world clock state: {e}. Starting fresh.")
                self.current_time = datetime.now()
                self.scheduled_events = []

    def _save(self):
        """Save clock state to disk with atomic write."""
        data = {
            "current_time": self.current_time.isoformat(),
            "scheduled": [
                {
                    "time": e.time.isoformat(),
                    "callback": e.callback,
                    "data": e.data,
                }
                for e in self.scheduled_events
            ],
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=2))

    async def tick(self, minutes: int = 10):
        """Advance the world clock by the specified minutes."""
        self.current_time += timedelta(minutes=minutes)

        # Fire any due events
        due = [e for e in self.scheduled_events if e.time <= self.current_time]
        self.scheduled_events = [e for e in self.scheduled_events if e.time > self.current_time]

        for event in due:
            await self._dispatch_event(event)

        self._save()

    async def _dispatch_event(self, event: ScheduledEvent) -> None:
        """Dispatch a scheduled event to its registered callback."""
        callback_name = event.callback
        logger.info(f"Dispatching scheduled event: {callback_name} with data {event.data}")

        # Handle built-in callback types
        if callback_name == "villain_event" and self.story_engine:
            villain = event.data.get("villain")
            progress = event.data.get("progress")
            if villain:
                try:
                    await self.story_engine.generate_event(
                        self.current_time,
                        [villain],
                        category="villain_move",
                        severity=event.data.get("severity", 0.7)
                    )
                    logger.info(f"Generated villain event for {villain}")
                except Exception as e:
                    logger.error(f"Failed to generate villain event: {e}")

        elif callback_name == "npc_event" and self.story_engine:
            npc = event.data.get("npc")
            if npc:
                try:
                    await self.story_engine.generate_event(
                        self.current_time,
                        [npc],
                        category="npc_event",
                        severity=event.data.get("severity", 0.5)
                    )
                except Exception as e:
                    logger.error(f"Failed to generate NPC event: {e}")

        elif callback_name == "quest_event" and self.story_engine:
            quest_id = event.data.get("quest_id")
            if quest_id and hasattr(self.story_engine, 'quest_mgr'):
                try:
                    quest = self.story_engine.quest_mgr.get_quest(quest_id)
                    if quest:
                        # Trigger quest-related event
                        await self.story_engine.apply_effects(
                            [{"type": "quest_update", "quest_id": quest_id, "update": event.data.get("update", "progress")}],
                            self.current_time
                        )
                except Exception as e:
                    logger.error(f"Failed to process quest event: {e}")

        elif callback_name == "random_event" and self.story_engine:
            # Generate a random story event
            try:
                await self.story_engine.generate_event(
                    self.current_time,
                    event.data.get("involved_entities", []),
                    category="incident",
                    severity=event.data.get("severity", 0.3)
                )
            except Exception as e:
                logger.error(f"Failed to generate random event: {e}")

        else:
            # Try to find custom registered callback
            custom_callback = self._get_callback(callback_name)
            if custom_callback:
                try:
                    if asyncio.iscoroutinefunction(custom_callback):
                        await custom_callback(event.data)
                    else:
                        custom_callback(event.data)
                except Exception as e:
                    logger.error(f"Custom callback {callback_name} failed: {e}")
            else:
                logger.warning(f"No handler found for scheduled event: {callback_name}")

    async def schedule_event(
        self,
        when: datetime,
        callback: str,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Schedule an event to fire at a specific time."""
        event = ScheduledEvent(when, callback, data or {})
        self.scheduled_events.append(event)
        # Keep events sorted by time
        self.scheduled_events.sort(key=lambda e: e.time)
        self._save()
        logger.debug(f"Scheduled event: {callback} at {when.isoformat()}")

    async def schedule_relative(
        self,
        minutes_from_now: int,
        callback: str,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Schedule an event relative to current time."""
        when = self.current_time + timedelta(minutes=minutes_from_now)
        await self.schedule_event(when, callback, data)

    def get_scheduled_events(self) -> List[Dict[str, Any]]:
        """Get list of upcoming scheduled events."""
        return [
            {
                "time": e.time.isoformat(),
                "callback": e.callback,
                "data": e.data,
            }
            for e in self.scheduled_events
        ]

    def clear_scheduled_events(self, callback: Optional[str] = None) -> int:
        """Clear scheduled events, optionally filtered by callback name."""
        if callback is None:
            count = len(self.scheduled_events)
            self.scheduled_events = []
        else:
            count = sum(1 for e in self.scheduled_events if e.callback == callback)
            self.scheduled_events = [e for e in self.scheduled_events if e.callback != callback]
        self._save()
        return count
