from __future__ import annotations
from world_builder.llm import LLMClient
from world_engine.prompt_builder import PromptBuilder


class NPCAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

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
        return await self.llm.generate_text(prompt, temperature=0.7)
