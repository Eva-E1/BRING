from __future__ import annotations
from world_builder.llm import LLMClient
from world_engine.prompt_builder import PromptBuilder


class NarratorAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def generate(
        self,
        context: dict,
        recent_memories: list,
        world_facts: list,
        conversation_history: list,
    ) -> str:
        prompt = PromptBuilder.build_narrator_prompt(
            context, recent_memories, world_facts, conversation_history
        )
        response = await self.llm.generate_text(prompt, temperature=0.8)
        return response.strip()
