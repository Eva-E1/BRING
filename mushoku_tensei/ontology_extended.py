"""
Extended ontology for the Mushoku Tensei extraction pipeline.

The goal is to keep the graph expressive enough for timeline-aware retrieval,
character role-play, and world-rule reasoning without overcomplicating the
memory layer. These models intentionally favor optional, text-grounded fields.
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


class Memory(BaseModel):
    """Past-life recollections and remembered scenes."""
    content: str
    past_life_reference: Optional[str] = None
    emotion: Optional[str] = None


class Skill(BaseModel):
    """Named proficiencies or training milestones."""
    level: Optional[str] = None
    system: Optional[str] = None
    description: Optional[str] = None


class MagicSystem(BaseModel):
    """Explicit rules or sub-systems of magic."""
    requires_incantation: Optional[bool] = None
    complexity: Optional[str] = None
    description: Optional[str] = None


class Job(BaseModel):
    """Occupations and service roles."""
    employer: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class Emotion(BaseModel):
    """Time-bound emotional states that matter for role-play."""
    type: str
    intensity: Optional[int] = Field(default=None, ge=1, le=10)
    cause: Optional[str] = None


class CalendarEra(BaseModel):
    """Named calendar systems such as the Armored Dragon Calendar."""
    shorthand: Optional[str] = None
    year_zero_offset: Optional[int] = None
    description: Optional[str] = None


class CharacterAge(BaseModel):
    """Canonical character age snapshots for point-in-time queries."""
    age_years: int = Field(ge=0, le=150)
    character_name: Optional[str] = None
    description: Optional[str] = None


class TimelineEvent(BaseModel):
    """Major world or character timeline anchors."""
    era: Optional[str] = None
    year: Optional[int] = None
    description: Optional[str] = None


class NarrativeArc(BaseModel):
    """Narrative grouping richer than a plain volume arc."""
    phase: Optional[str] = None
    volume: Optional[int] = None
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


class Teaches(BaseModel):
    source: Character
    target: Character
    subject: Optional[str] = None


class Trains(BaseModel):
    source: Character
    target: Character
    style: Optional[str] = None


class Protects(BaseModel):
    source: Character
    target: Character


class Bullys(BaseModel):
    source: Character
    target: Character


class Serves(BaseModel):
    source: Character
    target: Character
    role: Optional[str] = None


class Betrays(BaseModel):
    source: Character
    target: Character
    description: Optional[str] = None


class Regrets(BaseModel):
    source: Character
    target: Union[Event, HistoricalEvent, Concept, Memory]
    intensity: Optional[int] = Field(default=None, ge=1, le=10)


class Fears(BaseModel):
    source: Character
    target: Union[Character, Event, Concept, Ability, WorldRule]
    intensity: Optional[int] = Field(default=None, ge=1, le=10)


class FatherOf(BaseModel):
    source: Character
    target: Character


class Trusts(BaseModel):
    source: Character
    target: Character
    trust_level: Optional[int] = Field(default=None, ge=1, le=10)


# ── Merged entity type registry (for reference) ───────────────
ENTITY_TYPES_EXTENDED = {
    **BASE_ENTITY_TYPES,
    "Ability": Ability,
    "WorldRule": WorldRule,
    "HistoricalEvent": HistoricalEvent,
    "Arc": Arc,
    "Concept": Concept,
    "Memory": Memory,
    "Skill": Skill,
    "MagicSystem": MagicSystem,
    "Job": Job,
    "Emotion": Emotion,
    "CalendarEra": CalendarEra,
    "CharacterAge": CharacterAge,
    "TimelineEvent": TimelineEvent,
    "NarrativeArc": NarrativeArc,
}
