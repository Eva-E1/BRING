/home/ali/Lab/world_engine/roleplay_engine.py
```

from __future__ import annotations
import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from world_builder.graph_manager import GraphManager
from world_core.llm_queue import GlobalLLMQueue
from world_explorer.store import GraphStore
from world_narrative.memory_optimized import OptimizedMemoryStore
from world_narrative.chronicler import Chronicler
from world_narrative.director import Director
from world_narrative.story_engine import StoryEngine
from world_narrative.quest_manager import QuestManager
from world_narrative.world_clock import WorldClock
from world_narrative.validation import WorldValidator

from .memory_manager import MemoryManager
from .agents.narrator_agent import NarratorAgent
from .agents.npc_agent import NPCAgent
from .agents.scene_agent import SceneAgent
from .agents.director_agent import DirectorAgent
from .start_resolver import StartResolver

logger = logging.getLogger(__name__)


class RoleplayEngine:
    """
    Advanced roleplay system with third‑person narrative, memory, and agents.
    The LLM never speaks or acts for the user's character.
    """

    def __init__(
        self,
        db_path: Path,
        world_frame: dict,
        llm_queue: GlobalLLMQueue,
        gm: GraphManager,
        npc_mgr: OptimizedMemoryStore,
        chronicler: Chronicler,
        director: Director,
        story_engine: StoryEngine,
        validator: WorldValidator,
        quest_mgr: QuestManager,
        clock: WorldClock,
        graph_store: GraphStore,
    ):
        self.db_path = db_path
        self.world_frame = world_frame
        self.llm_queue = llm_queue
        self.gm = gm
        self.npc_mgr = npc_mgr
        self.chronicler = chronicler
        self.director = director
        self.story_engine = story_engine
        self.validator = validator
        self.quest_mgr = quest_mgr
        self.clock = clock
        self.graph_store = graph_store

        # Agents - pass the queue with HIGH priority for user-facing calls
        self.narrator = NarratorAgent(llm_queue)
        self.npc_agent = NPCAgent(llm_queue)
        self.scene_agent = SceneAgent(llm_queue)
        self.director_agent = DirectorAgent(llm_queue)

        # Memory manager for conversation
        self.memory = MemoryManager(db_path / "roleplay_memory.json")

        # Start resolver for parsing starting points
        self.start_resolver = StartResolver(gm, npc_mgr, director)

        # Session state
        self.active_character: Optional[str] = None
        self.current_location: str = "unknown"
        self.current_time: datetime = datetime.now()
        self.user_role: str = "protagonist"
        self.allow_auto_events: bool = True

    def set_session(
        self,
        character: Optional[str],
        location: str,
        story_time: datetime,
        role: str = "protagonist",
    ):
        self.active_character = character
        self.current_location = location
        self.current_time = story_time
        self.user_role = role

    async def _get_relevant_memories(self, context_query: str) -> List[str]:
        """Retrieve relevant world and NPC memories for the current context."""
        memories = []
        if self.active_character:
            npc_mems = await self.npc_mgr.get_relevant_memories(
                self.active_character, context_query, top_k=5
            )
            memories.extend(
                f"[Character memory] {m.get('description', m.get('fact', ''))}"
                for m in npc_mems
            )
        return memories

    async def _get_world_facts(self, query: str) -> List[str]:
        """Retrieve world facts from WorldMemory if available."""
        return []

    async def _get_nearby_npcs(self) -> List[str]:
        """Get NPCs that are in the same location as the player."""
        all_npcs = self.npc_mgr.list_all()
        nearby = [
            name
            for name, profile in all_npcs.items()
            if profile.location == self.current_location
        ]
        return nearby

    async def _get_director_plan(self) -> Optional[str]:
        """Get upcoming story beats from the director to inject."""
        plan = await self.director.story_planner.get_plan_summary()
        pending = plan.get("pending_beats", 0)
        if pending > 0:
            return f"There are {pending} upcoming story beats. The next one should happen soon."
        return None

    async def process_input(self, user_input: str) -> str:
        """Main entry point: process user action/statement, return narrative."""
        # Handle commands
        if user_input.strip().startswith("/"):
            return await self._handle_command(user_input.strip()[1:])

        # Determine if user is moving, talking, or performing action
        lower = user_input.lower()
        if any(token in lower for token in ("go", "move", "travel", "walk", "run", "head to")):
            return await self._handle_movement(user_input)
        elif any(
            token in lower
            for token in ("say", "ask", "tell", "shout", "whisper", "talk to")
        ):
            return await self._handle_dialogue(user_input)
        else:
            return await self._handle_generic_action(user_input)

    async def _handle_movement(self, user_input: str) -> str:
        """Process movement to a new location."""
        dest_match = re.search(
            r"(?:to|toward|into|for) ([a-zA-Z0-9' -]+)", user_input.lower()
        )
        if not dest_match:
            return "Where do you want to go?"

        destination = dest_match.group(1).strip()
        # Validate location existence
        loc_node = self.gm.store.get_by_name_and_type(destination, "Location")
        if not loc_node:
            return f"You don't know a place called '{destination}'."

        # Scene agent generates the journey description
        recent_events = await self.chronicler.get_timeline(
            since=self.current_time - timedelta(days=1), limit=10
        )
        recent_texts = [e["description"] for e in recent_events]
        description = await self.scene_agent.transition(
            self.current_location,
            destination,
            self.active_character or "you",
            recent_texts,
            [r["description"] for r in self.world_frame.get("world_rules", [])],
        )

        # Update state
        self.current_location = destination
        self.current_time += timedelta(minutes=10)

        # Log the movement
        await self.chronicler.log_event(
            f"{self.active_character or 'Player'} moved to {destination}",
            self.current_time,
            group="movement",
        )
        return description

    async def _handle_dialogue(self, user_input: str) -> str:
        """Process dialogue with an NPC."""
        match = re.match(
            r"(?:say to|talk to|ask|tell|shout at|whisper to) ([a-zA-Z0-9' -]+?)(?:\s+)(.+)$",
            user_input.lower(),
        )
        if not match:
            # Try simpler pattern
            match2 = re.match(r"(?:talk to|address) ([a-zA-Z0-9' -]+)", user_input.lower())
            if match2:
                npc_name = match2.group(1).strip()
                return f"To whom? Say 'tell {npc_name} Hello'."
            return "Whom are you talking to? Example: 'talk to John' or 'say to Mary Hello'."

        npc_name = match.group(1).strip()
        player_line = match.group(2).strip()
        if not player_line:
            return f"What do you want to say to {npc_name}?"

        # Verify NPC exists
        npc_node = self.gm.store.get_by_name_and_type(npc_name, "Character")
        if not npc_node:
            return f"There is no one named '{npc_name}'."

        # Verify NPC is nearby
        nearby = await self._get_nearby_npcs()
        if npc_name not in nearby:
            return f"{npc_name} is not here right now."

        # Get NPC personality
        personality = npc_node.profile.l2.get("personality", "friendly and neutral")
        relationship = "neutral"

        # Recent events
        recent = await self.chronicler.get_timeline(
            since=self.current_time - timedelta(hours=2), limit=5
        )
        recent_texts = [e["description"] for e in recent]

        # Generate NPC response
        response = await self.npc_agent.respond(
            npc_name,
            personality,
            self.active_character or "you",
            self.current_location,
            player_line,
            recent_texts,
            relationship,
        )

        # Log dialogue event
        await self.chronicler.log_event(
            f"{self.active_character or 'Player'} talked to {npc_name}: '{player_line}'",
            self.current_time,
            group="dialogue",
        )

        return f'{npc_name} says: "{response}"'

    async def _handle_generic_action(self, user_input: str) -> str:
        """Generic action (e.g., "I examine the old chest")."""
        # Build context for narrator
        context = {
            "world_name": self.world_frame["world_name"],
            "current_time": self.current_time.isoformat(),
            "location": self.current_location,
            "active_character": self.active_character,
            "user_role": self.user_role,
            "recent_timeline": [
                e["description"]
                for e in await self.chronicler.get_timeline(
                    since=self.current_time - timedelta(hours=2), limit=10
                )
            ],
            "world_rules": [
                r["description"] for r in self.world_frame.get("world_rules", [])
            ],
            "nearby_npcs": await self._get_nearby_npcs(),
            "available_items": [],
            "active_quests": [
                q.__dict__
                for q in self.quest_mgr.quests.values()
                if q.status == "active"
            ],
            "director_plan": await self._get_director_plan(),
        }

        recent_memories = await self._get_relevant_memories(user_input)
        world_facts = await self._get_world_facts(user_input)
        conversation = self.memory.get_recent(limit=5)

        narrative = await self.narrator.generate(
            context, recent_memories, world_facts, conversation
        )

        # Optionally inject story beat from director
        pending = await self.director.story_planner.get_pending_beats(self.current_time)
        if pending:
            beat = pending[0]
            narrative = await self.director_agent.inject_beat(beat["description"], narrative)
            await self.director.story_planner.mark_beat_done(beat["id"])

        # Log user action and resulting narrative
        await self.chronicler.log_event(
            f"User action: {user_input}", self.current_time, group="user_input"
        )
        self.memory.add_entry(user_input, narrative)

        # Advance time slightly
        self.current_time += timedelta(minutes=5)
        return narrative

    async def _handle_command(self, cmd: str) -> str:
        """Simple slash commands."""
        parts = cmd.split()
        verb = parts[0].lower()
        if verb == "help":
            return "Commands: /look, /inventory, /status, /quests, /time, /save, /quit"
        if verb == "look":
            loc_node = self.gm.store.get_by_name_and_type(
                self.current_location, "Location"
            )
            if loc_node:
                desc = loc_node.profile.l2.get("description", "You see nothing special.")
                return f"You look around. {desc}"
            return "You see nothing of note."
        if verb == "inventory":
            if not self.active_character:
                return "You are not controlling any character."
            state = self.npc_mgr.get(self.active_character)
            if state:
                items = list(state.inventory)
                return f"You are carrying: {', '.join(items) or 'nothing'}"
            return "No inventory found."
        if verb == "status":
            state = (
                self.npc_mgr.get(self.active_character) if self.active_character else None
            )
            if state:
                return f"Location: {state.location}\nHealth: {state.health}\nMood: {state.mood}\nGoals: {state.goals}"
            return f"Location: {self.current_location}\nNo active character."
        if verb == "quests":
            active = [q for q in self.quest_mgr.quests.values() if q.status == "active"]
            if not active:
                return "No active quests."
            return "\n".join(f"- {q.title}: {q.description}" for q in active)
        if verb == "time":
            return f"Story time: {self.current_time.isoformat()}"
        if verb == "save":
            # This is handled by CLI for full session persistence
            return "Session state saved. Use /quit to fully exit and persist."
        if verb == "quit":
            return "Goodbye!"
        return f"Unknown command: {verb}. Type /help."

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def get_session_state(self) -> dict:
        """Get the current session state for persistence."""
        return {
            "active_character": self.active_character,
            "current_location": self.current_location,
            "current_time": self.current_time.isoformat(),
            "user_role": self.user_role,
            "allow_auto_events": self.allow_auto_events,
        }

    def _session_path(self, session_id: str) -> Path:
        """Get the path for a session file."""
        return self.db_path / f"roleplay_session_{session_id}.json"

    def save_session(self, session_id: str) -> None:
        """Persist session state to disk."""
        state = self.get_session_state()
        state["conversation_history"] = list(self.memory.conversation_history)
        path = self._session_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        path.write_text(json.dumps(state, indent=2))

    def load_session(self, session_id: str) -> bool:
        """Load session state from disk. Returns True if successful."""
        path = self._session_path(session_id)
        if not path.exists():
            return False
        try:
            import json
            state = json.loads(path.read_text())
            self.active_character = state.get("active_character")
            self.current_location = state.get("current_location", "unknown")
            self.current_time = datetime.fromisoformat(state.get("current_time", datetime.now().isoformat()))
            self.user_role = state.get("user_role", "protagonist")
            self.allow_auto_events = state.get("allow_auto_events", True)
            # Load conversation history
            history = state.get("conversation_history", [])
            from collections import deque
            self.memory.conversation_history = deque(history, maxlen=self.memory.max_history)
            return True
        except Exception as e:
            logger.warning(f"Failed to load session {session_id}: {e}")
            return False

    async def start_background_tasks(self):
        """Start director and memory optimizer if not already running."""
        pass
