"""BRING Memory & Graph - public API."""

from .config import MemorySettings, get_settings
from .ontology import (
    Character,
    Event,
    Faction,
    Item,
    Knows,
    LocatedAt,
    Location,
    MemberOf,
    OccurredAt,
    ParticipatedIn,
    Possesses,
)

__all__ = [
    "ActorContext",
    "Character",
    "Chronicler",
    "Director",
    "Event",
    "Faction",
    "Item",
    "Knows",
    "LocatedAt",
    "Location",
    "MemberOf",
    "MemoryEngine",
    "MemorySettings",
    "OccurredAt",
    "ParticipatedIn",
    "Possesses",
    "get_settings",
]


def __getattr__(name: str):
    if name == "MemoryEngine":
        from .engine import MemoryEngine

        return MemoryEngine
    if name == "Chronicler":
        from .chronicler import Chronicler

        return Chronicler
    if name == "Director":
        from .director import Director

        return Director
    if name == "ActorContext":
        from .actor import ActorContext

        return ActorContext
    raise AttributeError(f"module 'memory' has no attribute {name!r}")
