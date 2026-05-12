"""Core data structures."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class LayeredProfile:
    l1: Dict[str, Any] = field(default_factory=dict)
    l2: Dict[str, Any] = field(default_factory=dict)
    l3: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            l1=data.get("l1", {}),
            l2=data.get("l2", {}),
            l3=data.get("l3", {}),
        )

    def get_layer(self, layer: str) -> dict:
        return getattr(self, layer, {})

    def get_effective_data(self, layers: List[str]) -> dict:
        """Merge the requested layers into a single dict (later layers override)."""
        merged = {}
        for lvl in layers:
            merged.update(self.get_layer(lvl))
        return merged

@dataclass
class Entity:
    uid: str
    name: str
    entity_type: str
    profile: LayeredProfile
    group_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
