"""
BRING v2 — Entity profile re-exports from world_core.
No more duplication. All model logic lives in world_core.models.
"""
from world_core.models import EntityNode, LayeredProfile, EntityType

__all__ = ["EntityNode", "LayeredProfile", "EntityType"]

