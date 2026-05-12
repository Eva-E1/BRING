from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


class StoryContext(BaseModel):
    """All context needed for narrative generation."""
    world_name: str
    current_time: datetime
    location: str
    active_character: Optional[str]
    user_role: str
    recent_timeline: List[str]
    world_rules: List[str]
    nearby_npcs: List[str]
    available_items: List[str]
    active_quests: List[Dict[str, Any]]
    director_plan: Optional[str]


class NarratorOutput(BaseModel):
    """Output from narrator agent."""
    narrative: str
    entities_mentioned: List[str] = []
    suggested_actions: List[str] = []


class NPCDialogue(BaseModel):
    """Output from NPC agent for dialogue."""
    speaker: str
    line: str
    emotion: Optional[str] = None
    suggested_effects: List[Dict[str, Any]] = []


class SceneTransition(BaseModel):
    """Output from scene agent for moving between locations."""
    new_location: str
    narrative: str
    time_advance_minutes: int = 0
