"""
BRING v2 — Unified data models.
All shared data structures live here. No more duplication across packages.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# ── Entity Type Enum ──────────────────────────────────────────────

class EntityType(str, Enum):
    CHARACTER = "Character"
    FACTION = "Faction"
    LOCATION = "Location"
    ITEM = "Item"
    EVENT = "Event"
    WORLD_RULE = "WorldRule"
    RACE = "Race"
    UNKNOWN = "Unknown"

    @classmethod
    def from_string(cls, s: str) -> "EntityType":
        try:
            return cls(s)
        except ValueError:
            return cls.UNKNOWN


# ── Layered Profile ───────────────────────────────────────────────

class LayeredProfile:
    """
    Three-layer entity profile:
      L1 — Classification (name, type, tags, relationships)
      L2 — Details (description, abilities, affiliations)
      L3 — Secrets (hidden truths, curses, true motivations)
    """

    __slots__ = ("l1", "l2", "l3")

    def __init__(
        self,
        l1: Optional[Dict[str, Any]] = None,
        l2: Optional[Dict[str, Any]] = None,
        l3: Optional[Dict[str, Any]] = None,
    ):
        self.l1: Dict[str, Any] = l1 or {}
        self.l2: Dict[str, Any] = l2 or {}
        self.l3: Dict[str, Any] = l3 or {}

    # ── Convenience accessors ─────────────────────────────────────

    @property
    def name(self) -> str:
        return self.l1.get("name", "")

    @property
    def entity_type(self) -> str:
        return self.l1.get("type", "")

    @property
    def summary(self) -> str:
        return self.l1.get("summary", "")

    @property
    def tags(self) -> List[str]:
        return self.l1.get("tags", [])

    @property
    def relationships(self) -> List[Dict[str, Any]]:
        return self.l1.setdefault("relationships", [])

    def get_layer(self, layer: str) -> Dict[str, Any]:
        return getattr(self, layer, {})

    def get_effective_data(self, layers: Optional[List[str]] = None) -> Dict[str, Any]:
        """Merge selected layers into a single dict."""
        result: Dict[str, Any] = {}
        for layer_name in (layers or ("l1", "l2", "l3")):
            data = getattr(self, layer_name, {})
            if data:
                result[layer_name] = data
        return result

    # ── Serialization ─────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {"l1": self.l1, "l2": self.l2, "l3": self.l3}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayeredProfile":
        return cls(
            l1=data.get("l1", {}),
            l2=data.get("l2", {}),
            l3=data.get("l3", {}),
        )


# ── Entity Node ───────────────────────────────────────────────────

@dataclass
class EntityNode:
    """
    Single entity in the world graph.
    UID format: "{EntityType}:{Name}"
    """
    uid: str
    name: str
    entity_type: str
    profile: LayeredProfile
    group_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    # ── Convenience ───────────────────────────────────────────────

    @property
    def etype(self) -> EntityType:
        return EntityType.from_string(self.entity_type)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "entity_type": self.entity_type,
            "profile": self.profile.to_dict(),
            "group_id": self.group_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityNode":
        return cls(
            uid=data["uid"],
            name=data["name"],
            entity_type=data["entity_type"],
            profile=LayeredProfile.from_dict(data["profile"]),
            group_id=data.get("group_id", ""),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )


# ── Relationship ──────────────────────────────────────────────────

@dataclass
class Relationship:
    """Typed, directional relationship between two entities."""
    source_uid: str
    target_uid: str
    rel_type: str
    strength: float = 0.0
    source_layer: str = "l1"  # which layer this came from

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source_uid,
            "target": self.target_uid,
            "type": self.rel_type,
            "strength": self.strength,
            "source_layer": self.source_layer,
        }


# ── World Frame ───────────────────────────────────────────────────

@dataclass
class WorldFrame:
    """Top-level world definition."""
    world_name: str = ""
    calendar_era: Dict[str, str] = field(default_factory=dict)
    magic_system: Dict[str, str] = field(default_factory=dict)
    races: List[Dict[str, Any]] = field(default_factory=list)
    factions: List[Dict[str, Any]] = field(default_factory=list)
    characters: List[Dict[str, Any]] = field(default_factory=list)
    locations: List[Dict[str, Any]] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)
    historical_events: List[Dict[str, Any]] = field(default_factory=list)
    world_rules: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_name": self.world_name,
            "calendar_era": self.calendar_era,
            "magic_system": self.magic_system,
            "races": self.races,
            "factions": self.factions,
            "characters": self.characters,
            "locations": self.locations,
            "items": self.items,
            "historical_events": self.historical_events,
            "world_rules": self.world_rules,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldFrame":
        return cls(
            world_name=data.get("world_name", ""),
            calendar_era=data.get("calendar_era", {}),
            magic_system=data.get("magic_system", {}),
            races=data.get("races", []),
            factions=data.get("factions", []),
            characters=data.get("characters", []),
            locations=data.get("locations", []),
            items=data.get("items", []),
            historical_events=data.get("historical_events", []),
            world_rules=data.get("world_rules", []),
        )

    def get_rules_text(self) -> str:
        return "\n".join(
            f"- {r['name']}: {r['description']}" for r in self.world_rules
        )

    def get_entity_names(self) -> List[str]:
        """Collect all entity names from the frame for reference."""
        names = []
        for key in (
            "races", "factions", "characters",
            "locations", "items", "historical_events", "world_rules",
        ):
            for item in self.__dict__.get(key, []):
                if isinstance(item, dict):
                    names.append(item.get("name", ""))
                else:
                    names.append(str(item))
        return names

