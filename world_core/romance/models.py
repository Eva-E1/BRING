"""Data models for the romantic relationships system."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class RomanceStatus(Enum):
    """Current status of a romantic relationship."""
    STRANGER = "stranger"
    ACQUAINTANCE = "acquaintance"
    FRIEND = "friend"
    CLOSE_FRIEND = "close_friend"
    CRUSH = "crush"
    DATING = "dating"
    ENGAGED = "engaged"
    MARRIED = "married"
    ESTRANGED = "estranged"
    RIVAL = "rival"


class RomanceProgression(Enum):
    """Stage of romantic progression."""
    ATTRACTION = "attraction"
    CONFESSION = "confession"
    DATE = "date"
    KISS = "kiss"
    RELATIONSHIP = "relationship"
    PROPOSAL = "proposal"
    MARRIAGE = "marriage"
    BREAKUP = "breakup"
    JEALOUSY = "jealousy"


@dataclass
class RelationshipMemory:
    """Stored per romantic pair."""
    pair_id: str
    status: RomanceStatus
    progression_stage: RomanceProgression
    compatibility: float
    affection: float
    history: List[Dict] = field(default_factory=list)
    last_interaction: datetime = field(default_factory=datetime.now)
    notes: Optional[str] = None
    gifts_given: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.compatibility = max(0.0, min(1.0, self.compatibility))
        self.affection = max(0.0, min(1.0, self.affection))

    def to_dict(self) -> Dict:
        return {
            "pair_id": self.pair_id,
            "status": self.status.value,
            "progression_stage": self.progression_stage.value,
            "compatibility": self.compatibility,
            "affection": self.affection,
            "history": self.history,
            "last_interaction": self.last_interaction.isoformat() if self.last_interaction else None,
            "notes": self.notes,
            "gifts_given": self.gifts_given,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> RelationshipMemory:
        return cls(
            pair_id=data["pair_id"],
            status=RomanceStatus(data.get("status", "stranger")),
            progression_stage=RomanceProgression(data.get("progression_stage", "attraction")),
            compatibility=data.get("compatibility", 0.5),
            affection=data.get("affection", 0.3),
            history=data.get("history", []),
            last_interaction=datetime.fromisoformat(data["last_interaction"]) if data.get("last_interaction") else datetime.now(),
            notes=data.get("notes"),
            gifts_given=data.get("gifts_given", []),
        )


@dataclass
class RomanceParams:
    """Input to the probability engine for romantic actions."""
    actor: str
    target: str
    action: RomanceProgression
    location: str
    extra: Optional[Dict] = None


@dataclass
class RomanceEvent:
    """A romantic event that occurred."""
    event_type: RomanceProgression
    actor: str
    target: str
    success: bool
    timestamp: datetime
    affection_change: float
    narrative: str
    location: str

    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type.value,
            "actor": self.actor,
            "target": self.target,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "affection_change": self.affection_change,
            "narrative": self.narrative,
            "location": self.location,
        }
