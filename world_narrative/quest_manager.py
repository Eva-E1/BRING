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
        # Callback for probability checking (set by NarrativeContext)
        self.prob_check_callback = None

    def _load(self):
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            for qdict in data.values():
                self.quests[qdict["id"]] = Quest(**qdict)

    def _save(self):
        data = {qid: q.__dict__ for qid, q in self.quests.items()}
        self.storage_path.write_text(json.dumps(data, indent=2))

    def get_quest(self, quest_id: str) -> Optional[Quest]:
        """Get a quest by ID."""
        return self.quests.get(quest_id)

    def get_all_quests(self) -> List[Quest]:
        """Get all quests."""
        return list(self.quests.values())

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

    def check_chance_objective(self, quest_id: str, profile: str, actor: str, target: Optional[str] = None) -> bool:
        """
        Check if a probability-based objective is completed.
        Returns True if the objective was just completed.
        """
        quest = self.quests.get(quest_id)
        if not quest:
            return False

        for idx, obj in enumerate(quest.objectives):
            if obj.get("type") == "chance" and obj.get("profile") == profile:
                if obj.get("target_npc") == target and not obj.get("completed", False):
                    # Use the callback to check probability
                    if self.prob_check_callback and self.prob_check_callback(profile, actor, target):
                        self.update_objective(quest_id, idx, True)
                        return True
        return False

    def get_active_chance_objectives(self) -> List[Dict[str, Any]]:
        """Get all active chance-based objectives across all quests."""
        objectives = []
        for quest in self.quests.values():
            if quest.status != "active":
                continue
            for idx, obj in enumerate(quest.objectives):
                if obj.get("type") == "chance" and not obj.get("completed", False):
                    objectives.append({
                        "quest_id": quest.id,
                        "quest_title": quest.title,
                        "objective_index": idx,
                        "profile": obj.get("profile"),
                        "target": obj.get("target_npc"),
                        "actor": obj.get("actor"),
                    })
        return objectives
