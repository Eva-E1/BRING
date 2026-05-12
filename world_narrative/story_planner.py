"""Plans story arcs, chapters, and scheduled story beats."""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from world_builder.graph_manager import GraphManager
from world_narrative.chronicler import Chronicler

logger = logging.getLogger(__name__)


@dataclass
class Chapter:
    """A story chapter containing multiple beats."""
    id: str
    title: str
    summary: str
    start_time: datetime
    end_time: Optional[datetime] = None
    completed: bool = False
    beats: List[str] = field(default_factory=list)  # IDs of story beats in this chapter


@dataclass
class StoryBeat:
    """A story beat within a chapter."""
    id: str
    chapter_id: str
    type: str  # "inciting_incident", "revelation", "setback", "victory", "cliffhanger"
    description: str
    scheduled_time: Optional[datetime] = None
    triggered: bool = False
    involved_entities: List[str] = field(default_factory=list)


class StoryPlanner:
    def __init__(self, gm: GraphManager, chronicler: Chronicler, state_path: Path):
        self.gm = gm
        self.chronicler = chronicler
        self.state_path = state_path
        self.chapters: Dict[str, Chapter] = {}
        self.beats: Dict[str, StoryBeat] = {}
        self.current_chapter_id: Optional[str] = None
        self._load()
        if not self.chapters:
            self._create_initial_plan()

    def _load(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.chapters = {
                    k: Chapter(
                        id=k,
                        title=v["title"],
                        summary=v["summary"],
                        start_time=datetime.fromisoformat(v["start_time"]),
                        end_time=datetime.fromisoformat(v["end_time"]) if v.get("end_time") else None,
                        completed=v.get("completed", False),
                        beats=v.get("beats", []),
                    )
                    for k, v in data.get("chapters", {}).items()
                }
                self.beats = {
                    k: StoryBeat(
                        id=k,
                        chapter_id=v["chapter_id"],
                        type=v["type"],
                        description=v["description"],
                        scheduled_time=datetime.fromisoformat(v["scheduled_time"]) if v.get("scheduled_time") else None,
                        triggered=v.get("triggered", False),
                        involved_entities=v.get("involved_entities", []),
                    )
                    for k, v in data.get("beats", {}).items()
                }
                self.current_chapter_id = data.get("current_chapter_id")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load story plan: {e}. Creating new plan.")
                self.chapters = {}
                self.beats = {}
                self.current_chapter_id = None

    def _save(self):
        data = {
            "chapters": {
                k: {
                    "title": v.title,
                    "summary": v.summary,
                    "start_time": v.start_time.isoformat(),
                    "end_time": v.end_time.isoformat() if v.end_time else None,
                    "completed": v.completed,
                    "beats": v.beats,
                }
                for k, v in self.chapters.items()
            },
            "beats": {
                k: {
                    "chapter_id": v.chapter_id,
                    "type": v.type,
                    "description": v.description,
                    "scheduled_time": v.scheduled_time.isoformat() if v.scheduled_time else None,
                    "triggered": v.triggered,
                    "involved_entities": v.involved_entities,
                }
                for k, v in self.beats.items()
            },
            "current_chapter_id": self.current_chapter_id,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=2))

    def _create_initial_plan(self):
        """Create a basic story arc with three chapters."""
        now = datetime.now()
        chapter1 = Chapter(
            id="ch1",
            title="The Awakening",
            summary="The protagonist discovers the central conflict.",
            start_time=now,
        )
        chapter2 = Chapter(
            id="ch2",
            title="Trials and Tribulations",
            summary="The hero faces challenges and learns about the villains.",
            start_time=now + timedelta(days=3),
        )
        chapter3 = Chapter(
            id="ch3",
            title="Climax",
            summary="Final confrontation and resolution.",
            start_time=now + timedelta(days=7),
        )
        self.chapters = {chapter1.id: chapter1, chapter2.id: chapter2, chapter3.id: chapter3}
        self.current_chapter_id = "ch1"
        self._generate_beats_for_chapter("ch1")
        self._generate_beats_for_chapter("ch2")
        self._generate_beats_for_chapter("ch3")
        self._save()

    def _generate_beats_for_chapter(self, chapter_id: str):
        """Generate a set of story beats for a given chapter."""
        chapter = self.chapters[chapter_id]
        beat_templates = {
            "inciting_incident": "A surprising event pushes the story forward.",
            "revelation": "New information changes the protagonist's understanding.",
            "setback": "The heroes suffer a defeat or loss.",
            "victory": "A small triumph that builds hope.",
            "cliffhanger": "The chapter ends with a tense moment.",
        }
        # Use the chapter start time as base, spread beats every 12-24 hours
        base = chapter.start_time
        for i, (btype, desc) in enumerate(beat_templates.items()):
            beat_time = base + timedelta(hours=12 * (i + 1))
            beat_id = f"{chapter_id}_{btype}"
            self.beats[beat_id] = StoryBeat(
                id=beat_id,
                chapter_id=chapter_id,
                type=btype,
                description=desc,
                scheduled_time=beat_time,
            )
            chapter.beats.append(beat_id)

    async def should_generate_beat(self, current_time: datetime) -> bool:
        """Return True if a scheduled beat is due and not yet triggered."""
        pending = [
            b for b in self.beats.values()
            if not b.triggered and b.scheduled_time and b.scheduled_time <= current_time
        ]
        return len(pending) > 0

    async def generate_next_beat(self, current_time: datetime) -> Optional[Dict[str, Any]]:
        """Trigger the next pending story beat and return its data."""
        pending = sorted(
            [
                b for b in self.beats.values()
                if not b.triggered and b.scheduled_time and b.scheduled_time <= current_time
            ],
            key=lambda b: b.scheduled_time
        )
        if not pending:
            return None
        beat = pending[0]
        beat.triggered = True
        self._save()
        return {
            "id": beat.id,
            "type": beat.type,
            "description": beat.description,
            "involved_entities": beat.involved_entities,
            "category": "story_beat",
        }

    async def record_beat_completed(self, beat_id: str, current_time: datetime):
        """Mark a beat as completed and potentially advance the chapter."""
        beat = self.beats.get(beat_id)
        if not beat:
            return
        # If all beats in current chapter are triggered, consider chapter completed
        chapter = self.chapters.get(beat.chapter_id)
        if chapter and all(self.beats[b].triggered for b in chapter.beats):
            chapter.completed = True
            chapter.end_time = current_time
            # Move to next chapter if exists
            chapter_ids = list(self.chapters.keys())
            idx = chapter_ids.index(beat.chapter_id)
            if idx + 1 < len(chapter_ids):
                self.current_chapter_id = chapter_ids[idx + 1]
        self._save()

    async def get_pending_beats(self, current_time: datetime) -> List[Dict[str, Any]]:
        """Return beats that are due but not yet triggered."""
        return [
            {
                "id": b.id,
                "type": b.type,
                "description": b.description,
                "involved_entities": b.involved_entities,
            }
            for b in self.beats.values()
            if not b.triggered and b.scheduled_time and b.scheduled_time <= current_time
        ]

    async def mark_beat_done(self, beat_id: str):
        """Mark a beat as done (alias for triggered)."""
        beat = self.beats.get(beat_id)
        if beat:
            beat.triggered = True
            self._save()

    async def get_plan_summary(self) -> Dict[str, Any]:
        return {
            "current_chapter": self.current_chapter_id,
            "chapters": {
                cid: {
                    "title": ch.title,
                    "summary": ch.summary,
                    "completed": ch.completed,
                    "beats_done": sum(1 for b in self.beats.values() if b.chapter_id == cid and b.triggered),
                    "beats_total": len(ch.beats),
                }
                for cid, ch in self.chapters.items()
            },
            "pending_beats": sum(1 for b in self.beats.values() if not b.triggered),
        }
