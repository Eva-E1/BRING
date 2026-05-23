"""
BRING v2 — Core shared infrastructure.
"""
from .models import EntityNode, LayeredProfile, EntityType, WorldFrame, Relationship
from .store import UnifiedEntityStore, NameIndex
from .event_bus import EventBus, Event, EventTopic, get_event_bus
from .utils import atomic_write_json, atomic_read_json, safe_names, deterministic_hash
"""World Core - Lazy imports to avoid circular dependency issues."""
from typing import TYPE_CHECKING

# Lazy imports to avoid circular import problems between:
# world_builder <-> world_core <-> world_director
if TYPE_CHECKING:
    from .llm_queue import GlobalLLMQueue
    from .memory import WorldMemory, WorldMemoryEntry


def __getattr__(name):
    """Lazy loading of world_core modules."""
    if name == "GlobalLLMQueue":
        from .llm_queue import GlobalLLMQueue
        return GlobalLLMQueue
    elif name in ("WorldMemory", "WorldMemoryEntry"):
        from .memory import WorldMemory, WorldMemoryEntry
        return globals()[name]
    raise AttributeError(f"module 'world_core' has no attribute '{name}'")


def __dir__():
    """Return list of available attributes for tab-completion."""
    return ["GlobalLLMQueue", "WorldMemory", "WorldMemoryEntry"]


__all__ = ["GlobalLLMQueue", "WorldMemory", "WorldMemoryEntry"]
