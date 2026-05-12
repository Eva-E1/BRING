from __future__ import annotations

import json
import os
import tempfile
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from world_builder.llm import LLMClient
from world_builder.graph_manager import GraphManager
from .director import Director
from .story_engine import StoryEngine
from .memory_optimized import OptimizedMemoryStore
from .chronicler import Chronicler
from .validation import WorldValidator
from .quest_manager import QuestManager

@dataclass
class UserSession:
    session_id: str
    world_name: str
    current_time: datetime
    current_location: str = "unknown"
    active_character: Optional[str] = None
    user_role: str = "protagonist"
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    allow_auto_events: bool = True
    verbosity: str = "normal"

    def advance_time(self, minutes: int = 30) -> None:
        self.current_time += timedelta(minutes=minutes)

    def append_to_history(self, user_input: str, assistant_output: str) -> None:
        self.conversation_history.append({
            "user": user_input,
            "assistant": assistant_output,
            "timestamp": datetime.now().isoformat(),
        })
        self.conversation_history = self.conversation_history[-20:]


class UserAgent:
    def __init__(
        self,
        llm: LLMClient,
        gm: GraphManager,
        npc_mgr: OptimizedMemoryStore,
        chronicler: Chronicler,
        director: Director,
        story_engine: StoryEngine,
        validator: WorldValidator,
        quest_mgr: QuestManager,
        session_dir: Path,
    ):
        self.llm = llm
        self.gm = gm
        self.npc_mgr = npc_mgr
        self.chronicler = chronicler
        self.director = director
        self.story_engine = story_engine
        self.validator = validator
        self.quest_mgr = quest_mgr
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.party: List[str] = []   # list of character names in party

    def _session_path(self, session_id: str) -> Path:
        safe = "".join(c if c.isalnum() else "-" for c in session_id)
        return self.session_dir / f"{safe}.json"

    def _session_to_dict(self, session: UserSession) -> dict:
        return {
            "session_id": session.session_id,
            "world_name": session.world_name,
            "current_time": session.current_time.isoformat(),
            "current_location": session.current_location,
            "active_character": session.active_character,
            "party": self.party,
            "user_role": session.user_role,
            "conversation_history": session.conversation_history,
            "allow_auto_events": session.allow_auto_events,
            "verbosity": session.verbosity,
        }

    def _save_session_atomic(self, session: UserSession):
        path = self._session_path(session.session_id)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tf:
            json.dump(self._session_to_dict(session), tf, indent=2)
            temp_path = Path(tf.name)
        os.replace(temp_path, path)

    def _save_session(self, session: UserSession):
        self._save_session_atomic(session)

    async def new_session(
        self, session_id: str, world_name: str, start_time: datetime, active_character: str = None
    ) -> UserSession:
        session = UserSession(
            session_id=session_id,
            world_name=world_name,
            current_time=start_time,
            active_character=active_character,
        )
        self.party = [active_character] if active_character else []
        self._save_session(session)
        return session

    async def load_session(self, session_id: str) -> UserSession:
        path = self._session_path(session_id)
        data = json.loads(path.read_text())
        session = UserSession(
            session_id=data["session_id"],
            world_name=data["world_name"],
            current_time=datetime.fromisoformat(data["current_time"]),
            current_location=data.get("current_location", "unknown"),
            active_character=data.get("active_character"),
            user_role=data.get("user_role", "protagonist"),
            conversation_history=data.get("conversation_history", []),
            allow_auto_events=data.get("allow_auto_events", True),
            verbosity=data.get("verbosity", "normal"),
        )
        self.party = data.get("party", [])
        return session

    async def process_input(self, session: UserSession, user_input: str) -> str:
        lower = user_input.lower().strip()
        if lower.startswith("/"):
            return await self._handle_command(session, lower[1:])
        if any(token in lower for token in ("go ", "move ", "travel ")):
            match = re.search(r"(?:to|toward|into) ([a-z0-9' -]+)", lower)
            if match:
                dest = match.group(1).strip()
                ok, msg = await self.validator.validate_action(
                    session.active_character or "user", "move", location=dest
                )
                if not ok:
                    return msg
                session.current_location = dest
                for char in self.party:
                    await self.npc_mgr.move(char, dest, session.current_time)
                return f"You move to {dest}."
            return "Where do you want to go?"

        # Conversation memory: extract facts and store as episodes
        facts = self._extract_facts(user_input)
        for fact in facts:
            await self.chronicler.log_event(f"Player learned: {fact}", session.current_time, group="player_knowledge")

        # Generate narrative response
        context = await self.director.get_narrative_context(user_input, session.current_time)
        prompt = f"""
You are a narrative AI in the world "{session.world_name}".
Current time: {session.current_time.isoformat()}
Player role: {session.user_role}
Active character: {session.active_character or "none"}
Current location: {session.current_location}
Recent timeline: {context['relevant_history'][-3:]}
User input: {user_input}

Respond in character, move the story forward, and offer agency.
"""
        response = await self.llm.generate_text(prompt, temperature=0.8)
        session.append_to_history(user_input, response)
        self._save_session(session)

        if session.allow_auto_events:
            event_res = await self.director.advance_story(
                session.current_time,
                session.world_name,
                [session.active_character] if session.active_character else [],
            )
            if event_res.get("event"):
                response += f"\n\n[Story event] {event_res['event']['description']}"
            if event_res.get("next_story_time"):
                session.current_time = event_res["next_story_time"]
                self._save_session(session)

        return response

    def _extract_facts(self, text: str) -> List[str]:
        # Very basic extraction – in production use LLM
        matches = re.findall(r"([A-Z][a-z]+) (?:knows|has|owns) (?:the )?([a-z']+)", text)
        return [f"{m[0]} knows about {m[1]}" for m in matches]

    async def _handle_command(self, session: UserSession, cmd: str) -> str:
        parts = cmd.split()
        verb = parts[0].lower()
        if verb == "help":
            return ("Commands: /time, /status, /autoevents, /save, /look, /talk <npc>, /inventory, "
                    "/go <location>, /party add <name>, /party remove <name>, /party, /quests, /attack <target>")
        if verb == "look":
            loc_node = self.gm.store.get_by_name_and_type(session.current_location, "Location")
            if loc_node:
                l2 = loc_node.profile.l2
                return f"You see {l2.get('description', 'nothing special')}. Landmarks: {l2.get('landmarks', [])}"
            return "You look around but see nothing of note."
        if verb == "talk" and len(parts) > 1:
            npc_name = parts[1]
            npc_node = self.gm.store.get_by_name_and_type(npc_name, "Character")
            if not npc_node:
                return f"No one named '{npc_name}' is here."
            prompt = f"""{npc_name} is a {npc_node.profile.l2.get('personality','')} character.
Player says: "{' '.join(parts[2:]) or 'Hello'}".
Write {npc_name}'s response. Keep it short and in character."""
            response = await self.llm.generate_text(prompt, temperature=0.8)
            await self.chronicler.log_event(f"Player talked with {npc_name}", session.current_time)
            return f"{npc_name}: {response}"
        if verb == "inventory":
            state = await self.npc_mgr.get(session.active_character) if session.active_character else None
            if state:
                items = list(state.inventory)
                return f"You are carrying: {', '.join(items) or 'nothing'}"
            return "No active character."

        # NEW: /quests command - show active quests
        if verb == "quests":
            active_quests = [q for q in self.quest_mgr.quests.values() if q.status == "active"]
            if not active_quests:
                return "No active quests."
            result = "Active Quests:\n"
            for q in active_quests:
                result += f"- {q.title}: {q.description}\n"
            return result.strip()

        # NEW: /party command - show party status or add/remove members
        if verb == "party":
            if len(parts) == 1:
                # Show party status
                if not self.party:
                    return "Your party is empty."
                result = "Party members:\n"
                for member in self.party:
                    state = self.npc_mgr.get(member)
                    if state:
                        result += f"- {member}: {state.location} (HP: {state.health}, Mood: {state.mood})\n"
                    else:
                        result += f"- {member}\n"
                return result.strip()

            subcmd = parts[1]
            if subcmd == "add" and len(parts) > 2:
                name = parts[2]
                if self.gm.store.get_by_name_and_type(name, "Character"):
                    if name not in self.party:
                        self.party.append(name)
                        self._save_session(session)
                        return f"{name} joined the party."
                    return f"{name} is already in the party."
                return f"Unknown character '{name}'."
            elif subcmd == "remove" and len(parts) > 2:
                name = parts[2]
                if name in self.party:
                    self.party.remove(name)
                    self._save_session(session)
                    return f"{name} left the party."
                return f"{name} not in party."

        # NEW: /attack command - simulate combat
        if verb == "attack" and len(parts) > 1:
            target = parts[1]
            # Validate attack against world rules
            character = session.active_character or "user"
            ok, msg, _ = await self.validator.validate_action(
                character, "attack", location=session.current_location, target=target
            )
            if not ok:
                return msg

            # Validate target exists
            target_node = self.gm.store.get_by_name_and_type(target, "Character")
            if not target_node:
                return f"No character named '{target}' found here."

            # Generate combat outcome via LLM
            prompt = f"""Simulate a fight between {character} and {target} in location {session.current_location}.
Consider their abilities, equipment, and the situation.
Provide a brief narrative outcome (2-3 sentences) and indicate if anyone was injured.
Return JSON: {{"outcome": "narrative text", "damage_taken": integer, "damage_dealt": integer, "victory": boolean}}"""

            try:
                result = await self.llm.generate_json(prompt, temperature=0.7)
                outcome = result.get("outcome", "The fight concluded.")
                damage_taken = result.get("damage_taken", 0)
                damage_dealt = result.get("damage_dealt", 0)
                victory = result.get("victory", False)

                # Apply damage to player
                if damage_taken > 0 and session.active_character:
                    await self.npc_mgr.adjust_health(session.active_character, -damage_taken)

                # Apply damage to target
                if damage_dealt > 0:
                    await self.npc_mgr.adjust_health(target, -damage_dealt)

                # Log the combat
                await self.chronicler.log_event(
                    f"{character} attacked {target}: {outcome}",
                    session.current_time,
                    group="combat"
                )

                result_msg = outcome
                if damage_taken > 0:
                    result_msg += f" You took {damage_taken} damage."
                if damage_dealt > 0:
                    result_msg += f" {target} took {damage_dealt} damage."
                if victory:
                    result_msg += " Victory!"
                else:
                    result_msg += " Defeat!"

                return result_msg

            except Exception as e:
                return f"The attack failed: {str(e)}"

        if verb == "time":
            return f"Story time: {session.current_time.isoformat()}"
        if verb == "status":
            state = await self.npc_mgr.get(session.active_character) if session.active_character else None
            if state:
                return f"Location: {state.location}\nHealth: {state.health}\nMood: {state.mood}\nGoals: {state.goals}"
            return f"Location: {session.current_location}\nNo active character."
        if verb == "autoevents":
            session.allow_auto_events = not session.allow_auto_events
            self._save_session(session)
            return f"Auto events: {session.allow_auto_events}"
        if verb == "save":
            self._save_session(session)
            return "Session saved."
        return f"Unknown command: {verb}. Type /help."
