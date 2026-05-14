from __future__ import annotations
from world_core.llm_queue import GlobalLLMQueue
from world_director.models import TaskPriority
from world_engine.prompt_builder import PromptBuilder


class NPCAgent:
    def __init__(self, llm_queue: GlobalLLMQueue):
        self.llm_queue = llm_queue

    async def respond(
        self,
        npc_name: str,
        npc_personality: str,
        player_character: str,
        location: str,
        player_line: str,
        recent_events: list,
        relationship: str = "neutral",
    ) -> str:
        prompt = PromptBuilder.build_npc_prompt(
            npc_name,
            npc_personality,
            player_character,
            location,
            player_line,
            recent_events,
            relationship,
        )
        return await self.llm_queue.generate_text(
            prompt, priority=TaskPriority.HIGH, temperature=0.7
        )
