"""Data models for the director."""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from enum import Enum


class TaskPriority(Enum):
    CRITICAL = 0      # must execute immediately
    HIGH = 1
    NORMAL = 2
    LOW = 3


class DirectorTask(BaseModel):
    """A task to be executed by an agent."""
    id: str
    type: Literal["expand_branch", "add_entity", "edit_entity", "generate_event", "advance_arc", "evolve_world", "llm_text", "llm_json"]
    priority: TaskPriority
    data: Dict[str, Any]
    created_at: datetime
    scheduled_time: Optional[datetime] = None


class StoryArc(BaseModel):
    """A character or faction arc with beats."""
    id: str
    name: str
    protagonist: str  # character or faction UID
    arc_type: Literal["hero", "villain", "redemption", "tragedy", "coming_of_age"]
    current_phase: int = 0
    phases: List[Dict[str, Any]]  # list of {description, required_beats, completed}
    timeline: List[Dict[str, Any]]  # events that happened
