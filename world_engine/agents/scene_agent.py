from __future__ import annotations
from world_core.llm_queue import GlobalLLMQueue
from world_director.models import TaskPriority
from world_engine.prompt_builder import PromptBuilder


class SceneAgent:
    def __init__(self, llm_queue: GlobalLLMQueue):
        self.llm_queue = llm_queue

    async def transition(
        self,
        current_location: str,
        destination: str,
        character: str,
        recent_events: list,
        world_rules: list,
    ) -> str:
        prompt = PromptBuilder.build_scene_transition_prompt(
            current_location, destination, character, recent_events, world_rules
        )
        return await self.llm_queue.generate_text(
            prompt, priority=TaskPriority.HIGH, temperature=0.8
        )
