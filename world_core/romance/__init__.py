"""Romantic Relationships System for World Engine.

This module provides a deterministic, probability-driven romantic relationship
system that integrates with the existing world engine infrastructure.

Main Components:
- RomanceEngine: Core engine for managing romantic relationships
- RelationshipMemory: Data model for storing relationship state
- RomanceStatus: Enum for relationship status levels
- RomanceProgression: Enum for relationship progression stages

Usage:
    from world_core.romance import RomanceEngine, RomanceStatus

    engine = RomanceEngine(prob_engine, world_memory, gm, npc_mgr, director)
    success, narrative, affection = await engine.attempt_confession(actor, target, location)
"""

from .engine import RomanceEngine
from .models import (
    RomanceEvent,
    RomanceParams,
    RomanceProgression,
    RomanceStatus,
    RelationshipMemory,
)
from .profiles import (
    ROMANCE_ATTRACTION,
    ROMANCE_BREAKUP,
    ROMANCE_CONFESSION,
    ROMANCE_DATE,
    ROMANCE_KISS,
    ROMANCE_PROPOSAL,
    get_romance_profile,
)

__all__ = [
    # Engine
    "RomanceEngine",
    # Models
    "RomanceEvent",
    "RomanceParams",
    "RomanceProgression",
    "RomanceStatus",
    "RelationshipMemory",
    # Profiles
    "ROMANCE_ATTRACTION",
    "ROMANCE_BREAKUP",
    "ROMANCE_CONFESSION",
    "ROMANCE_DATE",
    "ROMANCE_KISS",
    "ROMANCE_PROPOSAL",
    "get_romance_profile",
]
