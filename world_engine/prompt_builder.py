from __future__ import annotations
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds rich, context‑aware prompts for different narrative agents."""

    @staticmethod
    def build_narrator_prompt(
        context: Dict[str, Any],
        recent_memories: List[str],
        world_facts: List[str],
        conversation_history: List[Dict],
    ) -> str:
        """Prompt for the narrator agent (describes world, events, NPCs)."""
        timeline = "\n".join(f"- {e}" for e in context.get("recent_timeline", [])[-5:])
        rules = "\n".join(f"- {r}" for r in context.get("world_rules", []))
        memories = "\n".join(f"- {m}" for m in recent_memories[:5]) if recent_memories else "None"
        facts = "\n".join(f"- {f}" for f in world_facts[:3]) if world_facts else "None"
        history = "\n".join(
            f"User: {h['user']}\nAssistant: {h['assistant']}" for h in conversation_history[-3:]
        ) if conversation_history else "No previous conversation."

        return f"""You are a master storyteller in the world "{context['world_name']}".

Current story time: {context['current_time']}
Location: {context['location']}
Active character: {context['active_character'] or "none"}
User role: {context['user_role']}

World rules:
{rules}

Recent timeline:
{timeline}

Recent conversation:
{history}

Relevant memories about this character and world:
{memories}

World facts:
{facts}

Nearby NPCs: {', '.join(context.get('nearby_npcs', [])) or "None"}

The user is controlling {context['active_character'] or "their character"}.
You MUST NOT speak or act for the user's character. You only describe the environment, the actions and dialogue of NPCs, and the consequences of the user's choices.

Respond in immersive, third‑person descriptive prose. Move the story forward naturally. Describe what the user sees, hears, smells, and feels. If there are NPCs present, you can describe their appearance, mood, and what they do or say.

Output only the narrative text, no extra commentary.
"""

    @staticmethod
    def build_npc_prompt(
        npc_name: str,
        npc_personality: str,
        player_character: str,
        location: str,
        player_line: str,
        recent_events: List[str],
        relationship: str = "neutral",
    ) -> str:
        """Prompt for NPC dialogue responses."""
        events = "\n".join(f"- {e}" for e in recent_events[-3:]) if recent_events else "None"
        return f"""{npc_name} is a {npc_personality} character currently in {location}.
Their relationship with {player_character} is {relationship}.

Recent events: {events}

{player_character} says: "{player_line}"

Write {npc_name}'s response in character. Keep it short, natural, and consistent with their personality.
Return only the dialogue line, no extra description.
"""

    @staticmethod
    def build_scene_transition_prompt(
        current_location: str,
        destination: str,
        character: str,
        recent_events: List[str],
        world_rules: List[str],
    ) -> str:
        """Prompt for scene agent when moving to a new location."""
        events = "\n".join(f"- {e}" for e in recent_events[-3:]) if recent_events else "None"
        rules = "\n".join(f"- {r}" for r in world_rules)
        return f"""You are a scene agent. The player character {character} is moving from "{current_location}" to "{destination}".
Describe the journey and arrival. Do NOT speak or act for the character; just describe the environment, any obstacles, sights, and sounds.
World rules: {rules}
Recent events: {events}
Generate a short narrative (2-4 sentences). Output only the narrative text.
"""
