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
from world_core.probability import (
    ProbabilityEngine,
    ProbabilityContextResolver,
    PROFILES,
    get_profile,
    OutcomeQuality,
)

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
        world_memory: "WorldMemory" = None,
        prob_engine: ProbabilityEngine = None,
        prob_resolver: ProbabilityContextResolver = None,
        history_mgr = None,
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
        self.world_memory = world_memory
        self.history_mgr = history_mgr

        # Track active session ID for history management
        self.active_session_id: Optional[str] = None

        # Probability system - use passed instances or create defaults
        self.prob_engine = prob_engine or ProbabilityEngine(global_luck=0.5)
        self.prob_resolver = prob_resolver or ProbabilityContextResolver(gm, npc_mgr, world_memory)
        self.prob_engine.set_context_resolver(self.prob_resolver)

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

        # Track visited locations for automatic subgraph expansion
        self.visited_locations: set = set()

    def set_session(
        self,
        character: Optional[str],
        location: str,
        story_time: datetime,
        role: str = "protagonist",
        session_id: str = None,
    ):
        self.active_character = character
        self.current_location = location
        self.current_time = story_time
        self.user_role = role
        self.active_session_id = session_id

    async def _get_relevant_memories(self, context_query: str) -> List[str]:
        """Retrieve relevant world and NPC memories for the current context."""
        memories = []

        # Use unified WorldMemory if available
        if self.world_memory is not None:
            # Get nearby NPCs and location for filtering
            nearby_npcs = await self._get_nearby_npcs()
            entity_filter = set(nearby_npcs) | {self.active_character} if self.active_character else set(nearby_npcs)

            world_mems = await self.world_memory.retrieve(
                query=context_query,
                top_k=8,
                entity_filter=entity_filter if entity_filter else None,
                time_window=timedelta(hours=2),
                min_importance=0.2,  # Skip low-importance memories for performance
            )
            for m in world_mems:
                source_label = f"[{m['source_type']}: {m['source']}]"
                memories.append(f"{source_label} {m['content']}")
        else:
            # Fallback to NPC-only memory retrieval
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
        if self.world_memory is not None:
            facts = self.world_memory.get_recent_global_facts(limit=5)
            return [f["fact"] for f in facts]
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

        # Track location visit in unified world memory
        if self.world_memory is not None and self.active_character:
            await self.world_memory.add_location_visit(
                location_uid=loc_node.uid,
                location_name=destination,
                visitor_name=self.active_character,
                importance=0.3,
            )

        # Auto-expand subgraph on first visit to this location
        if loc_node.uid not in self.visited_locations:
            self.visited_locations.add(loc_node.uid)
            try:
                from world_intelligence.subgraph_expander import SubgraphExpander
                from world_explorer.builder_integration import BuilderInterface
                expander = SubgraphExpander(self.graph_store, BuilderInterface(self.db_path, gm=self.gm))
                report = await expander.expand_async(
                    loc_node.uid,
                    depth=1,
                    complete_layers=True,
                    check_rules=True,
                    generate_scene=False
                )
                await self.chronicler.log_event(
                    f"[System] Expanded subgraph around {destination}: {report.get('nodes_in_subgraph', 0)} nodes",
                    self.current_time,
                    group="system"
                )
            except Exception as e:
                logger.warning(f"Subgraph expansion failed: {e}")

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

        # Log to persistent history if history manager is available
        if self.history_mgr and self.active_session_id:
            self.history_mgr.add_turn(
                self.active_session_id,
                "user",
                user_input,
                metadata={"timestamp": datetime.now().isoformat()}
            )
            self.history_mgr.add_turn(
                self.active_session_id,
                "assistant",
                narrative,
                metadata={"timestamp": datetime.now().isoformat(), "action": "narrative"}
            )

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

        # Probability-based action commands
        if verb in ("attack", "fight", "hit"):
            return await self._handle_attack(parts[1] if len(parts) > 1 else None)
        if verb in ("persuade", "convince", "persuasion"):
            return await self._handle_persuade(parts[1] if len(parts) > 1 else None, " ".join(parts[2:]) if len(parts) > 2 else "")
        if verb in ("stealth", "sneak", "hide"):
            return await self._handle_stealth()
        if verb in ("intimidate", "threaten"):
            return await self._handle_intimidate(parts[1] if len(parts) > 1 else None)
        if verb in ("deception", "lie", "bluff"):
            return await self._handle_deception(parts[1] if len(parts) > 1 else None, " ".join(parts[2:]) if len(parts) > 2 else "")
        if verb == "chance":
            return await self._handle_chance(parts[1] if len(parts) > 1 else "generic", parts[2] if len(parts) > 2 else None)

        # Probability management commands
        if verb == "prob":
            if len(parts) < 2:
                return "Usage: /prob show <profile> [target] | /prob list | /prob modify <entity> <parameter> <value> [duration]"
            sub = parts[1].lower()
            if sub == "show":
                profile_name = parts[2] if len(parts) > 2 else "generic"
                target = parts[3] if len(parts) > 3 else None
                return await self._show_probability(profile_name, target)
            elif sub == "list":
                return await self._list_modifiers()
            elif sub == "modify":
                if len(parts) < 5:
                    return "Usage: /prob modify <entity> <parameter> <value> [duration_seconds]"
                entity = parts[2]
                param = parts[3]
                try:
                    value = float(parts[4])
                except ValueError:
                    return f"Invalid value: {parts[4]}"
                duration = int(parts[5]) if len(parts) > 5 else None
                return await self._apply_modifier(entity, param, value, duration)
            elif sub == "skill":
                # Show current skills
                if not self.active_character:
                    return "No active character."
                profile = self.npc_mgr.get(self.active_character)
                if not profile:
                    return f"Character {self.active_character} not found."
                skills = profile.skills or {}
                if not skills:
                    return "No skills defined."
                lines = [f"Skills for {self.active_character}:"]
                for skill, value in sorted(skills.items()):
                    lines.append(f"  {skill}: {value:.2f}")
                return "\n".join(lines)
            else:
                return f"Unknown /prob subcommand: {sub}"

        return f"Unknown command: {verb}. Type /help."

    # ------------------------------------------------------------------
    # Probability-Based Action Handlers
    # ------------------------------------------------------------------

    async def _build_prob_context(self, action_type: str, target: Optional[str] = None) -> Dict[str, Any]:
        """Build context for probability calculation."""
        return await self.prob_resolver.build_context(
            actor=self.active_character or "Player",
            target=target,
            action_type=action_type,
            location=self.current_location,
        )

    async def _handle_attack(self, target: Optional[str]) -> str:
        """Handle combat attack with probability-based resolution."""
        if not self.active_character:
            return "You need to control a character to attack."
        if not target:
            return "Attack whom? Usage: /attack <target>"

        # Validate target exists
        target_node = self.gm.store.get_by_name_and_type(target, "Character")
        if not target_node:
            return f"You don't see '{target}' here."

        # Build context and calculate probability
        context = await self._build_prob_context("combat", target)
        profile = get_profile("combat")
        result = self.prob_engine.roll(profile, context, self.active_character)

        # Generate narrative based on outcome
        narrative = await self._generate_action_narrative(
            action="attack",
            actor=self.active_character,
            target=target,
            result=result,
        )

        # Apply mechanical effects
        damage = 0
        if result.quality == OutcomeQuality.CRITICAL_SUCCESS:
            damage = 20
        elif result.quality == OutcomeQuality.SUCCESS:
            damage = 10
        elif result.quality == OutcomeQuality.MARGINAL_SUCCESS:
            damage = 5
        elif result.quality == OutcomeQuality.CRITICAL_FAILURE:
            # Counterattack!
            damage = -5

        if damage != 0:
            await self.npc_mgr.adjust_health(target, damage)
            effect_text = f" {target} takes {abs(damage)} damage!" if damage > 0 else f" You take {abs(damage)} damage!"
            narrative += effect_text

        await self.chronicler.log_event(
            f"{self.active_character} attacks {target}: {result.quality.value}",
            self.current_time,
            "combat"
        )

        return narrative

    async def _handle_persuade(self, target: Optional[str], message: str) -> str:
        """Handle persuasion attempt with probability-based resolution."""
        if not self.active_character:
            return "You need to control a character to persuade."
        if not target:
            return "Persuade whom? Usage: /persuade <target> <message>"
        if not message:
            return "What do you want to say? Usage: /persuade <target> <message>"

        # Build context with argument quality
        extra = {"argument_quality": min(1.0, len(message) / 100.0)}
        context = await self._build_prob_context("persuasion", target)
        context.update({f"extra_{k}": v for k, v in extra.items()})

        profile = get_profile("persuasion")
        result = self.prob_engine.roll(profile, context, self.active_character)

        # Generate response based on outcome
        narrative = await self._generate_action_narrative(
            action="persuade",
            actor=self.active_character,
            target=target,
            result=result,
            extra=f' saying "{message}"'
        )

        await self.chronicler.log_event(
            f"{self.active_character} persuades {target}: {result.quality.value}",
            self.current_time,
            "social"
        )

        return narrative

    async def _handle_stealth(self) -> str:
        """Handle stealth attempt with probability-based resolution."""
        if not self.active_character:
            return "You need to control a character to sneak."

        context = await self._build_prob_context("stealth")
        profile = get_profile("stealth")
        result = self.prob_engine.roll(profile, context, self.active_character)

        narrative = await self._generate_action_narrative(
            action="stealth",
            actor=self.active_character,
            target=None,
            result=result,
        )

        await self.chronicler.log_event(
            f"{self.active_character} attempts to sneak: {result.quality.value}",
            self.current_time,
            "stealth"
        )

        return narrative

    async def _handle_intimidate(self, target: Optional[str]) -> str:
        """Handle intimidation attempt with probability-based resolution."""
        if not self.active_character:
            return "You need to control a character to intimidate."
        if not target:
            return "Intimidate whom? Usage: /intimidate <target>"

        context = await self._build_prob_context("intimidation", target)
        profile = get_profile("intimidation")
        result = self.prob_engine.roll(profile, context, self.active_character)

        narrative = await self._generate_action_narrative(
            action="intimidate",
            actor=self.active_character,
            target=target,
            result=result,
        )

        await self.chronicler.log_event(
            f"{self.active_character} intimidates {target}: {result.quality.value}",
            self.current_time,
            "social"
        )

        return narrative

    async def _handle_deception(self, target: Optional[str], lie: str) -> str:
        """Handle deception attempt with probability-based resolution."""
        if not self.active_character:
            return "You need to control a character to lie."
        if not target:
            return "Lie to whom? Usage: /deception <target> <lie>"
        if not lie:
            return "What do you want to say? Usage: /deception <target> <lie>"

        extra = {"lie_quality": min(1.0, len(lie) / 100.0)}
        context = await self._build_prob_context("deception", target)
        context.update({f"extra_{k}": v for k, v in extra.items()})

        profile = get_profile("deception")
        result = self.prob_engine.roll(profile, context, self.active_character)

        narrative = await self._generate_action_narrative(
            action="lie",
            actor=self.active_character,
            target=target,
            result=result,
            extra=f' saying "{lie}"'
        )

        return narrative

    async def _handle_chance(self, action_type: str, target: Optional[str]) -> str:
        """Show probability of success for an action without performing it."""
        if not self.active_character:
            return "You need to control a character to check chances."

        profile = get_profile(action_type)
        if not profile:
            return f"Unknown action type: {action_type}. Available: {', '.join(PROFILES.keys())}"

        context = await self._build_prob_context(action_type, target)
        probability = self.prob_engine.get_success_chance(profile, context, self.active_character)

        return f"Chance of {action_type} success: {probability:.0%}"

    async def _generate_action_narrative(
        self,
        action: str,
        actor: str,
        target: Optional[str],
        result,
        extra: str = "",
    ) -> str:
        """Generate narrative description for a probability-based action."""
        quality = result.quality.value

        # Build prompt for LLM to generate narrative
        target_text = f" {target}" if target else ""
        quality_descriptions = {
            "critical_success": f"{actor} executes a perfect {action}!{extra}",
            "success": f"{actor} successfully {action}s{target_text}.{extra}",
            "marginal_success": f"{actor} barely manages to {action}{target_text}.{extra}",
            "failure": f"{actor} fails to {action}{target_text}.{extra}",
            "critical_failure": f"{actor} completely botches the {action} attempt{extra}!",
        }

        base_narrative = quality_descriptions.get(quality, f"{actor} attempts to {action}{target_text}.")

        # Optionally enhance with LLM
        if self.llm_queue:
            try:
                prompt = f"""Write a brief, vivid description (1-2 sentences) of this action:
Actor: {actor}
Action: {action}{extra}
Target: {target or 'none'}
Outcome: {quality}
Probability: {result.probability:.0%}
Roll: {result.roll:.0%}

Keep it concise and immersive."""
                narrative = await self.llm_queue.generate_text(prompt, temperature=0.7, max_tokens=100)
                if narrative:
                    return narrative.strip()
            except Exception:
                pass  # Fall back to template

        return base_narrative

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
            # Load session ID and conversation history
            self.active_session_id = session_id
            history = state.get("conversation_history", [])
            from collections import deque
            self.memory.conversation_history = deque(history, maxlen=self.memory.max_history)
            # Also load from persistent history manager if available
            if self.history_mgr and self.history_mgr.session_exists(session_id):
                # Rebuild in-memory history from persistent storage
                pairs = self.history_mgr.get_conversation_pairs(session_id)
                self.memory.conversation_history.clear()
                for pair in pairs[-20:]:  # Last 20 pairs
                    self.memory.add_entry(pair["user"]["content"], pair["assistant"]["content"])
            return True
        except Exception as e:
            logger.warning(f"Failed to load session {session_id}: {e}")
            return False

    async def start_background_tasks(self):
        """Start director and memory optimizer if not already running."""
        pass

    # ------------------------------------------------------------------
    # Probability CLI helpers (/prob commands)
    # ------------------------------------------------------------------

    async def _show_probability(self, profile_name: str, target: Optional[str] = None) -> str:
        """Show success probability for a given profile and optional target."""
        if not self.active_character:
            return "No active character."

        profile = get_profile(profile_name)
        if not profile:
            return f"Unknown profile: {profile_name}. Available: {', '.join(PROFILES.keys())}"

        context = await self._build_prob_context(profile_name, target)
        probability = self.prob_engine.get_success_chance(profile, context, self.active_character)

        # Get actor's relevant skill
        skill_name = profile_name.lower()
        actor_profile = self.npc_mgr.get(self.active_character)
        skill_value = 0.5
        if actor_profile and actor_profile.skills:
            skill_value = actor_profile.skills.get(skill_name, 0.5)

        return (f"{profile_name.capitalize()} chance for {self.active_character}: "
                f"{probability:.0%} (skill: {skill_value:.0%})")

    async def _list_modifiers(self) -> str:
        """List all active probability modifiers for the current character."""
        if not self.active_character:
            return "No active character."

        uid = f"Character:{self.active_character}"
        summary = self.prob_engine.get_modifier_summary(uid)

        if not summary["total_modifiers"]:
            return "No active modifiers."

        lines = [f"Active modifiers for {self.active_character}:",
                 f"Total: {summary['total_modifiers']}"]

        for param, mods in summary["by_parameter"].items():
            for m in mods:
                expiry = ""
                if m.get("expires_at"):
                    from datetime import datetime
                    exp = datetime.fromtimestamp(m["expires_at"])
                    expiry = f" (expires {exp.strftime('%H:%M:%S')})"
                lines.append(f"  {param}: {m['value']:+} ({m['type']}) from {m['source']}{expiry}")

        return "\n".join(lines)

    async def _apply_modifier(self, entity: str, param: str, value: float, duration: Optional[int] = None) -> str:
        """Apply a probability modifier to an entity."""
        from world_core.probability import ProbabilityModifier, ModifierType

        uid = f"Character:{entity}" if ":" not in entity else entity
        modifier = ProbabilityModifier(
            parameter_name=param,
            value=value,
            modifier_type=ModifierType.ADD,
            duration_seconds=duration,
            source="player_command"
        )
        self.prob_engine.apply_modifier(uid, modifier)

        dur_text = f" for {duration}s" if duration else " permanently"
        return f"Applied {param} {value:+.1f} to {entity}{dur_text}."
