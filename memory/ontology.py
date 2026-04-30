"""BRING ontology – Pydantic models used by Graphiti and the custom extraction pipeline."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ════════════════════════════════════════════════════════
#  Entities
# ════════════════════════════════════════════════════════

class Character(BaseModel):
    alias: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    faction: Optional[str] = None


class Location(BaseModel):
    type: Optional[str] = None
    description: Optional[str] = None
    region: Optional[str] = None


class Item(BaseModel):
    type: Optional[str] = None
    description: Optional[str] = None


class Event(BaseModel):
    description: Optional[str] = None
    event_type: Optional[str] = None  # battle, discovery, betrayal, ...


class Faction(BaseModel):
    description: Optional[str] = None


# ════════════════════════════════════════════════════════
#  Edges (relationships)
# ════════════════════════════════════════════════════════

class LocatedAt(BaseModel):
    source: Character | Item
    target: Location
    since: Optional[datetime] = None
    circumstance: Optional[str] = None


class Knows(BaseModel):
    source: Character
    target: Character
    relationship: Optional[str] = None
    trust_level: Optional[int] = Field(None, ge=1, le=10)


class Possesses(BaseModel):
    source: Character
    target: Item
    acquired_at: Optional[datetime] = None


class ParticipatedIn(BaseModel):
    source: Character
    target: Event
    role: Optional[str] = None
    outcome: Optional[str] = None


class MemberOf(BaseModel):
    source: Character
    target: Faction
    joined_at: Optional[datetime] = None
    rank: Optional[str] = None


class OccurredAt(BaseModel):
    source: Event
    target: Location


# ════════════════════════════════════════════════════════
#  Entity type registry (for Graphiti)
# ════════════════════════════════════════════════════════

ENTITY_TYPES = {
    "Character": Character,
    "Location": Location,
    "Item": Item,
    "Event": Event,
    "Faction": Faction,
}

# Edge type map: (source_type, target_type) -> list of possible edge models
EDGE_TYPE_MAP = {
    ("Character", "Location"): [LocatedAt],
    ("Item", "Location"): [LocatedAt],
    ("Character", "Character"): [Knows],
    ("Character", "Item"): [Possesses],
    ("Character", "Event"): [ParticipatedIn],
    ("Character", "Faction"): [MemberOf],
    ("Event", "Location"): [OccurredAt],
}
