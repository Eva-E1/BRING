import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

@dataclass
class Quest:
    id: str
    title: str
    description: str
    giver: str
    objectives: List[Dict[str, Any]]  # e.g., {"type":"goto","target":"location_name","completed":False}
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def from_dict(cls, data: dict):
        """Create a Quest from a dict, filling missing fields with defaults."""
        return cls(
            id=data.get("id", str(uuid4())),
            title=data.get("title", "Untitled Quest"),
            description=data.get("description", ""),
            giver=data.get("giver", "Unknown"),
            objectives=data.get("objectives", []),
            status=data.get("status", "active"),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

class QuestManager:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.quests: Dict[str, Quest] = {}
        self._load()

    def _load(self):
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            for qdict in data.values():
                self.quests[qdict["id"]] = Quest(**qdict)

    def _save(self):
        data = {qid: q.__dict__ for qid, q in self.quests.items()}
        self.storage_path.write_text(json.dumps(data, indent=2))

    def add_quest(self, quest):
        if isinstance(quest, dict):
            quest = Quest.from_dict(quest)
        self.quests[quest.id] = quest
        self._save()

    def update_objective(self, quest_id: str, objective_index: int, completed: bool):
        q = self.quests.get(quest_id)
        if q and 0 <= objective_index < len(q.objectives):
            q.objectives[objective_index]["completed"] = completed
            self._save()
            # if all completed, mark quest as done
            if all(obj.get("completed", False) for obj in q.objectives):
                q.status = "completed"
                self._save()
