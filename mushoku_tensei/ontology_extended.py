"""
Extended ontology for the Mushoku Tensei extraction pipeline.
Adds Ability, WorldRule, HistoricalEvent, Arc, Concept entities
and corresponding edge types on top of the base memory ontology.
(Useful as a reference – the extraction prompt already includes
these types, but this file keeps their data models consistent.)
"""

from datetime import datetime
from typing import Optional, List, Union

from pydantic import BaseModel, Field

from memory.ontology import (
    Character,
    Location,
    Item,
    Event,
    Faction,
    ENTITY_TYPES as BASE_ENTITY_TYPES,
)

# ── New entity types ────────────────────────────────────────────

class Ability(BaseModel):
    """Skills, magic, techniques."""
    category: Optional[str] = None   # attack, healing, summoning, barrier, unique ...
    description: Optional[str] = None
    prerequisites: Optional[str] = None


class WorldRule(BaseModel):
    """World‑building rules, laws of magic, racial traits, etc."""
    category: Optional[str] = None   # magic_system, racial_trait, historical_law, geography
    description: Optional[str] = None


class HistoricalEvent(BaseModel):
    """Large‑scale past events (e.g. Laplace War)."""
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    description: Optional[str] = None


class Arc(BaseModel):
    """Story arc / volume identification."""
    volume: Optional[int] = None
    description: Optional[str] = None


class Concept(BaseModel):
    """Abstract themes like 'reincarnation', 'destiny', 'family'."""
    description: Optional[str] = None


# ── New edge types ─────────────────────────────────────────────

class HasAbility(BaseModel):
    source: Character
    target: Ability
    acquired_at: Optional[datetime] = None
    proficiency: Optional[str] = None


class Governs(BaseModel):
    source: WorldRule
    target: Union[Ability, Event, Faction, Character, Location]
    description: Optional[str] = None


class PartOfArc(BaseModel):
    source: Union[Event, HistoricalEvent, Character]
    target: Arc
    role: Optional[str] = None


class Causes(BaseModel):
    source: Union[Event, HistoricalEvent, Ability]
    target: Union[Event, HistoricalEvent]
    description: Optional[str] = None


class InvolvesConcept(BaseModel):
    source: Union[Event, Arc, Character, WorldRule, Ability]
    target: Concept
    relevance: Optional[str] = None


# ── Merged entity type registry (for reference) ───────────────
ENTITY_TYPES_EXTENDED = {
    **BASE_ENTITY_TYPES,
    "Ability": Ability,
    "WorldRule": WorldRule,
    "HistoricalEvent": HistoricalEvent,
    "Arc": Arc,
    "Concept": Concept,
}
