from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from uuid import uuid4

from .models import StoryArc

logger = logging.getLogger(__name__)


class StoryArcManager:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.arcs: Dict[str, StoryArc] = {}
        self._load()

    def _load(self):
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                self.arcs = {k: StoryArc(**v) for k, v in data.items()}
            except Exception as e:
                logger.warning(f"Failed to load story arcs: {e}")

    def _save(self):
        data = {k: v.model_dump() for k, v in self.arcs.items()}
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(data, indent=2))

    def create_arc(self, name: str, protagonist: str, arc_type: str, phases: List[Dict]) -> StoryArc:
        arc_id = str(uuid4())
        arc = StoryArc(
            id=arc_id,
            name=name,
            protagonist=protagonist,
            arc_type=arc_type,
            phases=phases,
            current_phase=0,
            timeline=[],
        )
        self.arcs[arc_id] = arc
        self._save()
        return arc

    def advance_phase(self, arc_id: str) -> bool:
        """Move to next phase if available. Returns True if advanced."""
        arc = self.arcs.get(arc_id)
        if not arc or arc.current_phase + 1 >= len(arc.phases):
            return False
        arc.current_phase += 1
        self._save()
        return True

    def add_event(self, arc_id: str, event_description: str, story_time: datetime):
        arc = self.arcs.get(arc_id)
        if arc:
            arc.timeline.append({"description": event_description, "timestamp": story_time.isoformat()})
            self._save()

    def get_arcs_for_character(self, character_uid: str) -> List[StoryArc]:
        return [arc for arc in self.arcs.values() if arc.protagonist == character_uid]
