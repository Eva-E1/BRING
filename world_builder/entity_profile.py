"""Define entity profile data structures with three layers."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time

@dataclass
class LayeredProfile:
    """L1: classification, L2: details, L3: secrets/history."""
    l1: Dict[str, Any] = field(default_factory=dict)
    l2: Dict[str, Any] = field(default_factory=dict)
    l3: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"l1": self.l1, "l2": self.l2, "l3": self.l3}

    @classmethod
    def from_dict(cls, data: dict):
        return cls(l1=data.get("l1", {}), l2=data.get("l2", {}), l3=data.get("l3", {}))


@dataclass
class EntityNode:
    uid: str               # f"{entity_type}:{name}"
    name: str
    entity_type: str
    profile: LayeredProfile
    group_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at
