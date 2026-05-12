"""Manages villain agendas, memories, and autonomous actions."""
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
class VillainMemory:
    """A single memory entry for a villain."""
    timestamp: str
    description: str
    involved_entities: List[str]
    success: bool
    consequence: str = ""


@dataclass
class VillainAgenda:
    """A villain's long-term plan."""
    name: str
    description: str
    current_phase: str  # "plotting", "preparing", "executing", "climax"
    progress_clock: int = 0
    target_clock: int = 10
    memories: List[VillainMemory] = field(default_factory=list)
    minions: List[str] = field(default_factory=list)  # NPC minions
    secret_base: Optional[str] = None
    ultimate_goal: str = ""


class VillainManager:
    def __init__(self, gm: GraphManager, chronicler: Chronicler, state_path: Path):
        self.gm = gm
        self.chronicler = chronicler
        self.state_path = state_path
        self._villains: Dict[str, VillainAgenda] = {}
        self._load()

    def _load(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                for name, d in data.items():
                    memories = [VillainMemory(**m) for m in d.get("memories", [])]
                    self._villains[name] = VillainAgenda(
                        name=name,
                        description=d["description"],
                        current_phase=d["current_phase"],
                        progress_clock=d["progress_clock"],
                        target_clock=d["target_clock"],
                        memories=memories,
                        minions=d.get("minions", []),
                        secret_base=d.get("secret_base"),
                        ultimate_goal=d.get("ultimate_goal", ""),
                    )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load villain state: {e}. Creating defaults.")
                self._create_default_villains()
        else:
            self._create_default_villains()

    def _save(self):
        data = {}
        for name, v in self._villains.items():
            data[name] = {
                "description": v.description,
                "current_phase": v.current_phase,
                "progress_clock": v.progress_clock,
                "target_clock": v.target_clock,
                "memories": [m.__dict__ for m in v.memories],
                "minions": v.minions,
                "secret_base": v.secret_base,
                "ultimate_goal": v.ultimate_goal,
            }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=2))

    def _create_default_villains(self):
        """Generate initial villains from the world frame or create placeholders."""
        # Scan the graph for Faction nodes that might be villains
        villain_candidates = []
        try:
            for entity in self.gm.store.entities:
                if entity.entity_type == "Faction":
                    l2 = entity.profile.l2 or {}
                    if l2.get("alignment") == "evil" or l2.get("is_villain"):
                        villain_candidates.append(entity)
        except Exception as e:
            logger.debug(f"Could not scan for villains: {e}")

        if not villain_candidates:
            # Create a generic villain if none found
            self._villains["The Shadow"] = VillainAgenda(
                name="The Shadow",
                description="A mysterious entity seeking to plunge the world into darkness.",
                current_phase="plotting",
                progress_clock=0,
                target_clock=8,
                ultimate_goal="Extinguish all light sources.",
            )
        else:
            # Use discovered factions as villains
            for entity in villain_candidates:
                self._villains[entity.name] = VillainAgenda(
                    name=entity.name,
                    description=entity.profile.l1.get("summary", "A mysterious force."),
                    current_phase="plotting",
                    progress_clock=0,
                    target_clock=10,
                    ultimate_goal=entity.profile.l2.get("goal", "Unknown objective."),
                )

        self._save()

    async def tick(self, current_time: datetime) -> List[Dict[str, Any]]:
        """Advance all villain agendas and return any events that should be triggered."""
        events = []
        for name, villain in self._villains.items():
            # Increment progress clock based on phase
            increment = 0
            if villain.current_phase == "plotting":
                increment = random.randint(1, 2)
            elif villain.current_phase == "preparing":
                increment = random.randint(1, 3)
            elif villain.current_phase == "executing":
                increment = random.randint(2, 4)
            elif villain.current_phase == "climax":
                increment = random.randint(1, 5)

            villain.progress_clock += increment

            # Check if progress reaches target
            if villain.progress_clock >= villain.target_clock:
                # Phase transition
                phase_transition = self._advance_phase(villain)
                if phase_transition:
                    events.append(phase_transition)

            # Random chance to generate a minor villain event (20% per tick)
            if random.random() < 0.2:
                event = await self._generate_villain_event(villain, current_time)
                if event:
                    events.append(event)

            # Record memory of this tick
            memory = VillainMemory(
                timestamp=current_time.isoformat(),
                description=f"Advanced {villain.current_phase} phase",
                involved_entities=[villain.name] + villain.minions,
                success=True,
                consequence=f"Progress: {villain.progress_clock}/{villain.target_clock}",
            )
            villain.memories.append(memory)
            # Keep only last 50 memories per villain
            if len(villain.memories) > 50:
                villain.memories = villain.memories[-50:]

        self._save()
        return events

    def _advance_phase(self, villain: VillainAgenda) -> Optional[Dict[str, Any]]:
        """Move the villain to the next phase and return a transition event."""
        phases = ["plotting", "preparing", "executing", "climax"]
        if villain.current_phase == "climax":
            # Villain might be defeated or reset
            villain.progress_clock = 0
            return None

        current_idx = phases.index(villain.current_phase)
        villain.current_phase = phases[current_idx + 1]
        villain.progress_clock = 0
        villain.target_clock = int(villain.target_clock * 1.2)  # each phase takes longer

        return {
            "type": "villain_phase_transition",
            "villain": villain.name,
            "new_phase": villain.current_phase,
            "description": f"{villain.name} has entered the {villain.current_phase} phase.",
            "severity": 0.6,
            "involved_entities": [villain.name] + villain.minions,
        }

    async def _generate_villain_event(self, villain: VillainAgenda, current_time: datetime) -> Optional[Dict[str, Any]]:
        """Generate a random villain event (minor sabotage, rumour, etc.)."""
        event_types = ["sabotage", "rumour", "minion_attack", "theft", "kidnapping", "spy_infiltration"]
        etype = random.choice(event_types)
        target_entity = None

        # Pick a random character or location as target
        try:
            all_chars = list(self.gm.store.entities)
            char_names = [e.name for e in all_chars if e.entity_type == "Character"]
            if char_names:
                target_entity = random.choice(char_names)
        except Exception:
            pass

        # Log the event
        await self.chronicler.log_event(
            f"{villain.name} is planning: {etype}",
            current_time,
            group="villain"
        )

        return {
            "type": "villain_event",
            "villain": villain.name,
            "event_type": etype,
            "description": f"{villain.name} {etype} involving {target_entity or 'unknown'}.",
            "severity": random.uniform(0.3, 0.6),
            "involved_entities": [villain.name] + ([target_entity] if target_entity else []),
        }

    async def get_status(self) -> Dict[str, Any]:
        return {name: {
            "phase": v.current_phase,
            "progress": f"{v.progress_clock}/{v.target_clock}",
            "memories_count": len(v.memories),
            "minions": v.minions,
            "ultimate_goal": v.ultimate_goal,
        } for name, v in self._villains.items()}

    def get_villain(self, name: str) -> Optional[VillainAgenda]:
        """Get a specific villain by name."""
        return self._villains.get(name)

    def list_villains(self) -> List[str]:
        """List all villain names."""
        return list(self._villains.keys())
