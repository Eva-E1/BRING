"""
BRING v2 — Async event bus for decoupled inter-module communication.
Replaces direct cross-module calls with publish/subscribe.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)


class EventTopic(str, Enum):
    # Entity lifecycle
    ENTITY_ADDED = "entity.added"
    ENTITY_UPDATED = "entity.updated"
    ENTITY_REMOVED = "entity.removed"
    ENTITY_LAYER_COMPLETED = "entity.layer_completed"

    # Relationships
    RELATIONSHIP_ADDED = "relationship.added"
    RELATIONSHIP_REPAIRED = "relationship.repaired"
    RELATIONSHIP_BROKEN = "relationship.broken"

    # World
    WORLD_CREATED = "world.created"
    WORLD_FRAME_LOADED = "world.frame_loaded"
    WORLD_EVOLVED = "world.evolved"

    # Narrative
    STORY_EVENT = "narrative.event"
    STORY_BEAT = "narrative.beat"
    VILLAIN_PROGRESS = "narrative.villain_progress"
    QUEST_ADDED = "narrative.quest_added"
    QUEST_UPDATED = "narrative.quest_updated"

    # Memory
    MEMORY_ADDED = "memory.added"
    MEMORY_CONSOLIDATED = "memory.consolidated"
    MEMORY_FORGOTTEN = "memory.forgotten"

    # System
    MAINTENANCE_START = "system.maintenance_start"
    MAINTENANCE_DONE = "system.maintenance_done"
    GRAPH_CHANGED = "system.graph_changed"
    ERROR = "system.error"


@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid4()))
    topic: EventTopic = EventTopic.ERROR
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""  # module name that published


# Type alias for async event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Async-safe event bus with:
    - Topic-based subscription
    - Priority ordering
    - Error isolation (one handler failure doesn't affect others)
    - Event replay buffer for late subscribers
    """

    def __init__(self, replay_buffer_size: int = 100):
        self._handlers: Dict[EventTopic, List[tuple]] = defaultdict(list)
        self._replay_buffer: List[Event] = []
        self._replay_buffer_size = replay_buffer_size
        self._running = False

    def subscribe(
        self,
        topic: EventTopic,
        handler: EventHandler,
        priority: int = 0,
    ) -> None:
        """Subscribe to a topic. Higher priority = called first."""
        self._handlers[topic].append((priority, handler))
        self._handlers[topic].sort(key=lambda x: x[0], reverse=True)

    def subscribe_many(
        self,
        topics: List[EventTopic],
        handler: EventHandler,
        priority: int = 0,
    ) -> None:
        for topic in topics:
            self.subscribe(topic, handler, priority)

    def unsubscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        self._handlers[topic] = [
            (p, h) for p, h in self._handlers[topic] if h is not handler
        ]

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of its topic."""
        # Store in replay buffer
        self._replay_buffer.append(event)
        if len(self._replay_buffer) > self._replay_buffer_size:
            self._replay_buffer.pop(0)

        # Fire handlers (isolated)
        handlers = self._handlers.get(event.topic, [])
        for priority, handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    f"Event handler error on {event.topic.value}: {e}",
                    exc_info=True,
                )

    async def publish_simple(
        self,
        topic: EventTopic,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "",
    ) -> None:
        """Convenience: publish with minimal boilerplate."""
        await self.publish(Event(
            topic=topic,
            payload=payload or {},
            source=source,
        ))

    def get_replay(self, topic: Optional[EventTopic] = None, limit: int = 50) -> List[Event]:
        """Get recent events for a topic (or all topics)."""
        if topic:
            events = [e for e in self._replay_buffer if e.topic == topic]
        else:
            events = list(self._replay_buffer)
        return events[-limit:]

    async def wait_for(self, topic: EventTopic, timeout: float = 30.0) -> Optional[Event]:
        """Wait for the next event on a topic (one-shot)."""
        future: asyncio.Future[Event] = asyncio.get_event_loop().create_future()

        async def _handler(event: Event):
            if not future.done():
                future.set_result(event)

        self.subscribe(topic, _handler)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self.unsubscribe(topic, _handler)


# ── Global singleton ──────────────────────────────────────────────

_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus

