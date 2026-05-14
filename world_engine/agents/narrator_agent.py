from __future__ import annotations
from world_core.llm_queue import GlobalLLMQueue
from world_director.models import TaskPriority
from world_engine.prompt_builder import PromptBuilder


class NarratorAgent:
    def __init__(self, llm_queue: GlobalLLMQueue):
        self.llm_queue = llm_queue

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
        response = await self.llm_queue.generate_text(
            prompt, priority=TaskPriority.HIGH, temperature=0.8
        )
        return response.strip()
